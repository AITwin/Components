"""The STIB speed harvesters: the newest snapshot is the source, the earlier
ones arrive through the optional dependency on the same table."""
import os
import sys
import unittest
from datetime import datetime, timedelta

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FILE_STORAGE_DIRECTORY", "/tmp/storage")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.stib.harvesters.speed import StibSegmentsSpeedHarvester  # noqa: E402
from components.stib.harvesters.aggregated_speed import StibSegmentsAggregatedSpeedHarvester  # noqa: E402


class _Row:
    def __init__(self, date, data):
        self.date = date
        self.data = data


T0 = datetime(2026, 9, 19, 9, 0, 0)


def _distance(*metres):
    return [{"pointId": "1", "lineId": "71", "directionId": "A", "distanceFromPoint": m} for m in metres]


class Speed(unittest.TestCase):
    def test_speed_between_consecutive_snapshots(self):
        current = _Row(T0 + timedelta(seconds=20), _distance(300))
        previous = _Row(T0, _distance(100))
        out = StibSegmentsSpeedHarvester().run(current, [previous])
        self.assertEqual(out, [{"pointId": "1", "lineId": "71", "directionId": "A", "speed": 36.0}])

    def test_duplicate_source_snapshot_is_skipped(self):
        # STIB served the same payload twice: measure against the last distinct one.
        current = _Row(T0 + timedelta(seconds=40), _distance(300))
        duplicate = _Row(T0 + timedelta(seconds=20), _distance(300))
        previous = _Row(T0, _distance(100))
        out = StibSegmentsSpeedHarvester().run(current, [duplicate, previous])
        self.assertEqual(out[0]["speed"], 18.0)

    def test_no_distinct_previous_yields_none(self):
        current = _Row(T0, _distance(300))
        self.assertIsNone(StibSegmentsSpeedHarvester().run(current, [_Row(T0 - timedelta(seconds=20), _distance(300))]))
        self.assertIsNone(StibSegmentsSpeedHarvester().run(current, None))


def _speed(v):
    return [{"pointId": "1", "lineId": "71", "directionId": "A", "speed": v}]


class AggregatedSpeed(unittest.TestCase):
    def test_mean_over_ten_minute_window(self):
        current = _Row(T0, _speed(10))
        earlier = [
            _Row(T0 - timedelta(minutes=5), _speed(20)),
            _Row(T0 - timedelta(minutes=9), _speed(30)),
            _Row(T0 - timedelta(minutes=11), _speed(1000)),  # outside the window
        ]
        out = StibSegmentsAggregatedSpeedHarvester().run(current, earlier)
        self.assertEqual(out, [{"pointId": "1", "lineId": "71", "directionId": "A", "speed": 20.0}])

    def test_empty_snapshots_are_ignored(self):
        out = StibSegmentsAggregatedSpeedHarvester().run(_Row(T0, []), [_Row(T0 - timedelta(minutes=1), _speed(12))])
        self.assertEqual(out[0]["speed"], 12.0)
        self.assertEqual(StibSegmentsAggregatedSpeedHarvester().run(_Row(T0, []), None), [])


if __name__ == "__main__":
    unittest.main()
