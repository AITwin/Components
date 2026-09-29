"""STIB vehicle positions carrying their GTFS trip, one snapshot per poll.

The live counterpart of `stib.vehicle_identify`: the same vehicles, but tracked
by the punctuality pipeline's tracker and paired with the timetabled trip each
one is running (see live.py). The tracker is stateful — a vehicle's identity
and its stop calls are built up poll after poll — so it lives in the harvester
process between runs, and is rebuilt from the recent polls whenever it cannot
simply continue: on the first run, after a restart, after a gap longer than a
track survives, and when a new timetable arrives.
"""
import io
import json
import logging
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import timezone

import pandas as pd

from src.components import Harvester

from ..punctuality import match
from ..punctuality.harvester import _segments
from .live import LiveTracker

logger = logging.getLogger(__name__)

# How much history a rebuilt tracker replays before answering. An hour covers
# the stop calls of nearly every vehicle on the road, which is what pairing it
# with a trip needs; the optional dependency must supply at least this many
# polls (180 at the 20-second cadence).
BOOTSTRAP_SECONDS = 60 * 60

_state = {"tracker": None, "timetable": None}


def _poll(payload) -> pd.DataFrame:
    if isinstance(payload, (bytes, bytearray, str)):
        payload = json.loads(payload)
    frame = pd.DataFrame(
        [{"line_id": str(v.get("lineId")), "direction_id": str(v.get("directionId")),
          "point_id": str(v.get("pointId")), "distance_from_point": v.get("distanceFromPoint")}
         for v in payload or ()],
        columns=["line_id", "direction_id", "point_id", "distance_from_point"],
    )
    # Typed even when empty: the night's empty polls would otherwise turn the
    # distances of a whole bootstrap into objects once concatenated.
    frame["distance_from_point"] = pd.to_numeric(frame.distance_from_point, errors="coerce")
    return frame.dropna(subset=["distance_from_point"]).astype({"distance_from_point": "int64"})


def _epoch(date) -> float:
    # Stored dates are naive UTC.
    return date.replace(tzinfo=timezone.utc).timestamp() if date.tzinfo is None else date.timestamp()


def _tables(blob: bytes) -> dict:
    zf = zipfile.ZipFile(io.BytesIO(blob))
    return {n[:-8]: pd.read_parquet(io.BytesIO(zf.read(n)))
            for n in zf.namelist() if n.endswith(".parquet")}


class STIBVehicleTripHarvester(Harvester):

    def run(self, source, stib_gtfs_parquet, stib_segments=None, stib_vehicle_distance=None,
            stib_vehicle_trip=None):
        now = _epoch(source.date)
        tracker = _state["tracker"]
        stale = (
            tracker is None
            or _state["timetable"] != stib_gtfs_parquet.date
            or tracker.last_ts is None
            or not 0 < now - tracker.last_ts <= match.TRACK_TIMEOUT
        )
        if stale:
            tracker = self._rebuild(now, stib_gtfs_parquet, stib_segments, stib_vehicle_distance or [],
                                    stib_vehicle_trip)
            _state["tracker"], _state["timetable"] = tracker, stib_gtfs_parquet.date

        vehicles = tracker.step(_poll(source.data), now)
        if not vehicles:
            return None
        return {
            "type": "FeatureCollection",
            "features": [_feature(vehicle) for vehicle in vehicles if vehicle["geometry"]],
        }

    @staticmethod
    def _rebuild(now, gtfs_row, segments_row, history_rows, previous=None):
        started = time.time()
        history = sorted(
            (row for row in history_rows if now - BOOTSTRAP_SECONDS <= _epoch(row.date) < now),
            key=lambda row: row.date,
        )
        # Each row's payload is a blob download; fetch them side by side.
        with ThreadPoolExecutor(max_workers=8) as pool:
            polls = list(pool.map(lambda row: _poll(row.data), history))
        stamps = [_epoch(row.date) for row in history]

        observations = pd.concat(
            [poll.assign(ts=pd.Timestamp(stamp, unit="s", tz="UTC"))
             for poll, stamp in zip(polls, stamps)] or [_poll([])],
            ignore_index=True,
        )
        segments = _segments(segments_row.data) if segments_row is not None else None
        tracker = LiveTracker(_tables(gtfs_row.data), segments, observations if len(observations) else None)
        for poll, stamp in zip(polls, stamps):
            tracker.step(poll, stamp, assign=False)
        adopted = 0
        if previous is not None and now - _epoch(previous.date) <= BOOTSTRAP_SECONDS:
            payload = previous.data
            if isinstance(payload, (bytes, bytearray, str)):
                payload = json.loads(payload)
            adopted = tracker.adopt([f["properties"] for f in (payload or {}).get("features", ())],
                                    _epoch(previous.date))
        logger.info("STIB vehicle trips: tracker rebuilt from %d polls in %.1fs, %d identities kept",
                    len(polls), time.time() - started, adopted)
        return tracker


def _feature(vehicle: dict) -> dict:
    lon, lat = vehicle["geometry"]
    properties = {k: v for k, v in vehicle.items() if k != "geometry"}
    return {
        "type": "Feature",
        "id": vehicle["uuid"],
        "properties": properties,
        "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
    }
