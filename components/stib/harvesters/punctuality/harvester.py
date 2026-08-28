"""STIB punctuality: a GTFS-RT-shaped archive for a feed that has no GTFS-RT.

SNCB, TEC and De Lijn publish trip updates, so their punctuality tables are a
fold over a day of those updates. STIB publishes no such feed and no vehicle
identity at all: `vehicle_distance` is an anonymous set of positions every 20
seconds, each a line, a direction, the stop point last passed and the metres
since. Producing the same table therefore means recovering, in order, which
observations belong to one vehicle, which stops it called at, and which
timetabled trip it was running.

Three stages, two of them order-preserving alignments that rest on one physical
fact — vehicles on a line do not overtake each other:

  tracking      consecutive polls are aligned inside (line, direction,
                destination), so a poll's positions attach to the tracks they
                continue rather than to whichever is nearest;
  stop calls    a call is read where a track's distance along the line crosses a
                stop, with dwell taken from a standstill rather than a midpoint;
  trip ids      the day's journeys and the day's trips, both in time order, are
                aligned once per (line, direction) against the median difference
                between observed and scheduled times.

Where a journey breaks, the fragments are merged back onto the trip they came
from when that is unambiguous, and the calls a trip can never have been seen at
— its first and its last, which have no crossing to read — are dated by
extrapolating the running speed of the adjacent hop.

Two columns cannot be honest here and are documented rather than guessed:
`cancelled` and `trip_schedule_relationship` are always false and 0, because the
feed carries no cancellation signal and an unmatched trip is equally evidence
that the tracker lost the vehicle. `observed` marks a measured time and
`inferred` a derived one; they are mutually exclusive, and a consumer that wants
only measurement filters on `observed`.
"""
import io
import json
import logging
import math
import zipfile

import pandas as pd

from src.components import Harvester

from . import match, network, stopcalls
from .emit import EXTRA, emit_rows

logger = logging.getLogger(__name__)

# A Brussels service day runs past midnight; night buses belong to the day they
# started. The source range hands over a calendar day, so the trailing hours are
# what the timetable calls 24:00 onwards.
BRUSSELS = "Europe/Brussels"


def _observations(source) -> pd.DataFrame:
    """A day of polls flattened into one row per vehicle sighting.

    Each snapshot is the whole fleet at one instant, so the frame is built once
    from lists rather than by concatenating a frame per poll — a day is roughly
    two million rows across four thousand polls.
    """
    ts, line, direction, point, distance = [], [], [], [], []
    for snapshot in source:
        payload = snapshot.data
        if not payload:
            continue
        if isinstance(payload, (bytes, bytearray, str)):
            payload = json.loads(payload)
        # Stored timestamps are naive UTC; a caller may hand over an aware one.
        stamp = pd.Timestamp(snapshot.date)
        stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None \
            else stamp.tz_convert("UTC")
        for v in payload:
            ts.append(stamp)
            line.append(str(v["lineId"]))
            direction.append(str(v["directionId"]))
            point.append(str(v["pointId"]))
            distance.append(v["distanceFromPoint"])
    return pd.DataFrame({
        "ts": ts, "line_id": line, "direction_id": direction,
        "point_id": point, "distance_from_point": distance,
    })


def _polyline_m(line) -> float:
    """Length of a lon/lat polyline in metres, flat-earth over Brussels."""
    scale = math.cos(math.radians(50.85)) * 111320.0
    return sum(math.hypot((x1 - x0) * scale, (y1 - y0) * 111320.0)
               for (x0, y0), (x1, y1) in zip(line, line[1:]))


def _segments(payload) -> pd.DataFrame:
    """`/stib/segments` GeoJSON as the frame the network builder expects.

    Only the hop length is taken from here, and only where the feed itself has
    not observed one often enough; a day the endpoint cannot answer for is not
    fatal, so a missing or malformed payload becomes an empty frame rather than
    an exception.
    """
    if isinstance(payload, (bytes, bytearray, str)):
        payload = json.loads(payload)
    features = (payload or {}).get("features") or []
    rows = []
    for feature in features:
        line = (feature.get("geometry") or {}).get("coordinates") or []
        if len(line) < 2:
            continue
        rows.append(dict(feature.get("properties") or {},
                         length_m=_polyline_m(line),
                         geometry=json.dumps(line)))
    return pd.DataFrame(rows)


def _tables(blob: bytes) -> dict:
    """The GTFS parquet bundle as {table name: DataFrame}."""
    zf = zipfile.ZipFile(io.BytesIO(blob))
    return {n[:-8]: pd.read_parquet(io.BytesIO(zf.read(n)))
            for n in zf.namelist() if n.endswith(".parquet")}


class STIBPunctualityHarvester(Harvester):
    """One Brussels day of reconstructed STIB stop calls, as parquet."""

    def run(self, source, stib_gtfs_parquet, stib_segments=None):
        if not source:
            return None

        observations = _observations(source)
        if observations.empty:
            logger.warning("No vehicle-distance observations in the period")
            return None

        # The service date is the day the polls start on, read in Brussels time
        # so a run beginning at 23:50 is not filed under the next day.
        day = observations.ts.dt.tz_convert(BRUSSELS).min().date()
        polls = observations.ts.nunique()

        gtfs = _tables(stib_gtfs_parquet.data)
        segments = _segments(stib_segments.data if stib_segments else None)

        lines = network.LineNetwork.from_gtfs(gtfs, segments, observations)
        located = lines.locate(observations)
        if located.empty:
            logger.warning("No observation could be placed on a line for %s", day)
            return None

        coarse = stopcalls.coarse_lines(located)
        journeys = match.track_journeys(located, coarse=coarse)
        calls = stopcalls.all_calls(journeys)

        schedule = match.timetable(gtfs, day)
        matches, scores = match.assign_trips(calls, schedule, day)
        merged, report, lost = match.merge_fragments(calls, schedule, matches, day)

        frame, edges = emit_rows(calls, schedule, matches, scores, day, merged, lost)
        frame = frame.drop(columns=["observed_primary"], errors="ignore")

        logger.info(
            "STIB punctuality %s: %d polls, %d observations, %.1f%% placed, "
            "%d journeys, %d/%d trips matched, %d fragments merged, "
            "%d rows (%.1f%% measured, %.1f%% inferred)",
            day, polls, len(observations), 100 * len(located) / len(observations),
            calls.journey.nunique(), len(matches), schedule.trip_id.nunique(),
            report["merged"], len(frame),
            100 * frame.observed.mean(), 100 * frame.inferred.mean(),
        )

        buf = io.BytesIO()
        frame.to_parquet(buf, compression="zstd", index=False)
        return buf.getvalue()
