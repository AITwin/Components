"""The Infrabel punctuality collector only stores yesterday's departures."""
import os
import sys
import unittest
from datetime import datetime, timezone
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FILE_STORAGE_DIRECTORY", "/tmp/storage")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.train.infrabel.collectors import punctuality  # noqa: E402


def _collect(days):
    response = mock.Mock()
    response.json.return_value = [{"datdep": day, "delay_arr": 0} for day in days]
    with mock.patch.object(punctuality.requests, "get", return_value=response), \
            mock.patch.object(punctuality, "expected_day", return_value="2026-09-30"):
        return punctuality.InfrabelPunctualityCollector().run()


class InfrabelPunctuality(unittest.TestCase):
    def test_yesterday_is_the_brussels_day_before(self):
        # 23:30 UTC on the 30th is already the 1st in Brussels
        self.assertEqual(punctuality.expected_day(datetime(2026, 9, 30, 23, 30, tzinfo=timezone.utc)), "2026-09-30")
        self.assertEqual(punctuality.expected_day(datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc)), "2026-09-30")

    def test_yesterdays_file_is_stored(self):
        self.assertEqual(len(_collect(["2026-09-30", "2026-09-30"])), 2)

    def test_a_file_not_yet_replaced_is_refused(self):
        with self.assertRaises(ValueError):
            _collect(["2026-09-29"])

    def test_an_empty_file_is_refused(self):
        with self.assertRaises(ValueError):
            _collect([])


if __name__ == "__main__":
    unittest.main()
