import io
import logging
import zipfile
from datetime import timezone
from zoneinfo import ZoneInfo

import pandas as pd
import polars as pl
from google.transit import gtfs_realtime_pb2

from src.components import Harvester

logger = logging.getLogger(__name__)

BRUSSELS = ZoneInfo("Europe/Brussels")

_CANCELED = gtfs_realtime_pb2.TripDescriptor.CANCELED
_SKIPPED = gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.SKIPPED
_NO_DATA = gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.NO_DATA

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
            times = [
                arr.time if has_arr and arr.time else None,
                arr.delay if has_arr and arr.HasField("delay") else None,
                dep.time if has_dep and dep.time else None,
                dep.delay if has_dep and dep.HasField("delay") else None,
            ]
            stop_rel = stu.schedule_relationship
            # Operators stop predicting a stop once the vehicle has passed it and
            # re-publish it empty (TEC: NO_DATA at the origin after departure).
            # The latest snapshot winning outright erased the last real value, so
            # an empty field keeps what an earlier snapshot recorded, and a later
            # NO_DATA does not demote a stop that had data.
            if prior is not None:
                times = [new if new is not None else old
                         for new, old in zip(times, prior[3:7])]
                if stop_rel == _NO_DATA and any(v is not None for v in prior[3:7]):
                    stop_rel = prior[7]
            acc[key] = (
                trip.route_id,
                direction_id,
                trip.schedule_relationship,
                *times,
                stop_rel,
                ts,
            )
            seen += 1
    return seen


def _service_day(source) -> str:
    """YYYYMMDD of the Brussels day the source range covers (its first snapshot;
    stored dates are naive UTC)."""
    first = min(snapshot.date for snapshot in source)
    if first.tzinfo is None:
        first = first.replace(tzinfo=timezone.utc)
    return first.astimezone(BRUSSELS).strftime("%Y%m%d")


def _variants(trip_id: str):
    """The forms a trip id takes across an operator's feeds, most specific first:
    as is, without the `gt:<agency>:` prefix the published GTFS adds (De Lijn,
    SNCB), without the last `:` component, and without the validity date
    (YYYYMMDD) and what follows it: SNCB's realtime feed and timetable fill that
    date differently, and the timetable appends a `:<n>` to most trips
    (`...:1054:20261004:1` against the feed's `...:1054:20271210`)."""
    yield trip_id
    bare = trip_id.split(":", 2)[2] if trip_id.startswith("gt:") and trip_id.count(":") >= 2 else trip_id
    if bare != trip_id:
        yield bare
    if ":" in bare:
        yield bare.rsplit(":", 1)[0]
    parts = bare.split(":")
    dated = next((i for i in range(len(parts) - 1, 0, -1)
                  if len(parts[i]) == 8 and parts[i].isdigit()), None)
    if dated is not None and dated < len(parts) - 1:
        yield ":".join(parts[:dated])


class _Trips:
    """route_id and direction_id of the timetable's trips, under every variant
    of their id; a variant two trips share with different values is dropped."""

    def __init__(self, gtfs_zip: bytes):
        with zipfile.ZipFile(io.BytesIO(gtfs_zip)) as zf:
            trips = pd.read_parquet(io.BytesIO(zf.read("trips.parquet")))
        direction = trips["direction_id"] if "direction_id" in trips else pd.Series(None, index=trips.index)
        self.lookup = {}
        clash = set()
        for trip_id, route_id, direction_id in zip(trips.trip_id.astype(str), trips.route_id, direction):
            value = (None if pd.isna(route_id) or route_id == "" else str(route_id),
                     None if pd.isna(direction_id) or direction_id == "" else int(direction_id))
            for key in _variants(trip_id):
                if self.lookup.setdefault(key, value) != value:
                    clash.add(key)
        for key in clash:
            del self.lookup[key]

    def get(self, trip_id):
        for key in _variants(trip_id):
            if key in self.lookup:
                return self.lookup[key]
        return None, None


_trips_cache = {"key": None, "trips": None}


def _timetable(dependencies):
    """The operator's timetable among the optional dependencies, if declared."""
    name, row = next(((k, v) for k, v in dependencies.items()
                      if k.endswith("gtfs_parquet") and v is not None), (None, None))
    if row is None:
        return None
    if _trips_cache["key"] != (name, row.date):
        _trips_cache.update(key=(name, row.date), trips=_Trips(row.data))
    return _trips_cache["trips"]


class PunctualityHarvester(Harvester):
    """Build a daily punctuality parquet from GTFS-RT trip-update snapshots.

    Snapshots stream through one at a time, folding into a dict keyed by
    (trip_id, start_date, start_time, stop_sequence, stop_id); chronological
    order means the latest update wins. The accumulator is drained directly
    into columnar lists, so the dict and the column storage never coexist at
    full size.

    Cancelled trips that arrive with no stop_time_update entries are kept as
    a single synthetic row per trip-instance with null stop fields.

    With the operator's `gtfs_parquet` as an optional dependency, route_id and
    direction_id the feed leaves out are filled from the timetable (De Lijn and
    SNCB send neither; SNCB's timetable has no direction either).
    """

    def run(self, source, **dependencies):
        if not source:
            return None
        timetable = _timetable(dependencies)

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

        # Operators announce cancellations days ahead (De Lijn up to three), and
        # those trips would be filed under every day that saw the announcement.
        # A day keeps the trips that started on it or before it (overnight runs).
        day = _service_day(source)
        future = [k for k in acc if k[1] and k[1] > day]
        for k in future:
            del acc[k]

        if not acc:
            return None

        logger.info("Punctuality: %d snapshots, %d rows from %d updates, %d future rows dropped",
                    snapshots, len(acc), updates, len(future))

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
            # Protobuf reads an absent field as "": a feed that never sends it
            # (De Lijn start_time) gets null, not an empty string.
            cols["start_date"][i] = start_date or None
            cols["start_time"][i] = start_time or None
            cols["stop_sequence"][i] = stop_sequence
            cols["stop_id"][i] = stop_id
            if timetable is not None and (not route_id or direction_id is None):
                known_route, known_direction = timetable.get(trip_id)
                route_id = route_id or known_route
                direction_id = direction_id if direction_id is not None else known_direction
            cols["route_id"][i] = route_id or None
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
