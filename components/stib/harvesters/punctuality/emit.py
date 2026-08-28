"""Turning matched journeys into one row per scheduled stop call.

Lifted from the reconstruction's CLI so the harvester and the command-line
build share it rather than drifting apart. `emit_rows` is the former `_emit`.
"""
import numpy as np
import pandas as pd

from . import match, stopcalls


SCHEMA = {
    "trip_id": "large_string",
    "start_date": "large_string",
    "start_time": "large_string",
    "stop_sequence": "int32",
    "stop_id": "large_string",
    "route_id": "large_string",
    "direction_id": "int32",
    "trip_schedule_relationship": "int32",
    "arrival_time": "timestamp[us]",
    "arrival_delay": "int32",
    "departure_time": "timestamp[us]",
    "departure_delay": "int32",
    "stop_schedule_relationship": "int32",
    "cancelled": "bool",
}
# Ours, appended after the shared set so nothing that reads the shared columns
# positionally or by name is disturbed.
EXTRA = ["journey_id", "match_deviation_minutes", "observed", "inferred",
         "missing_reason"]


def emit_rows(calls, schedule, matches, scores, day, merged=None, lost=None):
    """One row per scheduled stop call of every matched trip.

    A merged fragment (see `match.merge_fragments`) is a *second* journey on a
    trip the assignment already found. It fills in times on stop calls that trip
    already has; it never adds a trip and never adds a row, so the before and
    after of merging differ in exactly one number — how many of those rows carry
    an observation. `observed_primary` is that number before merging, and the
    build drops it once it has been counted.
    """
    merged = merged or {}
    by_journey = {trip: journey for journey, trip in matches.items()}
    rows = schedule[schedule.trip_id.isin(by_journey)].copy()

    everything = dict(matches, **merged)
    observed = calls[calls.journey.isin(everything)].copy()
    observed["trip_id"] = observed.journey.map(everything)
    observed["primary"] = observed.journey.isin(matches)
    observed["arrival_s"] = match.service_day_seconds(observed.arrival, day)
    observed["departure_s"] = match.service_day_seconds(observed.departure, day)
    # The assignment's own journey is the trip's first witness; a fragment only
    # fills what it left empty.
    observed = observed.sort_values(["primary", "order"], ascending=[False, True])
    observed = observed.drop_duplicates(["trip_id", "point"])
    seen = observed.set_index(["trip_id", "point"])
    only_primary = observed[observed.primary].set_index(["trip_id", "point"])

    key = pd.MultiIndex.from_arrays([rows.trip_id, rows.point])
    rows["actual_arrival"] = seen.arrival_s.reindex(key).values
    rows["actual_departure"] = seen.departure_s.reindex(key).values
    rows["was_arrival"] = only_primary.arrival_s.reindex(key).values
    rows["was_departure"] = only_primary.departure_s.reindex(key).values

    # Everything above is a crossing the feed actually reported. `observed` is
    # fixed here, before the two ends are extrapolated, so it keeps meaning
    # "measured" and a consumer can drop the inferences with one predicate.
    rows["measured"] = rows.actual_arrival.notna() | rows.actual_departure.notna()

    rows = rows.sort_values(["trip_id", "stop_sequence"])
    chain = (calls.drop_duplicates(["line_id", "direction", "point"])
             .set_index(["line_id", "direction", "point"]).metres)
    rows["edge_metres"] = chain.reindex(pd.MultiIndex.from_arrays([
        rows.route_short_name.astype(str), rows.direction_id.astype(int),
        rows.point])).values
    metres = stopcalls.place_positions(rows)
    arrivals, departures, inferred, edges = stopcalls.extrapolate_edges(rows, metres)
    edges["interior"] = stopcalls.fill_interior(
        rows, arrivals, departures, inferred, metres)
    rows["actual_arrival"], rows["actual_departure"] = arrivals, departures
    rows["inferred"] = inferred
    rows["missing_reason"] = stopcalls.missing_reasons(
        rows, rows.measured.to_numpy(dtype=bool) | inferred, lost or {})

    midnight = pd.Timestamp(day).tz_localize(match.BRUSSELS)

    def stamp(seconds):
        # The published archives hold microseconds. Interpolating between polls
        # lands on nanoseconds, and arrow refuses to drop them silently.
        out = midnight + pd.to_timedelta(seconds, unit="s")
        return out.dt.tz_convert("UTC").dt.tz_localize(None).dt.floor("us")

    starts = schedule.groupby("trip_id").departure_time.min()

    out = pd.DataFrame({
        "trip_id": rows.trip_id.astype(str),
        "start_date": day.strftime("%Y%m%d"),
        "start_time": rows.trip_id.map(starts).map(_clock),
        "stop_sequence": rows.stop_sequence.astype("int32"),
        "stop_id": rows.stop_id.astype(str),
        "route_id": rows.route_id.astype(str),
        "direction_id": rows.direction_id.astype("int32"),
        "trip_schedule_relationship": np.int32(0),
        "arrival_time": stamp(rows.actual_arrival),
        "arrival_delay": rows.actual_arrival - rows.arrival_time,
        "departure_time": stamp(rows.actual_departure),
        "departure_delay": rows.actual_departure - rows.departure_time,
        "stop_schedule_relationship": np.int32(0),
        "cancelled": False,
        "journey_id": rows.trip_id.map(by_journey),
        "match_deviation_minutes": rows.trip_id.map(
            {trip: scores[journey] for journey, trip in matches.items()}),
        "observed": rows.measured,
        "inferred": rows.inferred,
        "missing_reason": rows.missing_reason,
        "observed_primary": rows.was_arrival.notna() | rows.was_departure.notna(),
    })
    for column in ("arrival_delay", "departure_delay"):
        out[column] = out[column].round().astype("Int32")
    return out.sort_values(["trip_id", "stop_sequence"]).reset_index(drop=True), edges


def _clock(seconds):
    if seconds != seconds:
        return None
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


