"""Tests for source_range_to_period_and_limit, focused on the @<tz> path.

The legacy timezone-naive paths are exercised lightly to guard against
regressions while the timezone-aware path is checked across DST transitions.
"""
import os
import sys
import unittest
from datetime import datetime

# Stub the env vars the storage/engine modules expect so the import succeeds
# without a real DB or storage backend.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FILE_STORAGE_DIRECTORY", "/tmp/storage")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.runners.run_harvester import source_range_to_period_and_limit  # noqa: E402


class LegacyBehaviour(unittest.TestCase):
    def test_none_returns_single_row(self):
        d = datetime(2024, 5, 6, 14, 0)
        self.assertEqual(source_range_to_period_and_limit(d, None), (d, None, 1))

    def test_int_limit(self):
        d = datetime(2024, 5, 6, 14, 0)
        self.assertEqual(source_range_to_period_and_limit(d, 5), (d, None, 5))

    def test_str_digit_limit(self):
        d = datetime(2024, 5, 6, 14, 0)
        self.assertEqual(source_range_to_period_and_limit(d, "7"), (d, None, 7))

    def test_legacy_1d_is_rolling_24h(self):
        d = datetime(2024, 5, 6, 14, 23, 11)
        start, end, limit = source_range_to_period_and_limit(d, "1d")
        self.assertEqual(start, d)
        self.assertEqual(end, datetime(2024, 5, 7, 14, 23, 11))
        self.assertIsNone(limit)

    def test_legacy_1h_is_rolling_hour(self):
        d = datetime(2024, 5, 6, 14, 23, 11)
        start, end, _ = source_range_to_period_and_limit(d, "1h")
        # 14 % 1 == 0, so no subtraction; only an offset of one hour is added.
        self.assertEqual(start, d)
        self.assertEqual(end, datetime(2024, 5, 6, 15, 23, 11))


class TimezoneAlignedPeriod(unittest.TestCase):
    def test_1d_at_brussels_summer(self):
        # 2024-05-06 14:23 UTC is 16:23 Brussels (CEST, UTC+2).
        # Window should cover Brussels-day 2024-05-06: [05-05 22:00 UTC, 05-06 22:00 UTC).
        d = datetime(2024, 5, 6, 14, 23, 11)
        start, end, limit = source_range_to_period_and_limit(d, "1d@Europe/Brussels")
        self.assertEqual(start, datetime(2024, 5, 5, 22, 0))
        self.assertEqual(end, datetime(2024, 5, 6, 22, 0))
        self.assertIsNone(limit)
        self.assertEqual((end - start).total_seconds(), 24 * 3600)

    def test_1d_at_brussels_winter(self):
        # 2024-01-15 14:23 UTC is 15:23 Brussels (CET, UTC+1).
        d = datetime(2024, 1, 15, 14, 23, 11)
        start, end, _ = source_range_to_period_and_limit(d, "1d@Europe/Brussels")
        self.assertEqual(start, datetime(2024, 1, 14, 23, 0))
        self.assertEqual(end, datetime(2024, 1, 15, 23, 0))
        self.assertEqual((end - start).total_seconds(), 24 * 3600)

    def test_1d_late_in_utc_day_aligns_to_local_day(self):
        # 2024-05-06 23:30 UTC is 2024-05-07 01:30 Brussels — window is the
        # Brussels day that *contains* the local time, i.e. 2024-05-07.
        d = datetime(2024, 5, 6, 23, 30)
        start, end, _ = source_range_to_period_and_limit(d, "1d@Europe/Brussels")
        self.assertEqual(start, datetime(2024, 5, 6, 22, 0))
        self.assertEqual(end, datetime(2024, 5, 7, 22, 0))

    def test_1d_at_brussels_dst_spring_forward_is_23h(self):
        # 2024-03-31: clocks jump 02:00 CET -> 03:00 CEST. Brussels-day is 23 h.
        d = datetime(2024, 3, 31, 12, 0)  # mid-day on the transition day
        start, end, _ = source_range_to_period_and_limit(d, "1d@Europe/Brussels")
        self.assertEqual(start, datetime(2024, 3, 30, 23, 0))  # 03-31 00:00+01
        self.assertEqual(end, datetime(2024, 3, 31, 22, 0))    # 04-01 00:00+02
        self.assertEqual((end - start).total_seconds(), 23 * 3600)

    def test_1d_at_brussels_dst_fall_back_is_25h(self):
        # 2024-10-27: clocks fall 03:00 CEST -> 02:00 CET. Brussels-day is 25 h.
        d = datetime(2024, 10, 27, 12, 0)
        start, end, _ = source_range_to_period_and_limit(d, "1d@Europe/Brussels")
        self.assertEqual(start, datetime(2024, 10, 26, 22, 0))  # 10-27 00:00+02
        self.assertEqual(end, datetime(2024, 10, 27, 23, 0))    # 10-28 00:00+01
        self.assertEqual((end - start).total_seconds(), 25 * 3600)

    def test_1h_at_utc_floors_to_hour(self):
        # @UTC is a degenerate timezone; the floor must zero out minutes/seconds
        # (unlike the legacy path, which doesn't).
        d = datetime(2024, 5, 6, 14, 23, 11)
        start, end, _ = source_range_to_period_and_limit(d, "1h@UTC")
        self.assertEqual(start, datetime(2024, 5, 6, 14, 0))
        self.assertEqual(end, datetime(2024, 5, 6, 15, 0))

    def test_invalid_unit_raises(self):
        with self.assertRaises(ValueError):
            source_range_to_period_and_limit(datetime(2024, 1, 1), "1y@UTC")


if __name__ == "__main__":
    unittest.main()
