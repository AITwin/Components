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
    # The line as passengers and the timetable name it, not the GTFS route_id:
    # STIB renumbers route_id in every snapshot, so id 60 is line 69 in August,
    # 66 in October and 71 in December. Writing it here would make the column
    # meaningless the moment two days are compared.
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
EXTRA = ["route_gtfs_id", "journey_id", "match_deviation_minutes", "observed", "inferred",
         "missing_reason", "dwell_share"]


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
        "route_id": rows.route_short_name.astype(str),
        "direction_id": rows.direction_id.astype("int32"),
        "trip_schedule_relationship": np.int32(0),
        "arrival_time": stamp(rows.actual_arrival),
        "arrival_delay": rows.actual_arrival - rows.arrival_time,
        "departure_time": stamp(rows.actual_departure),
        "departure_delay": rows.actual_departure - rows.departure_time,
        "stop_schedule_relationship": np.int32(0),
        "cancelled": False,
        "route_gtfs_id": rows.route_id.astype(str),
        "journey_id": rows.trip_id.map(by_journey),
        "match_deviation_minutes": rows.trip_id.map(
            {trip: scores[journey] for journey, trip in matches.items()}),
        "observed": rows.measured,
        "inferred": rows.inferred,
        "missing_reason": rows.missing_reason,
        "dwell_share": np.float32("nan"),
        "observed_primary": rows.was_arrival.notna() | rows.was_departure.notna(),
    })
    for column in ("arrival_delay", "departure_delay"):
        out[column] = out[column].round().astype("Int32")
    return out.sort_values(["trip_id", "stop_sequence"]).reset_index(drop=True), edges


def emit_added(calls, matches, day, minimum_stops=3):
    """One row per stop call of a vehicle the timetable never promised.

    Roughly a fifth of the journeys reconstructed each day end up with no trip,
    and the timetable cannot be the explanation: on every day measured there are
    only enough unused trips to cover about a sixth of them, so most of these
    vehicles have nothing left to be matched to. They are not double sightings
    either — for nine in ten, no matched vehicle passed the same stop within two
    minutes. They dwell at stops almost as much as scheduled runs do, which is
    what a vehicle carrying passengers does and a vehicle running to a depot does
    not. Dropping them silently overstates how long a passenger waits, because it
    removes departures from the observed side of the comparison while leaving the
    scheduled side whole.

    So they are published, as GTFS-RT ADDED trips, and deliberately thin. Their
    delays are null rather than zero: there is no scheduled time to be late
    against, and a zero would read as perfect punctuality. Their stop sequence is
    the order they were seen in, not a position in a pattern — these runs are
    observed from wherever the tracker picked them up, typically halfway along
    the line, so their first stop is not an origin. `dwell_share` is carried so a
    consumer can set its own threshold for what counts as service instead of
    inheriting one chosen here.
    """
    left = calls[~calls.journey.isin(matches)].copy()
    keep = left.groupby("journey").point.transform("size") >= minimum_stops
    left = left[keep]
    if not len(left):
        return pd.DataFrame(columns=list(SCHEMA) + EXTRA + ["observed_primary"])

    left = left.sort_values(["journey", "order"])
    left["arrival_s"] = match.service_day_seconds(left.arrival, day)
    left["departure_s"] = match.service_day_seconds(left.departure, day)
    # An added trip is nothing but its sightings, so a call with no time at all
    # has nothing to say. A scheduled trip keeps such a row and explains it,
    # because there the timetable asserts the call should have happened; here
    # nothing does. Dropping it is what keeps every published row timed.
    left = left[left.arrival_s.notna() | left.departure_s.notna()]
    keep = left.groupby("journey").point.transform("size") >= minimum_stops
    left = left[keep]
    if not len(left):
        return pd.DataFrame(columns=list(SCHEMA) + EXTRA + ["observed_primary"])
    first = left.groupby("journey").arrival_s.transform("min")

    midnight = pd.Timestamp(day).tz_localize(match.BRUSSELS)

    def stamp(seconds):
        out = midnight + pd.to_timedelta(seconds, unit="s")
        return out.dt.tz_convert("UTC").dt.tz_localize(None).dt.floor("us")

    dwell = (left.groupby("journey").dwelled.transform("mean")
             if "dwelled" in left else np.float32("nan"))

    out = pd.DataFrame({
        # A journey has no trip id, so it lends its own, prefixed to make clear
        # at a glance that nothing in the operator's timetable answers to it.
        "trip_id": "added-" + left.journey.astype(str),
        "start_date": day.strftime("%Y%m%d"),
        "start_time": first.map(_clock),
        "stop_sequence": left.groupby("journey").cumcount().astype("int32") + 1,
        "stop_id": left.point.astype(str),
        "route_id": left.line_id.astype(str),
        "direction_id": left.direction.astype("int32"),
        "trip_schedule_relationship": np.int32(1),
        "arrival_time": stamp(left.arrival_s),
        "departure_time": stamp(left.departure_s),
        "stop_schedule_relationship": np.int32(0),
        "cancelled": False,
        "route_gtfs_id": None,
        "journey_id": left.journey.astype(str),
        "match_deviation_minutes": np.float32("nan"),
        "observed": left.arrival_s.notna() | left.departure_s.notna(),
        "inferred": False,
        "missing_reason": None,
        "dwell_share": dwell,
        "observed_primary": left.arrival_s.notna() | left.departure_s.notna(),
    })
    # Null, not zero: an added trip has no scheduled time to be measured against.
    for column in ("arrival_delay", "departure_delay"):
        out[column] = pd.array([pd.NA] * len(out), dtype="Int32")
    out = out[list(SCHEMA) + EXTRA + ["observed_primary"]]
    return out.sort_values(["trip_id", "stop_sequence"]).reset_index(drop=True)


def _clock(seconds):
    if seconds != seconds:
        return None
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


