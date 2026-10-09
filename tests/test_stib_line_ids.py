"""Line ids containing "0" (10, 20, 50...) survive the vehicle_position_geometry preparation."""
import os
import sys
import unittest

import pandas as pd

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FILE_STORAGE_DIRECTORY", "/tmp/storage")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.stib.harvesters.vehicle_position_geometry import (  # noqa: E402
    STIBVehiclePositionGeometryHarvester,
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


if __name__ == "__main__":
    unittest.main()
