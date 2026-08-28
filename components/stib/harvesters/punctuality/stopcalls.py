#!/usr/bin/env python3
"""When each journey called at each stop.

The feed gives a vehicle's position as metres past a stop point, which makes stop
calls unusually direct to read: the poll where the reported point changes from A
to B *is* the vehicle reaching B. No projection onto a shape is needed — STIB has
already done that projection, and the point id is the answer.

Two times are wanted per call, and they are not the same time:

  * **arrival** — when the vehicle reached the stop. It falls between the last
    poll before the point changed and the first poll after, and is interpolated
    between them by how far each one had got.
  * **departure** — when it left. A vehicle at a stop reports zero metres past
    it, and it keeps reporting zero for as long as it stands there, so a dwell is
    visible as a run of zeros and departure is the end of that run, not its
    middle. A vehicle stuck in traffic or laying over between two stops reports a
    *non-zero* constant distance instead, and is therefore never mistaken for a
    dwell — which matters, because layovers are long and would otherwise turn
    into minutes of invented waiting at a stop the vehicle had already left.
"""
import numpy as np
import pandas as pd

# A vehicle is standing at a stop, rather than just past it, while it reports no
# more than this many metres beyond the point. The feed quantises to the metre
# and vehicles do not park perfectly.
AT_STOP_METRES = 12

# Two polls further apart than this say nothing about what happened between them.
MAX_BRIDGE_SECONDS = 180.0

# A vehicle can stand *on* a stop for far longer than it dwells there: a terminus
# layover parks it on the last stop of the line, and a driver changeover holds it
# at an intermediate one. The feed reports both exactly as it reports a dwell, so
# beyond this the standstill is not read as a departure at all — a null says "not
# observed", which is true, where two hours of dwell would have said something
# false and been believed.
MAX_DWELL_SECONDS = 600.0

# Not every line is tracked to the metre. The four metro lines report the stop
# they are at and nothing else — lines 1 and 5 report zero metres past it in
# 100% of observations, lines 2 and 6 in 61-65% with a maximum of one metre —
# because a metro's position comes from the signalling system, which knows
# sections and not metres. On those lines a run of zeros is not a dwell, it is
# the whole hop, and reading it as a dwell invents 70 seconds of standing at
# every station. Departure is then simply unobservable, and is reported equal to
# arrival rather than guessed at.
COARSE_METRES = 30


def coarse_lines(observations: pd.DataFrame) -> set:
    """Lines whose feed resolves stops but not distance between them."""
    spread = observations.groupby("line_id").distance_from_point.quantile(0.90)
    return set(spread.index[spread <= COARSE_METRES])


def journey_calls(journey: pd.DataFrame, coarse: bool = False) -> pd.DataFrame:
    """Stop calls for one journey, in order.

    `journey` is the located observations of a single track, any order. Returns
    one row per stop reached, with the times that could be established; a stop
    the vehicle was already at when the track began has no arrival, and one it
    had not left when the track ended has no departure.
    """
    journey = journey.sort_values("ts")
    stamps = journey.ts.values.astype("datetime64[ns]").astype("int64") / 1e9
    progress = journey.progress.values
    marks = journey.point_metres.values
    metres = journey.distance_from_point.values
    points = journey.point.values

    rows = []
    changes = np.flatnonzero(points[1:] != points[:-1]) + 1
    starts = np.concatenate([[0], changes])
    ends = np.concatenate([changes, [len(journey)]])

    for run, (first, last) in enumerate(zip(starts, ends)):
        point = points[first]
        arrival = None
        if run > 0:
            before, after = first - 1, first
            if stamps[after] - stamps[before] <= MAX_BRIDGE_SECONDS:
                approach = (progress[before] - progress[before - 1],
                            stamps[before] - stamps[before - 1]) if before else None
                arrival = _crossing(stamps[before], stamps[after],
                                    progress[before], progress[after],
                                    marks[after], approach)

        # The dwell: the leading polls of this run that report the vehicle at the
        # stop rather than past it.
        standing = first
        if not coarse:
            while standing < last and metres[standing] <= AT_STOP_METRES:
                standing += 1

        if standing == first:
            # Never seen at rest here — it went straight through, so it left when
            # it arrived.
            departure = arrival
        else:
            settled = stamps[standing - 1]
            moving = stamps[standing] if standing < last else (
                stamps[last] if last < len(journey) else None)
            if moving is None or moving - settled > MAX_BRIDGE_SECONDS:
                departure = settled
            else:
                departure = 0.5 * (settled + moving)
            if arrival is not None and departure - arrival > MAX_DWELL_SECONDS:
                departure = None                # a layover, not a dwell
            if arrival is None and run == 0:
                arrival = None                  # the track began mid-dwell
            elif arrival is not None:
                arrival = min(arrival, stamps[first])

        rows.append({
            "point": point,
            # Where the stop sits along the chain, in metres. Carried through to
            # the stop calls because merging a fragment back into a trip has to
            # bound how far a vehicle could have moved between the two, and the
            # located observations are gone by then.
            "metres": float(marks[first]),
            "layover": bool(departure is None and standing > first),
            "order": run,
            "arrival": arrival,
            "departure": departure,
            "observations": int(last - first),
            "dwelled": bool(standing > first),
        })

    calls = pd.DataFrame(rows)
    if calls.empty:
        return calls
    for column in ("arrival", "departure"):
        calls[column] = pd.to_datetime(calls[column], unit="s", utc=True)
    return calls


def _crossing(t0, t1, p0, p1, target, approach=None):
    """When progress passed `target`, between the polls either side of it.

    Usually the later poll is already past the stop and the crossing falls
    linearly between the two. Often it is not: a vehicle standing at the stop
    reports exactly zero metres past it, so the later poll sits exactly on the
    target and linear interpolation degenerates to "it arrived when we next
    looked" — late by up to a poll, systematically. Where the poll before shows
    how fast the vehicle was closing, that speed is carried the last few metres
    instead, which is both earlier and right.
    """
    if p1 > p0 + 1e-9 and p1 > target:
        share = (target - p0) / (p1 - p0)
        return t0 + float(np.clip(share, 0.0, 1.0)) * (t1 - t0)
    if approach and approach[0] > 1.0 and approach[1] > 0:
        speed = approach[0] / approach[1]
        return float(min(t0 + max(target - p0, 0.0) / speed, t1))
    return t1


# ------------------------------------------------------- the two edges --
#
# A stop call is read off the moment the reported point *changes*, which means
# the first and last stop of a run have no moment to read. At the start the
# vehicle is already past stop 1 when it first appears in its (line, direction,
# destination) group — the departure from stop 1 happened before anything was
# watching. At the end it reaches its terminus and immediately leaves the group
# for the opposite one, so the arrival at the last stop falls outside the journey
# that should own it. Neither is a tracking failure; there is simply no crossing
# to observe, and the loss is a fixed two calls per trip whatever its length.
#
# It is worth about a tenth of the archive. Measured on a built day, 89.6% of the
# stop calls a matched trip is missing sit at its two ends — roughly half of all
# trips lose exactly one call at each end — while interior holes are 14.5%. Those
# interior holes have other causes and are left alone.
#
# What can be said about an edge is what the vehicle was doing when it appeared
# or vanished. The speed between its first two calls, carried back one hop, dates
# the departure it had already made; the speed between its last two, carried
# forward, dates the arrival it was about to make. Both are bounded by the same
# MAX_SPEED the tracker uses, refused when the vehicle was standing rather than
# running, and refused when the extrapolation would have to reach further than
# `EDGE_MAX_SECONDS` or `EDGE_MAX_STOPS`.
#
# These are **inferences, not observations**, and they are marked as such: the
# rows they fill carry `observed = False` and `inferred = True`, so a consumer
# that wants only measured times can drop them with one predicate.

EDGE_MAX_STOPS = 2                # never reach further than this from the edge
EDGE_MAX_SECONDS = 300.0          # nor further than this in time
EDGE_MIN_SPEED = 1.0              # m/s — below this the vehicle was standing
EDGE_MAX_SPEED = 25.0             # the tracker's own bound, 90 km/h


def place_positions(frame: pd.DataFrame) -> np.ndarray:
    """`edge_metres` for every row, with unreported stops placed per trip."""
    metres = frame["edge_metres"].to_numpy(dtype=float, copy=True)
    for positions in frame.groupby("trip_id", sort=False).indices.values():
        metres[positions] = _place(metres[positions])
    return metres


# ---------------------------------------------------- bracketed holes --
#
# A call missing from the *middle* of a trip, with a measured call on either
# side, is the one inference that needs no argument: the vehicle demonstrably
# passed, and both ends of its passage are timed. Interpolating between them by
# distance rather than by stop count respects a chain whose hops are not equal,
# and the same MAX_SPEED bound applies. What is refused is a bracket too wide to
# mean anything — over a quarter of an hour, or implying a speed no vehicle runs
# at, the two observations are not evidence about the middle.
#
# Only the arrival is inferred. How long it stood there is not deducible from
# two calls either side, and inventing a dwell would be the guess this avoids.

INTERIOR_MAX_SECONDS = 900.0
INTERIOR_MIN_SPEED = 1.0


def fill_interior(frame, arrival, departure, inferred, metres):
    """Interpolate missing calls that have a measured call on both sides."""
    measured = frame["measured"].to_numpy(dtype=bool)
    counts = {"filled": 0, "trips_filled": 0, "refused_bracket_too_wide": 0,
              "refused_no_usable_speed": 0, "refused_out_of_order": 0}

    for positions in frame.groupby("trip_id", sort=False).indices.values():
        seen = positions[measured[positions]]
        if len(seen) < 2:
            continue
        before = counts["filled"]
        spots = np.searchsorted(positions, seen)
        for (left, right), (a, b) in zip(zip(spots, spots[1:]), zip(seen, seen[1:])):
            if right - left < 2:
                continue                        # nothing missing between them
            went = _either(departure, arrival, a)
            came = _either(arrival, departure, b)
            span, run = came - went, metres[b] - metres[a]
            if not (np.isfinite(span) and np.isfinite(run)) or span <= 0 or run <= 0:
                counts["refused_no_usable_speed"] += 1
                continue
            if span > INTERIOR_MAX_SECONDS:
                counts["refused_bracket_too_wide"] += 1
                continue
            speed = run / span
            if not INTERIOR_MIN_SPEED <= speed <= EDGE_MAX_SPEED:
                counts["refused_no_usable_speed"] += 1
                continue
            steps = positions[left + 1:right]
            gaps = metres[steps] - metres[a]
            if not np.all((gaps > 0) & (gaps < run)):
                counts["refused_out_of_order"] += 1
                continue
            arrival[steps] = went + gaps / speed
            inferred[steps] = True
            counts["filled"] += len(steps)
        counts["trips_filled"] += counts["filled"] > before
    return counts


# --------------------------------------------- what is still missing --
#
# One number for coverage says nothing about what to fix next. Every stop call
# still without a time gets a reason instead, and the four are different
# failures with different remedies:
#
#   * `dropped_track` — the tracker saw this vehicle and lost it. A fragment was
#     offered to this trip and refused; the refusal reason is in the merge
#     report. This is the one that is ours to fix.
#   * `journey_ended_early` / `journey_started_late` — no fragment was even
#     offered. The vehicle stopped being reported, which may be a feed gap and
#     may be a trip that genuinely short-turned or did not run. STIB publishes no
#     cancellation signal, so these two cannot be told apart from here.
#   * `unbracketed_hole` — a hole in the middle whose brackets were too far apart
#     in time, or implied a speed no vehicle runs at, to interpolate across.
#   * `no_journey_matched` — the trip was matched but its journey carries no
#     usable time at all. Rare.

def missing_reasons(frame, has_time, lost) -> np.ndarray:
    """Why each row that still has no time has none."""
    reasons = np.full(len(frame), None, dtype=object)
    for trip, positions in frame.groupby("trip_id", sort=False).indices.items():
        got = positions[has_time[positions]]
        if not len(got):
            reasons[positions] = "no_journey_matched"
            continue
        dropped = trip in lost
        first, last = got[0], got[-1]
        for position in positions[~has_time[positions]]:
            if position < first:
                reasons[position] = ("dropped_track" if dropped
                                     else "journey_started_late")
            elif position > last:
                reasons[position] = ("dropped_track" if dropped
                                     else "journey_ended_early")
            else:
                reasons[position] = "unbracketed_hole"
    return reasons


def extrapolate_edges(frame: pd.DataFrame, metres=None):
    """Date the stop calls at each trip's two ends, where no crossing exists.

    `frame` is one row per scheduled stop call of a trip, sorted by
    `(trip_id, stop_sequence)`, carrying `actual_arrival` and `actual_departure`
    in service-day seconds (NaN where nothing was read) and `edge_metres`, the
    stop's position along its line's chain.

    Returns `(arrival, departure, inferred, counts)`. Only the calls immediately
    outside the observed range are ever filled — an interior hole is never
    invented, because an interior hole means the tracker lost the vehicle and
    that is a different thing from never having looked.
    """
    arrival = frame["actual_arrival"].to_numpy(dtype=float, copy=True)
    departure = frame["actual_departure"].to_numpy(dtype=float, copy=True)
    metres = (place_positions(frame) if metres is None
              else np.asarray(metres, dtype=float))
    inferred = np.zeros(len(frame), dtype=bool)

    counts = {"leading": 0, "trailing": 0, "trips_extended": 0,
              "refused_nothing_to_extend": 0, "refused_no_usable_speed": 0,
              "refused_too_far": 0, "refused_no_position": 0}

    for positions in frame.groupby("trip_id", sort=False).indices.values():
        before = counts["leading"] + counts["trailing"]
        seen = positions[np.isfinite(arrival[positions]) |
                         np.isfinite(departure[positions])]
        if len(seen) < 2:
            counts["refused_nothing_to_extend"] += 1
            continue
        _extend(positions, seen, arrival, departure, metres, inferred, counts, -1)
        _extend(positions, seen, arrival, departure, metres, inferred, counts, +1)
        counts["trips_extended"] += (counts["leading"] + counts["trailing"]) > before
    return arrival, departure, inferred, counts


def _place(metres):
    """Give every stop of a trip a position, including ones never reported.

    A stop's position along the chain is measured from the feed, so a stop the
    feed never reported on this line and direction has none — and it is
    disproportionately a *terminus*, which is exactly the stop the trailing
    extrapolation wants. Untreated it is the single largest refusal.

    An unreported stop between two reported ones is placed between them; one past
    the end is placed by the trip's own median hop, which is a length measured on
    this very line rather than a constant invented here. Getting that length 20%
    wrong moves the inferred time by 20% of one hop — a handful of seconds on a
    call already marked as an inference.
    """
    known = np.flatnonzero(np.isfinite(metres))
    if len(known) < 2:
        return metres
    hop = float(np.median(np.diff(metres[known]) / np.diff(known)))
    if not np.isfinite(hop) or hop <= 0:
        return metres
    out = np.interp(np.arange(len(metres)), known, metres[known])
    first, last = known[0], known[-1]
    out[:first] = metres[first] - hop * (first - np.arange(first))
    out[last + 1:] = metres[last] + hop * (np.arange(last + 1, len(metres)) - last)
    return out


def _either(first, second, index):
    """The one time this call has, preferring `first`."""
    value = first[index]
    return value if np.isfinite(value) else second[index]


def _extend(positions, seen, arrival, departure, metres, inferred, counts, way):
    """Carry the edge speed one or two stops past the end of what was seen.

    The speed is the *running* speed over the hop between the two calls nearest
    the edge — from the departure of one to the arrival of the next — so a dwell
    at either end is not counted as time spent moving. Taking it from arrival to
    arrival instead would fold the dwell into the hop, halve the speed at a stop
    where the vehicle waited, and refuse the extrapolation as too far.
    """
    edge, neighbour = (seen[-1], seen[-2]) if way > 0 else (seen[0], seen[1])
    left, reached = (neighbour, edge) if way > 0 else (edge, neighbour)
    departed = _either(departure, arrival, left)
    arrived = _either(arrival, departure, reached)
    # The extrapolation runs from the far side of the edge's own stop: the
    # moment it left, going forward; the moment it arrived, going back.
    base = _either(departure, arrival, edge) if way > 0 else \
        _either(arrival, departure, edge)
    if not (np.isfinite(departed) and np.isfinite(arrived) and np.isfinite(base)):
        counts["refused_no_usable_speed"] += 1
        return

    span = arrived - departed
    run = (metres[edge] - metres[neighbour]) * way
    if not np.isfinite(run) or span <= 0 or run <= 0:
        counts["refused_no_usable_speed"] += 1
        return
    speed = run / span
    if not EDGE_MIN_SPEED <= speed <= EDGE_MAX_SPEED:
        # Standing at a stop, or a jump the tracker would itself have refused.
        counts["refused_no_usable_speed"] += 1
        return

    here = int(np.flatnonzero(positions == edge)[0])
    for step in range(1, EDGE_MAX_STOPS + 1):
        index = here + way * step
        if not 0 <= index < len(positions):
            return
        target = positions[index]
        if not np.isfinite(metres[target]):
            counts["refused_no_position"] += 1
            return
        gap = (metres[target] - metres[edge]) * way
        if gap <= 0:
            return                              # the chain does not order these
        if gap / speed > EDGE_MAX_SECONDS:
            counts["refused_too_far"] += 1
            return
        when = base + way * gap / speed
        if way > 0:
            # It was about to arrive; when it left again is not knowable.
            arrival[target] = when
            counts["trailing"] += 1
        else:
            # It had already left; when it arrived was before anyone looked.
            departure[target] = when
            counts["leading"] += 1
        inferred[target] = True


def all_calls(tracked: pd.DataFrame) -> pd.DataFrame:
    """Stop calls for every journey in a tracked day."""
    tracked = tracked[tracked.journey.notna()]
    frames = []
    coarse = coarse_lines(tracked)
    for journey, group in tracked.groupby("journey", sort=False):
        calls = journey_calls(group, coarse=group.line_id.iloc[0] in coarse)
        if calls.empty:
            continue
        calls["journey"] = journey
        calls["line_id"] = group.line_id.iloc[0]
        calls["direction"] = group.direction.iloc[0]
        calls["destination"] = group.destination.iloc[0]
        calls["coarse"] = group.line_id.iloc[0] in coarse
        frames.append(calls)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
