"""Line ids containing "0" (10, 20, 50...) survive the vehicle_position_geometry preparation."""
import os
import sys
import unittest

import pandas as pd

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FILE_STORAGE_DIRECTORY", "/tmp/storage")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from components.stib.harvesters.vehicle_position_geometry import (  # noqa: E402
    STIBVehiclePositionGeometryHarvester,
    _SegmentCache,
)


class LineIds(unittest.TestCase):
    def test_lines_with_a_zero_are_kept(self):
        ids = ["10", "20", "50", "60", "80", "100", "N10", "3.0", "T39", "71"]
        frame = pd.DataFrame({
            "lineId": ids,
            "pointId": ["1234"] * len(ids),
            "directionId": ["5678"] * len(ids),
            "distanceFromPoint": [0] * len(ids),
        })
        out = STIBVehiclePositionGeometryHarvester.prepare_realtime_dataframe(frame)
        self.assertEqual(list(out["line_id"]), ["10", "20", "50", "60", "80", "100", "N10", "3", "39", "71"])


class SegmentCache(unittest.TestCase):
    @staticmethod
    def _segments(date, x):
        return SimpleNamespace(date=date, data={"type": "FeatureCollection", "features": [{
            "type": "Feature",
            "properties": {"start": "1", "end": "2", "line_id": "10", "direction": "V"},
            "geometry": {"type": "LineString", "coordinates": [[x, 50.8], [x, 50.9]]},
        }]})

    def test_a_new_segments_snapshot_replaces_the_cached_one(self):
        first = _SegmentCache(self._segments(datetime(2026, 10, 8), 4.3)).get_segment(1, "10", "V")
        same = _SegmentCache(self._segments(datetime(2026, 10, 8), 9.9)).get_segment(1, "10", "V")
        new = _SegmentCache(self._segments(datetime(2026, 10, 9), 4.4)).get_segment(1, "10", "V")
        self.assertEqual((first.coords[0][0], same.coords[0][0], new.coords[0][0]), (4.3, 4.3, 4.4))


if __name__ == "__main__":
    unittest.main()
