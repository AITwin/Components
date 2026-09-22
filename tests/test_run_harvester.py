"""Tests for the run_harvester gating logic, in particular the period-style
``end_date`` gate that ensures we only fire once a Brussels-day's worth of
source data has elapsed.
"""
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FILE_STORAGE_DIRECTORY", "/tmp/storage")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from importlib import import_module  # noqa: E402
runner = import_module("src.runners.run_harvester")


class _Row:
    def __init__(self, date):
        self.date = date


def _config(source_range="1d@Europe/Brussels"):
    cfg = MagicMock()
    cfg.name = "h"
    cfg.source.name = "s"
    cfg.source_range = source_range
    cfg.source_range_strict = True
    cfg.dependencies = []
    cfg.dependencies_limit = []
    cfg.optional_dependencies = []
    cfg.optional_dependencies_limit = None
    cfg.multiple_results = False
    instance = MagicMock()
    instance.run.return_value = b"out"
    cfg.component.return_value = instance
    return cfg, instance


def _tables():
    return {"h": MagicMock(name="harvester_table"),
            "s": MagicMock(name="source_table")}


class PeriodGate(unittest.TestCase):
    def setUp(self):
        runner._first_row_date_cache.clear()

    def test_bootstrap_skips_when_period_not_elapsed(self):
        cfg, instance = _config()
        tables = _tables()
        first_source = _Row(datetime(2025, 9, 10, 6, 0))  # 08:00 Brussels (CEST)
        # Brussels-day 2025-09-10 ends at 2025-09-10 22:00 UTC.
        # Source has only mid-day data, nothing past 22:00 UTC → must not fire.
        with patch.object(runner, "retrieve_latest_row", return_value=None), \
             patch.object(runner, "retrieve_first_row", return_value=first_source), \
             patch.object(runner, "retrieve_between_datetime",
                          return_value=[_Row(datetime(2025, 9, 10, 12, 0))]), \
             patch.object(runner, "retrieve_after_datetime", return_value=[]) as gate, \
             patch.object(runner, "write_result") as write:
            ok = runner.run_harvester(cfg, tables)
        self.assertFalse(ok)
        instance.run.assert_not_called()
        write.assert_not_called()
        # The gate must look at the source table, past end_date (not the harvester table).
        gate.assert_called_with(tables["s"], datetime(2025, 9, 10, 22, 0), 1)

    def test_bootstrap_fires_when_source_past_end_date(self):
        cfg, instance = _config()
        tables = _tables()
        first_source = _Row(datetime(2025, 9, 10, 6, 0))
        snapshots = [_Row(datetime(2025, 9, 10, h, 0)) for h in (6, 12, 18)]
        with patch.object(runner, "retrieve_latest_row", return_value=None), \
             patch.object(runner, "retrieve_first_row", return_value=first_source), \
             patch.object(runner, "retrieve_between_datetime", return_value=snapshots), \
             patch.object(runner, "retrieve_after_datetime",
                          return_value=[_Row(datetime(2025, 9, 11, 1, 0))]), \
             patch.object(runner, "write_result") as write:
            ok = runner.run_harvester(cfg, tables)
        self.assertTrue(ok)
        instance.run.assert_called_once_with(snapshots)
        # write_result is called with the period end as the storage date.
        self.assertEqual(write.call_args.args[3], datetime(2025, 9, 10, 22, 0))

    def test_subsequent_run_advances_to_next_brussels_day(self):
        cfg, instance = _config()
        tables = _tables()
        # Last harvested storage_date is exactly previous Brussels midnight in UTC.
        last_harvested = _Row(datetime(2025, 9, 10, 22, 0))
        snapshots = [_Row(datetime(2025, 9, 11, h, 0)) for h in (6, 12, 18)]
        with patch.object(runner, "retrieve_latest_row", return_value=last_harvested), \
             patch.object(runner, "retrieve_between_datetime",
                          return_value=snapshots) as between, \
             patch.object(runner, "retrieve_after_datetime",
                          return_value=[_Row(datetime(2025, 9, 12, 1, 0))]), \
             patch.object(runner, "write_result") as write:
            ok = runner.run_harvester(cfg, tables)
        self.assertTrue(ok)
        # Window must be the *next* Brussels day, not the same one.
        between.assert_called_once_with(
            tables["s"],
            datetime(2025, 9, 10, 22, 0),
            datetime(2025, 9, 11, 22, 0),
            None,
        )
        self.assertEqual(write.call_args.args[3], datetime(2025, 9, 11, 22, 0))


if __name__ == "__main__":
    unittest.main()


class LatestOnly(unittest.TestCase):
    """A live harvester with LATEST_ONLY skips the backlog and takes the newest source row."""

    def setUp(self):
        runner._first_row_date_cache.clear()

    def _run(self, latest_only):
        cfg, instance = _config(source_range=None)
        cfg.latest_only = latest_only
        tables = _tables()
        last_harvested = _Row(datetime(2026, 9, 22, 7, 37))
        backlog_next = _Row(datetime(2026, 9, 22, 7, 38))
        newest = _Row(datetime(2026, 9, 22, 11, 43))

        def latest_row(table, with_null=False):
            return last_harvested if table is tables["h"] else newest

        with patch.object(runner, "retrieve_latest_row", side_effect=latest_row), \
             patch.object(runner, "retrieve_between_datetime", return_value=[backlog_next]), \
             patch.object(runner, "retrieve_after_datetime", return_value=[newest]), \
             patch.object(runner, "write_result") as write:
            self.assertTrue(runner.run_harvester(cfg, tables))
        return instance.run.call_args[0][0], write.call_args[0][3]

    def test_skips_to_newest_source_row(self):
        source, stored_at = self._run(latest_only=True)
        self.assertEqual(source.date, datetime(2026, 9, 22, 11, 43))
        self.assertEqual(stored_at, datetime(2026, 9, 22, 11, 43))

    def test_default_works_through_the_backlog(self):
        source, stored_at = self._run(latest_only=False)
        self.assertEqual(source.date, datetime(2026, 9, 22, 7, 38))
        self.assertEqual(stored_at, datetime(2026, 9, 22, 7, 38))
