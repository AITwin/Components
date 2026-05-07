import io
import logging

import polars as pl
from google.transit import gtfs_realtime_pb2

from src.components import Harvester

logger = logging.getLogger(__name__)

_CANCELED = gtfs_realtime_pb2.TripDescriptor.CANCELED
_SKIPPED = gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.SKIPPED

_SCHEMA = {
    "trip_id": pl.Utf8,
    "start_date": pl.Utf8,
    "start_time": pl.Utf8,
    "stop_sequence": pl.Int32,
    "stop_id": pl.Utf8,
    "route_id": pl.Utf8,
    "direction_id": pl.Int32,
    "trip_schedule_relationship": pl.Int32,
    "arrival_time": pl.Int64,
    "arrival_delay": pl.Int32,
    "departure_time": pl.Int64,
    "departure_delay": pl.Int32,
    "stop_schedule_relationship": pl.Int32,
    "cancelled": pl.Boolean,
}


def _ingest(feed_bytes: bytes, fallback_ts: int, acc: dict) -> int:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(feed_bytes)
    feed_ts = feed.header.timestamp or fallback_ts
    seen = 0
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        tu = entity.trip_update
        trip = tu.trip
        ts = tu.timestamp or feed_ts
        direction_id = trip.direction_id if trip.HasField("direction_id") else None

        # Cancelled trips are typically published with no stop_time_update entries;
        # emit one synthetic trip-only row so the cancellation isn't dropped.
        if trip.schedule_relationship == _CANCELED and len(tu.stop_time_update) == 0:
            key = (trip.trip_id, trip.start_date, trip.start_time, None, None)
            prior = acc.get(key)
            if prior is None or prior[-1] < ts:
                acc[key] = (trip.route_id, direction_id, _CANCELED,
                            None, None, None, None, 0, ts)
                seen += 1
            continue

        for stu in tu.stop_time_update:
            seq = stu.stop_sequence if stu.HasField("stop_sequence") else None
            key = (trip.trip_id, trip.start_date, trip.start_time, seq, stu.stop_id)
            prior = acc.get(key)
            if prior is not None and prior[-1] >= ts:
                continue
            has_arr = stu.HasField("arrival")
            has_dep = stu.HasField("departure")
            arr = stu.arrival
            dep = stu.departure
            acc[key] = (
                trip.route_id,
                direction_id,
                trip.schedule_relationship,
                arr.time if has_arr and arr.time else None,
                arr.delay if has_arr and arr.HasField("delay") else None,
                dep.time if has_dep and dep.time else None,
                dep.delay if has_dep and dep.HasField("delay") else None,
                stu.schedule_relationship,
                ts,
            )
            seen += 1
    return seen


class PunctualityHarvester(Harvester):
    """Build a daily punctuality parquet from GTFS-RT trip-update snapshots.

    Snapshots stream through one at a time, folding into a dict keyed by
    (trip_id, start_date, start_time, stop_sequence, stop_id); chronological
    order means the latest update wins. The accumulator is drained directly
    into columnar lists, so the dict and the column storage never coexist at
    full size.

    Cancelled trips that arrive with no stop_time_update entries are kept as
    a single synthetic row per trip-instance with null stop fields.
    """

    def run(self, source):
        if not source:
            return None

        acc = {}
        snapshots = updates = 0
        for snapshot in source:
            try:
                feed_bytes = snapshot.data
                if not feed_bytes:
                    continue
                updates += _ingest(feed_bytes, int(snapshot.date.timestamp()), acc)
                snapshots += 1
            except Exception as exc:
                logger.warning("Failed snapshot %s: %s", snapshot.date, exc)

        if not acc:
            return None

        logger.info("Punctuality: %d snapshots, %d rows from %d updates",
                    snapshots, len(acc), updates)

        cols = {name: [None] * len(acc) for name in _SCHEMA}
        i = 0
        while acc:
            k, v = acc.popitem()
            (trip_id, start_date, start_time, stop_sequence, stop_id) = k
            (route_id, direction_id, trip_schedule_relationship,
             arrival_time, arrival_delay,
             departure_time, departure_delay,
             stop_schedule_relationship, _ts) = v
            cols["trip_id"][i] = trip_id
            cols["start_date"][i] = start_date
            cols["start_time"][i] = start_time
            cols["stop_sequence"][i] = stop_sequence
            cols["stop_id"][i] = stop_id
            cols["route_id"][i] = route_id
            cols["direction_id"][i] = direction_id
            cols["trip_schedule_relationship"][i] = trip_schedule_relationship
            cols["arrival_time"][i] = arrival_time
            cols["arrival_delay"][i] = arrival_delay
            cols["departure_time"][i] = departure_time
            cols["departure_delay"][i] = departure_delay
            cols["stop_schedule_relationship"][i] = stop_schedule_relationship
            cols["cancelled"][i] = (trip_schedule_relationship == _CANCELED
                                    or stop_schedule_relationship == _SKIPPED)
            i += 1

        df = pl.DataFrame(cols, schema=_SCHEMA).with_columns(
            pl.from_epoch(c, time_unit="s").alias(c)
            for c, t in _SCHEMA.items() if t == pl.Int64
        ).sort(["trip_id", "start_date", "start_time", "stop_sequence", "stop_id"])

        buf = io.BytesIO()
        df.write_parquet(buf, compression="zstd")
        return buf.getvalue()
