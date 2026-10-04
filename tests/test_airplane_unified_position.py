"""The unified airplane positions leave out a feed that stopped."""
import os
import sys
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FILE_STORAGE_DIRECTORY", "/tmp/storage")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.airplane.harvesters.unified_position import AirplaneUnifiedPositionHarvester  # noqa: E402

NOW = datetime(2026, 10, 1, 16, 20)


def _row(date, *icao24s):
    features = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [4.5, 50.8]},
                 "properties": {"icao24": icao, "callsign": icao.upper()}} for icao in icao24s]
    return SimpleNamespace(date=date, data={"type": "FeatureCollection", "features": features})


def _sources(source, live):
    out = AirplaneUnifiedPositionHarvester().run(source, live)
    return {f["properties"]["icao24"]: f["properties"]["sources"] for f in out["features"]}


class UnifiedPosition(unittest.TestCase):
    def test_a_current_feed_is_merged(self):
        self.assertEqual(_sources(_row(NOW, "a", "b"), _row(NOW - timedelta(minutes=1), "b", "c")),
                         {"a": ["opensky"], "b": ["adsb.lol", "opensky"], "c": ["adsb.lol"]})

    def test_no_second_feed_yet(self):
        self.assertEqual(_sources(_row(NOW, "a"), None), {"a": ["opensky"]})

    def test_a_stopped_feed_is_left_out(self):
        self.assertEqual(_sources(_row(NOW, "a"), _row(NOW - timedelta(days=49), "b")), {"a": ["opensky"]})


if __name__ == "__main__":
    unittest.main()
