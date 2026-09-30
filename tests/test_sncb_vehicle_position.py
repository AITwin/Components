"""SNCB positions: the timetable read on Brussels time, and Infrabel segments
whichever way their geometry runs."""
import os
import sys
import unittest
from datetime import datetime

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FILE_STORAGE_DIRECTORY", "/tmp/storage")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shapely.geometry import LineString  # noqa: E402

from components.train.sncb.harvesters.vehicle_position_geometry import _position, _service_clock  # noqa: E402


class Clock(unittest.TestCase):
    def test_summer_poll_reads_the_timetable_two_hours_later(self):
        day, seconds = _service_clock(datetime(2026, 9, 30, 5, 14))      # 07:14 in Brussels
        self.assertEqual(str(day), "2026-09-30")
        self.assertEqual(seconds, 7 * 3600 + 14 * 60)

    def test_winter_poll_one_hour(self):
        self.assertEqual(_service_clock(datetime(2026, 12, 1, 5, 14))[1], 6 * 3600 + 14 * 60)

    def test_after_local_midnight_is_the_next_service_day(self):
        day, seconds = _service_clock(datetime(2026, 9, 29, 22, 30))     # 00:30 on the 30th
        self.assertEqual((str(day), seconds), ("2026-09-30", 30 * 60))


class Orientation(unittest.TestCase):
    def _row(self, line):
        return {"geometry": line, "percentage": 0.25, "stop_lon_start": 4.0, "stop_lat_start": 50.0}

    def test_measured_from_the_departure_station_either_way(self):
        forward = LineString([(4.0, 50.0), (5.0, 50.0)])
        backward = LineString([(5.0, 50.0), (4.0, 50.0)])
        self.assertAlmostEqual(_position(self._row(forward)).x, 4.25)
        self.assertAlmostEqual(_position(self._row(backward)).x, 4.25)


if __name__ == "__main__":
    unittest.main()
