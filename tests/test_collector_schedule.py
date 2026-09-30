"""Daily collectors make up a missed run at startup and retry a failed one."""
import importlib
import os
import sys
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FILE_STORAGE_DIRECTORY", "/tmp/storage")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schedule  # noqa: E402

rc = importlib.import_module("src.runners.run_collector")


def _config(sched, component=None):
    return SimpleNamespace(name="x_gtfs", schedule=sched, component=component, data_type="binary")


class Overdue(unittest.TestCase):
    def _overdue(self, sched, latest, now):
        row = None if latest is None else SimpleNamespace(date=latest)
        with mock.patch.object(rc, "retrieve_latest_row", lambda table: row):
            return rc._is_overdue(_config(sched), None, now)

    def test_daily_run_that_left_no_row_is_made_up(self):
        # due at 00:20 on the 23rd, last row from the 22nd: the run failed
        self.assertTrue(self._overdue("00:20", datetime(2026, 9, 22, 0, 21), datetime(2026, 9, 23, 5, 0)))

    def test_daily_run_done_is_not_repeated(self):
        self.assertFalse(self._overdue("00:20", datetime(2026, 9, 23, 0, 20, 30), datetime(2026, 9, 23, 5, 0)))

    def test_before_today_due_time_yesterdays_row_is_enough(self):
        self.assertFalse(self._overdue("04:20", datetime(2026, 9, 22, 4, 21), datetime(2026, 9, 23, 3, 0)))

    def test_interval_schedules_unchanged(self):
        self.assertTrue(self._overdue("7d", datetime(2026, 9, 1), datetime(2026, 9, 23)))
        self.assertFalse(self._overdue("7d", datetime(2026, 9, 20), datetime(2026, 9, 23)))


class Retry(unittest.TestCase):
    def setUp(self):
        schedule.clear()
        self.addCleanup(schedule.clear)

    def _collector(self, outcomes):
        calls = {"n": 0}

        class C:
            def run(self):
                ok = outcomes[min(calls["n"], len(outcomes) - 1)]
                calls["n"] += 1
                if not ok:
                    raise RuntimeError("database refused the connection")
                return None
        return C, calls

    def test_a_failed_daily_run_is_retried_until_it_succeeds(self):
        cls, calls = self._collector([False, False, True])
        rc._run_or_retry(_config("00:20", cls), None, False)
        self.assertEqual(len(schedule.jobs), 1)
        for _ in range(3):
            schedule.run_all()
        self.assertEqual(calls["n"], 3)
        self.assertEqual(schedule.jobs, [])

    def test_retries_stop_after_the_limit(self):
        cls, calls = self._collector([False])
        rc._run_or_retry(_config("04:20", cls), None, False)
        for _ in range(10):
            schedule.run_all()
        self.assertEqual(calls["n"], 1 + rc.RETRY_TIMES)
        self.assertEqual(schedule.jobs, [])

    def test_frequent_collectors_just_wait_for_the_next_run(self):
        cls, calls = self._collector([False])
        rc._run_or_retry(_config("20s", cls), None, False)
        self.assertEqual(schedule.jobs, [])


if __name__ == "__main__":
    unittest.main()
