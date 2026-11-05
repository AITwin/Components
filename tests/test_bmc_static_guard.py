"""BMC static collectors refuse an empty or partial answer instead of storing it."""
import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FILE_STORAGE_DIRECTORY", "/tmp/storage")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.stib.collectors.stop_details import STIBStopDetailsCollector  # noqa: E402
from components.stib.collectors.stops_by_line import STIBStopsByLineCollector  # noqa: E402
from src.utilities import bmc  # noqa: E402


def _answer(n):
    response = mock.Mock()
    response.json.return_value = {"total_count": n, "results": [{"id": i} for i in range(n)]}
    return response


class StaticGuard(unittest.TestCase):
    def test_empty_answer_is_refused(self):
        for collector in (STIBStopsByLineCollector, STIBStopDetailsCollector):
            with mock.patch.object(bmc, "bmc_request", return_value=_answer(0)):
                with self.assertRaises(ValueError):
                    collector().run()

    def test_partial_stops_by_line_is_refused(self):
        # 2026-11-03: 49 of 74 lines, about 98 rows
        with mock.patch.object(bmc, "bmc_request", return_value=_answer(98)):
            with self.assertRaises(ValueError):
                STIBStopsByLineCollector().run()

    def test_full_answer_is_kept(self):
        with mock.patch.object(bmc, "bmc_request", return_value=_answer(148)):
            self.assertEqual(len(STIBStopsByLineCollector().run()["results"]), 148)

    def test_no_floor_by_default(self):
        with mock.patch.object(bmc, "bmc_request", return_value=_answer(0)):
            self.assertEqual(bmc.bmc_request_all("/x"), [])


if __name__ == "__main__":
    unittest.main()
