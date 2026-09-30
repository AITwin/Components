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


def _polls(*metres, every=20):
    """Snapshots of one vehicle's distance every `every` seconds, newest first
    (None: only another vehicle is reported)."""
    elsewhere = [{"pointId": "9", "lineId": "71", "directionId": "A", "distanceFromPoint": 0}]
    rows = [_Row(T0 + timedelta(seconds=every * i), _distance(m) if m is not None else elsewhere)
            for i, m in enumerate(metres)]
    return rows[-1], list(reversed(rows[:-1]))


class Speed(unittest.TestCase):
    def test_move_timed_from_when_each_distance_first_appeared(self):
        # STIB refreshed the distance every 40 s: 100 stood for two polls, then 300.
        # The 200 m took 40 s (18 km/h), not the 20 s between the last two polls.
        current, earlier = _polls(None, 100, 100, 300)
        out = StibSegmentsSpeedHarvester().run(current, earlier)
        self.assertEqual(out, [{"pointId": "1", "lineId": "71", "directionId": "A", "speed": 18.0}])

    def test_consecutive_changes_are_timed_by_the_poll_interval(self):
        current, earlier = _polls(None, 100, 300)
        self.assertEqual(StibSegmentsSpeedHarvester().run(current, earlier)[0]["speed"], 36.0)

    def test_a_repeated_payload_repeats_the_last_move(self):
        current, earlier = _polls(None, 100, 100, 300, 300)
        self.assertEqual(StibSegmentsSpeedHarvester().run(current, earlier)[0]["speed"], 18.0)

    def test_a_value_whose_start_is_out_of_sight_is_not_measured(self):
        current, earlier = _polls(100, 300)
        self.assertEqual(StibSegmentsSpeedHarvester().run(current, earlier), [])

    def test_a_long_standstill_is_not_averaged_into_a_speed(self):
        current, earlier = _polls(None, 100, 100, 100, 100, 100, 300)
        self.assertEqual(StibSegmentsSpeedHarvester().run(current, earlier), [])

    def test_implausible_speed_is_dropped(self):
        current, earlier = _polls(None, 0, 800)        # 800 m in 20 s = 144 km/h
        self.assertEqual(StibSegmentsSpeedHarvester().run(current, earlier), [])

    def test_two_vehicles_on_one_key_are_not_paired(self):
        current, earlier = _polls(None, 100, 300)
        current.data = current.data + _distance(50)
        self.assertEqual(StibSegmentsSpeedHarvester().run(current, earlier), [])

    def test_no_earlier_snapshot_yields_none(self):
        self.assertIsNone(StibSegmentsSpeedHarvester().run(_Row(T0, _distance(300)), None))


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
