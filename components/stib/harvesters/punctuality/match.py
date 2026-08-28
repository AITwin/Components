#!/usr/bin/env python3
"""Recovering journeys, and then trip ids, from a feed that names neither.

STIB's realtime feed carries no vehicle identifier and no trip id. Every poll is
an anonymous set of positions, and two consecutive polls have to be stitched into
tracks before anything can be said about a journey. Two facts make that possible:

  * vehicles on the same line, in the same direction, running to the same
    destination do not overtake each other, so their order along the line is the
    same in every poll;
  * they move forward, by an amount a 20-second poll bounds.

Which reduces stitching to an ordered alignment between two sorted lists — the
same shape of problem as a diff, and solved the same way.

The same no-overtaking fact returns at the end, for trip ids: the journeys a line
runs in a direction and the trips its timetable holds are both in time order, and
the assignment between them must preserve that order. Choosing each journey's
best trip independently does not, and the errors it makes are the ones that
matter — two journeys minutes apart both claiming the trip between them. So the
assignment is one order-preserving alignment per (line, direction) over the whole
day, by dynamic programming, and journeys with no acceptable trip are left
unmatched.
"""
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

# A poll is ~20 s apart. Positions are metres along the line, so what a vehicle
# can have done between two polls is a speed — 25 m/s is 90 km/h, which no STIB
# vehicle exceeds — plus slack for the metro lines, whose position is quantised
# to whole stations and so arrives in jumps.
MAX_SPEED = 25.0                  # metres per second
ADVANCE_SLACK = 400.0             # metres of quantisation slack
# The metro reports the station it is at and nothing in between, so its position
# does not creep — it jumps a whole inter-station hop at once, up to about 1.6 km.
# Bounding its movement by speed alone cuts every metro journey into fragments a
# few stations long.
COARSE_SLACK = 1800.0
BACKWARD_TOLERANCE = 60.0         # metres a vehicle may appear to slip back
TRACK_TIMEOUT = 240.0             # seconds a track survives without an observation
# Pairing cost is how much of what was possible in the interval the vehicle would
# have had to use — 0 for standing still, 1 for the fastest move still allowed.
# Scaling it in metres instead makes a long legal move dearer than abandoning the
# track and starting another, which is how a metro running between two distant
# stations gets its journey cut in half every time.
GAP_COST = 0.75
MIN_TRACK_CALLS = 3               # a journey worth reporting visits this many stops


# --------------------------------------------------------------- alignment --

def align(costs, gap_cost=GAP_COST):
    """Order-preserving alignment of two sequences, as index pairs.

    `costs[i, j]` is the cost of pairing i with j, `inf` where the pair is
    impossible; leaving either element unpaired costs `gap_cost`. This is the
    Needleman-Wunsch recurrence, and it is what enforces no-overtaking: pairing
    (i, j) forbids any later pairing (i', j') with i' > i and j' < j.

    The row recurrence is run with numpy rather than a double loop. The awkward
    term is the within-row one, `best[i, j] = min(best[i, j], best[i, j-1] + gap)`,
    which is sequential — but with a constant gap cost it is a running minimum of
    `best[i, j] - j * gap`, which numpy accumulates in one pass. Without that a
    day of one line's journeys against its trips is a few hundred thousand cells
    of Python.
    """
    n, m = costs.shape
    steps = np.arange(m + 1) * gap_cost
    best = np.full((n + 1, m + 1), np.inf)
    best[0] = steps
    for i in range(1, n + 1):
        row = np.minimum(best[i - 1] + gap_cost,
                         np.concatenate([[np.inf], best[i - 1, :-1] + costs[i - 1]]))
        np.minimum.accumulate(row - steps, out=row)      # the j-1 gap chain
        best[i] = row + steps

    pairs, i, j = [], n, m
    while i and j:
        here = best[i, j]
        if np.isclose(here, best[i - 1, j - 1] + costs[i - 1, j - 1]):
            i, j = i - 1, j - 1
            pairs.append((i, j))
        elif np.isclose(here, best[i - 1, j] + gap_cost):
            i -= 1
        else:
            j -= 1
    return pairs[::-1], float(best[n, m])


# ------------------------------------------------------------------ tracks --

def track_journeys(located: pd.DataFrame, coarse=()) -> pd.DataFrame:
    """Give every observation a `journey` id.

    Tracking runs inside (line, direction, destination). Destination is part of
    the key because it is constant for a whole run and splits vehicles that share
    a line but not a turn-back point; a vehicle that reaches its terminus and
    starts back the other way leaves this group and appears in the opposite one,
    which is exactly where one journey should end and the next begin.
    """
    located = located.sort_values(["line_id", "direction", "destination", "ts", "progress"])
    journey_ids = np.empty(len(located), dtype=object)
    seed = [0]

    offset = 0
    for key, group in located.groupby(["line_id", "direction", "destination"], sort=False):
        slack = COARSE_SLACK if key[0] in coarse else ADVANCE_SLACK
        journey_ids[offset:offset + len(group)] = _track_group(group, key, seed, slack)
        offset += len(group)

    out = located.copy()
    out["journey"] = journey_ids
    counts = out.groupby("journey").point.nunique()
    keep = set(counts.index[counts >= MIN_TRACK_CALLS])
    out["journey"] = [j if j in keep else None for j in out.journey]
    return out


def _track_group(group, key, seed, slack=ADVANCE_SLACK):
    line, direction, destination = key
    stamps = group.ts.values.astype("datetime64[ns]").astype("int64") / 1e9
    progress = group.progress.values

    live = []            # (journey id, last progress, last time)
    assigned = np.empty(len(group), dtype=object)

    start = 0
    while start < len(group):
        end = start
        while end < len(group) and stamps[end] == stamps[start]:
            end += 1
        now = stamps[start]
        here = progress[start:end]

        live = [t for t in live if now - t[2] <= TRACK_TIMEOUT]
        live.sort(key=lambda t: t[1])

        if live and len(here):
            costs = np.full((len(live), len(here)), np.inf)
            for i, (_, was, when) in enumerate(live):
                elapsed = max(now - when, 1.0)
                advance = here - was
                ok = (advance >= -BACKWARD_TOLERANCE) & \
                     (advance <= MAX_SPEED * elapsed + slack)
                # Standing still is free; the cost grows with how far a vehicle
                # would have had to run, and with how long it was unseen.
                allowed = MAX_SPEED * elapsed + slack
                costs[i, ok] = np.abs(advance[ok]) / allowed + 0.15 * (elapsed > 45)
            pairs, _ = align(costs)
        else:
            pairs = []

        taken = set()
        for i, j in pairs:
            journey, _, _ = live[i]
            assigned[start + j] = journey
            live[i] = (journey, here[j], now)
            taken.add(j)
        for j in range(len(here)):
            if j in taken:
                continue
            seed[0] += 1
            journey = f"{line}-{direction}-{destination}-{seed[0]:06d}"
            assigned[start + j] = journey
            live.append((journey, here[j], now))
        start = end
    return assigned


# ------------------------------------------------------------- trip ids --

# Journeys and trips are paired only if they agree this closely, in minutes of
# median deviation over the stops they share.
MAX_DEVIATION_MINUTES = 12.0
TRIP_GAP_COST = 7.0          # cost of leaving a journey, or a trip, unmatched
MIN_SHARED_STOPS = 3
WINDOW_MINUTES = 25.0        # never even compare a journey and a trip further apart

BRUSSELS = "Europe/Brussels"


def service_day_seconds(stamps: pd.Series, day) -> np.ndarray:
    """Seconds since the service day's local midnight.

    GTFS counts a service day from local midnight and lets it run past 24:00, so
    a night bus at 01:30 is 25:30. Observations are converted the same way, which
    is what makes the two comparable at all.
    """
    midnight = pd.Timestamp(day).tz_localize(BRUSSELS)
    return (stamps.dt.tz_convert(BRUSSELS) - midnight).dt.total_seconds().values


def timetable(gtfs: dict, day) -> pd.DataFrame:
    """Every stop call the timetable holds for `day`, in normalised point ids."""
    from .calendars import services_on
    from .network import normalise_stop

    calendar = gtfs.get("calendar")
    exceptions = gtfs.get("calendar_dates")
    running = services_on(_as_dates(calendar, ("start_date", "end_date")),
                          _as_dates(exceptions, ("date",)), day)

    routes = gtfs["routes"].copy()
    routes["route_short_name"] = routes.route_short_name.astype(str)
    trips = gtfs["trips"].merge(routes[["route_id", "route_short_name"]], on="route_id")
    trips = trips[trips.service_id.astype(str).isin({str(s) for s in running})]

    times = gtfs["stop_times"].merge(
        trips[["trip_id", "route_short_name", "direction_id", "route_id"]], on="trip_id")
    times["point"] = times.stop_id.astype(str).map(normalise_stop)
    for column in ("arrival_time", "departure_time"):
        times[column] = pd.to_timedelta(times[column]).dt.total_seconds()
    return times.sort_values(["trip_id", "stop_sequence"])


def _as_dates(frame, columns):
    """calendars.services_on wants YYYYMMDD-ish text; the parquet holds dates."""
    if frame is None or not len(frame):
        return frame
    out = frame.copy()
    for column in columns:
        out[column] = pd.to_datetime(out[column]).dt.strftime("%Y%m%d")
    return out


def assign_trips(calls: pd.DataFrame, schedule: pd.DataFrame, day):
    """Give each journey a GTFS trip id, or none.

    Per (line, direction) this is one order-preserving alignment between the
    journeys of the day and the trips of the day, both in time order. A journey
    is compared with a trip only over the stops they share, by the median of the
    absolute differences between observed and scheduled arrival — a median rather
    than a mean because one badly interpolated call should not decide a trip, and
    over shared stops rather than all of them because a short turn legitimately
    serves fewer stops than the pattern it belongs to.

    A journey whose best trip is still more than `MAX_DEVIATION_MINUTES` out, or
    which shares too few stops with any trip, stays unmatched. Twelve minutes is
    generous for a metro and tight for a bus in traffic; it is set by what the
    headway makes unambiguous, not by what a delay can be.
    """
    calls = calls.copy()
    calls["seconds"] = service_day_seconds(
        calls.arrival.fillna(calls.departure), day)

    observed = {}
    for journey, group in calls.groupby("journey", sort=False):
        good = group.dropna(subset=["seconds"])
        observed[journey] = (dict(zip(good.point, good.seconds)),
                             group.line_id.iloc[0], int(group.direction.iloc[0]),
                             float(np.nanmin(group.seconds)))

    planned = {}
    for trip, group in schedule.groupby("trip_id", sort=False):
        planned[trip] = (dict(zip(group.point, group.arrival_time)),
                         str(group.route_short_name.iloc[0]),
                         int(group.direction_id.iloc[0]),
                         float(group.departure_time.iloc[0]))

    by_group = defaultdict(lambda: ([], []))
    for journey, (_, line, direction, start) in observed.items():
        by_group[(line, direction)][0].append((start, journey))
    for trip, (_, line, direction, start) in planned.items():
        by_group[(line, direction)][1].append((start, trip))

    matches, scores = {}, {}
    for (line, direction), (journeys, trips) in by_group.items():
        journeys.sort()
        trips.sort()
        if not journeys or not trips:
            continue
        costs = np.full((len(journeys), len(trips)), np.inf)
        trip_starts = np.array([s for s, _ in trips])
        for i, (start, journey) in enumerate(journeys):
            seen = observed[journey][0]
            near = np.flatnonzero(np.abs(trip_starts - start) <= WINDOW_MINUTES * 60)
            for j in near:
                cost = _deviation(seen, planned[trips[j][1]][0])
                if cost is not None and cost <= MAX_DEVIATION_MINUTES:
                    costs[i, j] = cost
        pairs, _ = align(costs, TRIP_GAP_COST)
        for i, j in pairs:
            matches[journeys[i][1]] = trips[j][1]
            scores[journeys[i][1]] = float(costs[i, j])

    return matches, scores


def _deviation(seen: dict, scheduled: dict):
    """Median |observed - scheduled| in minutes over shared stops, or None."""
    shared = seen.keys() & scheduled.keys()
    if len(shared) < MIN_SHARED_STOPS:
        return None
    gaps = [abs(seen[p] - scheduled[p]) for p in shared]
    coverage = len(shared) / max(len(seen), 1)
    return float(np.median(gaps)) / 60.0 + 3.0 * (1.0 - coverage)


# ------------------------------------------------------ fragment merging --
#
# The tracker sometimes cuts one real run into two. Stage 2 then does the right
# thing with the pieces — a fragment sharing two stops with a trip is refused,
# because two stops cannot tell one trip from its neighbour — and the trip keeps
# only the stop calls of whichever piece won it. That is most of the distance
# between 95% of trips matched and 78% of stop calls observed: the trips are
# found, but a third of their calls are sitting in a fragment nobody claimed.
#
# So: after the assignment, an unmatched fragment may be attached to a trip that
# is *already matched*, when doing so is unambiguous. Never to an unmatched trip
# — a fragment is by construction too short to identify a trip on its own, and
# letting it name one would be exactly the guess the 3-shared-stop rule exists to
# refuse. The fragment adds observed times to stop calls the trip already has;
# it can never add a trip, a row, or a stop.
#
# Five things are checked, and a candidate that fails any of them is refused
# rather than argued with. A wrong merge is worse than a missing one: it does
# not fail loudly, it silently writes a delay that never happened.
#
#   1. **On the trip.** Every stop the fragment called at must be a stop of the
#      trip. A fragment that visits a stop the trip does not serve is not a piece
#      of that trip's run.
#   2. **The same delay.** The fragment's median offset from the timetable must
#      be within `MERGE_MAX_DRIFT_MINUTES` of the offset the trip's own journey
#      already shows, and inside the assignment's own `MAX_DEVIATION_MINUTES`
#      band. A trip running six minutes late has a fragment six minutes late;
#      comparing the fragment with the timetable alone would refuse exactly the
#      delayed trips this archive exists to record.
#   3. **No conflict.** Where the fragment and the journey both called at a stop,
#      the two times must agree to within `MERGE_AGREE_SECONDS`. Overlap is
#      allowed rather than forbidden because the overlap is the evidence: a
#      broken track re-reports the stop it was lost at, and two readings of one
#      event agree. Two readings that *disagree* are two vehicles, and refusing
#      them is the whole point.
#   4. **Continuity.** Journey and fragment are merged into one trajectory in
#      time order, and it must behave like one vehicle: never running backwards
#      by more than `BACKWARD_TOLERANCE`, never covering ground faster than the
#      `MAX_SPEED` bound the tracker itself uses, and never with a hole longer
#      than `MERGE_MAX_GAP_SECONDS` between the two pieces. The speed bound is
#      what refuses a fragment observed at the same instant somewhere else on the
#      line: no vehicle is in two places at once.
#   5. **No overtaking.** The order-preserving guarantee the alignment enforced
#      must survive. For every other matched journey running at the same time,
#      the timetable says which of the two trips is ahead at that instant; the
#      fragment's observed position must agree. A merge that would put the
#      fragment ahead of a vehicle its trip is scheduled behind is refused — that
#      is precisely the crossing `align` forbade.
#
# And then uniqueness: if two trips both pass, the fragment goes to neither.

MERGE_MAX_GAP_SECONDS = 600.0     # the longest hole one run may have in it
MERGE_AGREE_SECONDS = 120.0       # two readings of one stop call, from each side
# The fragment carries the trip's own delay — measured where the two meet, and
# loosely, because this rule is not the one doing the work. Tightening it to four
# minutes refuses 1,003 fragments a day; at eight it refuses 395, and the ones it
# stops refusing are caught instead by `conflict`, `runs backwards` and
# `overtakes` — the physics. The measured cost of the change is nil: median delay
# 71 s against 72 s, implausibly-early rows 2.02% against 2.09%, for half a point
# of stop-call coverage. Beyond eight the gain stops and the ambiguity grows.
MERGE_MAX_DRIFT_MINUTES = 8.0
# ...measured where the two meet, not averaged over the whole run. Delay
# accumulates along a route, so a fragment covering the last ten stops of a
# thirty-stop line is legitimately several minutes further behind than the
# median of the journey's first twenty. Comparing it against that median refuses
# exactly the long routes whose tracks break most often — which is what the
# refusal counters showed: "delay disagrees" was four times any other reason.
MERGE_SEAM_STOPS = 3              # host calls nearest the seam, for that comparison
MERGE_ORDER_TOLERANCE = 250.0     # metres of slack in the no-overtaking test

# Fine-grained refusals, most-nearly-accepted first: a fragment refused for
# several reasons is reported under the one it got furthest with.
_REFUSALS = ("overtakes", "runs backwards", "too fast", "implausible gap",
             "conflict", "delay disagrees", "not on the trip")
_KIND = {
    "ambiguous": "ambiguity",
    "conflict": "conflict",
    "overtakes": "implausible", "runs backwards": "implausible",
    "too fast": "implausible", "implausible gap": "implausible",
    "delay disagrees": "implausible",
    "not on the trip": "no candidate", "no trip near it": "no candidate",
    "no matched trip on the line": "no candidate",
}


class _Run:
    """One journey's observed trajectory: when it was where, in metres."""

    __slots__ = ("journey", "seconds", "metres", "at", "start", "end")

    def __init__(self, journey, seconds, metres, at):
        self.journey = journey
        self.seconds = seconds
        self.metres = metres
        self.at = at                                  # point -> seconds
        self.start = float(seconds[0])
        self.end = float(seconds[-1])

    def joined(self, other):
        """This run with `other`'s observations folded in, in time order."""
        seconds = np.concatenate([self.seconds, other.seconds])
        metres = np.concatenate([self.metres, other.metres])
        order = np.argsort(seconds, kind="stable")
        at = dict(other.at)
        at.update(self.at)                            # the host's own reading wins
        return _Run(self.journey, seconds[order], metres[order], at)


def merge_fragments(calls: pd.DataFrame, schedule: pd.DataFrame, matches: dict, day):
    """Attach unmatched fragments to already-matched trips. Returns (merged, report).

    `merged` maps a fragment's journey id to the trip it joins — a second journey
    for that trip, never a new one. `report` counts what merged and what was
    refused, and why, because the only honest way to defend a rule like this is
    to say how often it declined to fire. `lost` maps a trip to the reason a
    fragment offered to it was turned away, which is what lets a stop call that
    is still missing say whether the vehicle was dropped or never seen.
    """
    if "metres" not in calls.columns:
        raise ValueError("stop calls carry no `metres`; rebuild them (stopcalls.py)")

    calls = calls.copy()
    calls["seconds"] = service_day_seconds(calls.arrival.fillna(calls.departure), day)
    coarse = (set(calls.loc[calls.coarse.astype(bool), "line_id"].astype(str))
              if "coarse" in calls.columns else set())

    runs, where = {}, {}
    for journey, group in calls.groupby("journey", sort=False):
        good = group.dropna(subset=["seconds"]).sort_values("seconds")
        if good.empty:
            continue
        runs[journey] = _Run(journey, good.seconds.values.astype(float),
                             good.metres.values.astype(float),
                             dict(zip(good.point, good.seconds)))
        where[journey] = (str(group.line_id.iloc[0]), int(group.direction.iloc[0]))

    planned, span, owner = {}, {}, {}
    for trip, group in schedule.groupby("trip_id", sort=False):
        group = group.sort_values("stop_sequence")
        planned[trip] = dict(zip(group.point, group.arrival_time))
        span[trip] = (float(group.arrival_time.iloc[0]),
                      float(group.arrival_time.iloc[-1]))
        owner[trip] = (str(group.route_short_name.iloc[0]),
                       int(group.direction_id.iloc[0]))

    # Where each stop sits along its chain, as the located observations measured
    # it. This is what turns a timetable into a scheduled *position*, which is
    # what the no-overtaking test compares against.
    chain = {}
    for key, group in calls.groupby(["line_id", "direction"], sort=False):
        chain[(str(key[0]), int(key[1]))] = dict(zip(group.point, group.metres))

    hosts, fragments = defaultdict(list), defaultdict(list)
    for journey, trip in matches.items():
        if journey in runs:
            hosts[where[journey]].append([runs[journey], trip])
    for journey in runs:
        if journey not in matches:
            fragments[where[journey]].append(journey)

    merged, refusals, added = {}, Counter(), 0
    # Which trips had a fragment offered and refused. That is evidence the
    # tracker saw the vehicle and dropped it, as against the vehicle simply
    # ceasing to be reported, and the two are different failures.
    lost = {}
    tracks = {}
    for key, group in fragments.items():
        pool = hosts.get(key)
        if not pool:
            refusals["no matched trip on the line"] += len(group)
            continue
        spans = np.array([span[trip] for _, trip in pool])
        slack = COARSE_SLACK if key[0] in coarse else ADVANCE_SLACK
        for fragment in sorted(group, key=lambda j: (runs[j].start, j)):
            piece = runs[fragment]
            near = np.flatnonzero(
                (spans[:, 0] - MAX_DEVIATION_MINUTES * 60 <= piece.end) &
                (spans[:, 1] + MAX_DEVIATION_MINUTES * 60 >= piece.start))
            if not len(near):
                refusals["no trip near it"] += 1
                continue

            taken, refused = [], []
            for index in near:
                host, trip = pool[index]
                reason = _may_join(piece, host, planned[trip], slack)
                if reason is None and _overtakes(piece, trip, pool, index,
                                                 planned, chain[key], tracks):
                    reason = "overtakes"
                if reason is None:
                    taken.append(index)
                else:
                    refused.append((index, reason))
            if len(taken) == 1:
                index = taken[0]
                pool[index][0] = pool[index][0].joined(piece)
                merged[fragment] = pool[index][1]
                added += len(piece.at)
            elif len(taken) > 1:
                refusals["ambiguous"] += 1
                for index in taken:
                    lost.setdefault(pool[index][1], "ambiguous")
            else:
                reason = _worst([r for _, r in refused])
                refusals[reason] += 1
                # Only the trips the fragment could actually have belonged to —
                # its stops are theirs, and it failed on something later than
                # that. A trip that merely happened to be near in time was never
                # a candidate and did not lose anything.
                for index, why in refused:
                    if why not in ("not on the trip", "no trip near it"):
                        lost.setdefault(pool[index][1], why)

    by_kind = Counter()
    for reason, count in refusals.items():
        by_kind[_KIND.get(reason, "no candidate")] += count
    total = sum(1 for j in runs if j not in matches)
    report = {
        "fragments": total,
        "merged": len(merged),
        "merged_share": round(len(merged) / max(total, 1), 4),
        "stop_calls_added": int(added),
        "trips_gaining_calls": len(set(merged.values())),
        "refused": dict(refusals.most_common()),
        "refused_by_kind": dict(by_kind.most_common()),
        "trips_offered_a_refused_fragment": len(lost),
    }
    return merged, report, lost


def _worst(reasons):
    """The refusal a fragment got furthest with, of several."""
    for reason in _REFUSALS:
        if reason in reasons:
            return reason
    return reasons[0] if reasons else "no trip near it"


def _may_join(piece: _Run, host: _Run, scheduled: dict, slack: float):
    """None if the fragment may join this trip, else why not."""
    if any(point not in scheduled for point in piece.at):
        return "not on the trip"
    shared = [p for p in host.at if p in scheduled]
    if not shared:
        return "not on the trip"

    drift = float(np.median([piece.at[p] - scheduled[p] for p in piece.at]))
    theirs = _seam_offset(host, shared, scheduled,
                          float(np.median([scheduled[p] for p in piece.at])))
    if abs(drift) > MAX_DEVIATION_MINUTES * 60:
        return "delay disagrees"
    if abs(drift - theirs) > MERGE_MAX_DRIFT_MINUTES * 60:
        return "delay disagrees"

    for point in piece.at.keys() & host.at.keys():
        if abs(piece.at[point] - host.at[point]) > MERGE_AGREE_SECONDS:
            return "conflict"

    return _continuity(piece, host, slack)


def _seam_offset(host: _Run, shared, scheduled: dict, seam: float) -> float:
    """The host journey's delay where the fragment joins it, not on average.

    A route's delay grows along it. Taking the median offset over the whole
    journey and comparing a tail fragment against it charges the fragment for
    delay the vehicle picked up after the journey's last call — which on a long
    route is minutes. The comparison that means something is local: the offset at
    the host's own calls nearest the seam, in scheduled time.
    """
    nearest = sorted(shared, key=lambda p: abs(scheduled[p] - seam))[:MERGE_SEAM_STOPS]
    return float(np.median([host.at[p] - scheduled[p] for p in nearest]))


def _continuity(piece: _Run, host: _Run, slack: float):
    """Whether the two, put in time order, behave like one vehicle."""
    times = np.concatenate([piece.seconds, host.seconds])
    metres = np.concatenate([piece.metres, host.metres])
    side = np.concatenate([np.zeros(len(piece.seconds)), np.ones(len(host.seconds))])
    order = np.lexsort((side, times))
    times, metres, side = times[order], metres[order], side[order]

    steps, advance = np.diff(times), np.diff(metres)
    if np.any(advance < -BACKWARD_TOLERANCE):
        return "runs backwards"
    crossing = side[1:] != side[:-1]
    if not crossing.any():
        return "implausible gap"
    allowed = MAX_SPEED * np.maximum(steps, 1.0) + slack
    if np.any(crossing & (advance > allowed)):
        return "too fast"
    if float(np.min(steps[crossing])) > MERGE_MAX_GAP_SECONDS:
        return "implausible gap"
    return None


def _scheduled_track(trip, planned, chain, cache):
    """A trip's scheduled run as (times, metres) along its chain."""
    if trip not in cache:
        pairs = sorted((t, chain[p]) for p, t in planned[trip].items() if p in chain)
        cache[trip] = (np.array([t for t, _ in pairs]),
                       np.array([m for _, m in pairs])) if len(pairs) >= 2 else None
    return cache[trip]


def _overtakes(piece: _Run, trip, pool, index, planned, chain, cache) -> bool:
    """Whether joining `trip` would put the fragment on the wrong side of somebody.

    Two trips running at once have an order, and the timetable knows it: at any
    instant one of them is further along the chain than the other. If the
    fragment, merged into `trip`, would be observed ahead of a vehicle whose trip
    is scheduled *behind* it at that moment — or behind one scheduled ahead — the
    merge has invented an overtaking, which is the one thing the alignment was
    built to forbid.
    """
    mine = _scheduled_track(trip, planned, chain, cache)
    if mine is None:
        return False
    for other, (rival, its_trip) in enumerate(pool):
        if other == index or rival.end <= piece.start or rival.start >= piece.end:
            continue
        theirs = _scheduled_track(its_trip, planned, chain, cache)
        if theirs is None:
            continue
        inside = (piece.seconds >= rival.start) & (piece.seconds <= rival.end)
        if not inside.any():
            continue
        when = piece.seconds[inside]
        seen = piece.metres[inside] - np.interp(when, rival.seconds, rival.metres)
        want = np.interp(when, *mine) - np.interp(when, *theirs)
        if np.any((seen > MERGE_ORDER_TOLERANCE) & (want < -MERGE_ORDER_TOLERANCE)) or \
           np.any((seen < -MERGE_ORDER_TOLERANCE) & (want > MERGE_ORDER_TOLERANCE)):
            return True
    return False
