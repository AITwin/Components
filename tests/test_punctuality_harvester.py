"""The GTFS-RT punctuality harvester folding snapshots into one row per stop.

Each case replays a short sequence of hand-built trip-update snapshots, the way
the collector stores them every 20 s, and reads the parquet the harvester emits.
The first case is the defect that motivated the merge rule: TEC publishes a
delay at a trip's origin, then re-publishes that stop as NO_DATA once the bus has
left, and "latest snapshot wins" erased the only real value.
"""
import io
import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

import polars as pl
from google.transit import gtfs_realtime_pb2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.punctuality_harvester import PunctualityHarvester  # noqa: E402

STU = gtfs_realtime_pb2.TripUpdate.StopTimeUpdate
T0 = 1_788_000_000


def snapshot(ts, stops, trip_rel=gtfs_realtime_pb2.TripDescriptor.SCHEDULED):
    """stops: (stop_sequence, stop_id, departure_delay or None, stop relationship)."""
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = ts
    tu = feed.entity.add(id="e1").trip_update
    tu.trip.trip_id, tu.trip.start_date, tu.trip.start_time = "T1", "20260910", "08:00:00"
    tu.trip.schedule_relationship = trip_rel
    tu.timestamp = ts
    for seq, stop_id, delay, rel in stops:
        stu = tu.stop_time_update.add(stop_sequence=seq, stop_id=stop_id, schedule_relationship=rel)
        if delay is not None:
            stu.departure.delay = delay
            stu.departure.time = T0 + delay
    return SimpleNamespace(data=feed.SerializeToString(),
                           date=datetime.fromtimestamp(ts, tz=timezone.utc))


def run(snaps):
    return pl.read_parquet(io.BytesIO(PunctualityHarvester().run(snaps))).sort("stop_sequence")


def test_later_no_data_keeps_the_last_real_delay():
    df = run([
        snapshot(T0, [(1, "A", 240, STU.SCHEDULED), (2, "B", 240, STU.SCHEDULED)]),
        snapshot(T0 + 20, [(1, "A", None, STU.NO_DATA), (2, "B", 300, STU.SCHEDULED)]),
    ])
    origin, nxt = df.row(0, named=True), df.row(1, named=True)
    assert origin["departure_delay"] == 240
    assert origin["stop_schedule_relationship"] == STU.SCHEDULED
    assert nxt["departure_delay"] == 300          # a newer real value still wins


def test_a_stop_never_predicted_stays_empty():
    df = run([
        snapshot(T0, [(1, "A", None, STU.NO_DATA)]),
        snapshot(T0 + 20, [(1, "A", None, STU.NO_DATA)]),
    ])
    row = df.row(0, named=True)
    assert row["departure_delay"] is None
    assert row["stop_schedule_relationship"] == STU.NO_DATA


def test_skip_and_cancellation_still_follow_the_latest_snapshot():
    df = run([
        snapshot(T0, [(1, "A", 60, STU.SCHEDULED)]),
        snapshot(T0 + 20, [(1, "A", None, STU.SKIPPED)],
                 trip_rel=gtfs_realtime_pb2.TripDescriptor.CANCELED),
    ])
    row = df.row(0, named=True)
    assert row["stop_schedule_relationship"] == STU.SKIPPED
    assert row["trip_schedule_relationship"] == gtfs_realtime_pb2.TripDescriptor.CANCELED
    assert row["cancelled"]


def test_older_snapshot_arriving_late_does_not_overwrite():
    df = run([
        snapshot(T0 + 20, [(1, "A", 120, STU.SCHEDULED)]),
        snapshot(T0, [(1, "A", 999, STU.SCHEDULED)]),
    ])
    assert df.row(0, named=True)["departure_delay"] == 120
