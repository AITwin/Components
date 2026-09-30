"""route_id and direction_id filled from the timetable when the feed omits them."""
import io
import os
import sys
import unittest
import zipfile
from datetime import datetime
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FILE_STORAGE_DIRECTORY", "/tmp/storage")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402
from google.transit import gtfs_realtime_pb2  # noqa: E402

from components.punctuality_harvester import PunctualityHarvester, _Trips, _variants  # noqa: E402


def _gtfs_zip(trips):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        buf = io.BytesIO(); pd.DataFrame(trips).to_parquet(buf, index=False)
        zf.writestr("trips.parquet", buf.getvalue())
    return out.getvalue()


def _feed(trips):
    feed = gtfs_realtime_pb2.FeedMessage(); feed.header.gtfs_realtime_version = "2.0"; feed.header.timestamp = 1
    for trip_id, route_id in trips:
        e = feed.entity.add(); e.id = trip_id
        e.trip_update.trip.trip_id = trip_id
        if route_id:
            e.trip_update.trip.route_id = route_id
        s = e.trip_update.stop_time_update.add(); s.stop_id = "S1"; s.arrival.delay = 60
    return feed.SerializeToString()


class Variants(unittest.TestCase):
    def test_prefix_and_validity_suffix(self):
        self.assertEqual(list(_variants("gt:nmbssncb:88:007::1:2:3:1644:20260216")),
                         ["gt:nmbssncb:88:007::1:2:3:1644:20260216", "88:007::1:2:3:1644:20260216", "88:007::1:2:3:1644"])

    def test_an_ambiguous_variant_is_dropped(self):
        trips = _Trips(_gtfs_zip([{"trip_id": "gt:x:A:1", "route_id": "R1", "direction_id": 0},
                                  {"trip_id": "gt:x:A:2", "route_id": "R2", "direction_id": 0}]))
        self.assertEqual(trips.get("A:9"), (None, None))
        self.assertEqual(trips.get("A:1"), ("R1", 0))


class Enrichment(unittest.TestCase):
    def _run(self, trips, feed_trips):
        now = datetime(2026, 9, 30, 8)
        row = SimpleNamespace(date=now, data=_feed(feed_trips))
        gtfs = SimpleNamespace(date=now, data=_gtfs_zip(trips))
        return pd.read_parquet(io.BytesIO(PunctualityHarvester().run([row], de_lijn_gtfs_parquet=gtfs))).set_index("trip_id")

    def test_filled_from_the_timetable(self):
        out = self._run([{"trip_id": "gt:delijn:T1", "route_id": "gr:delijn:7", "direction_id": 1}], [("T1", "")])
        self.assertEqual((out.loc["T1", "route_id"], out.loc["T1", "direction_id"]), ("gr:delijn:7", 1))

    def test_what_the_feed_says_is_kept(self):
        out = self._run([{"trip_id": "gt:delijn:T1", "route_id": "gr:delijn:7", "direction_id": 1}], [("T1", "FEED")])
        self.assertEqual(out.loc["T1", "route_id"], "FEED")

    def test_without_the_dependency_nothing_changes(self):
        now = datetime(2026, 9, 30, 8)
        out = pd.read_parquet(io.BytesIO(PunctualityHarvester().run([SimpleNamespace(date=now, data=_feed([("T1", "")]))])))
        self.assertTrue(out.direction_id.isna().all())


if __name__ == "__main__":
    unittest.main()
