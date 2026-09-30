"""STIB vehicles, live, each on its GTFS trip.

The punctuality harvester answers "which timetabled trip was this vehicle
running?" once a day, with the whole day in hand. This module answers it every
20 seconds with only the past: the same tracker (consecutive polls aligned
under no-overtaking, see match.py) run one poll at a time, and the vehicles on
the road right now paired with the trips that could be running.

What changes when there is no future to look at:

  * Only vehicles seen in the current poll are paired with trips. A track that
    broke off minutes ago no longer holds on to its trip, so the track that
    continues it can take it over; in the daily alignment the dead fragment
    kept the trip and the live vehicle went without.
  * The pairing minimises the total deviation instead of preserving an order
    (see _pair), because a live track has no reliable start to order it by.
  * Two stop calls are enough to compare a vehicle with a trip, not three: a
    vehicle then has its trip about a minute after leaving its first stop.
  * A pairing is sticky. The pair chosen at the previous poll costs less, so a
    trip id does not flicker between two neighbours of similar deviation.

A vehicle standing at the last stop of a trip has finished it and gives it up:
the feed keeps a vehicle laying over at its terminus in the group it arrived
in, and without this it would carry the finished trip, frozen, for up to half
an hour.

A vehicle standing at its first stop, waiting to leave, gets no trip. Handing
it the next departure from that stop was tried and was right four times out of
five whatever the window: the vehicle that makes a departure is as often one
that arrives late and turns straight round as the one waiting. A wrong trip id
is worse than none for anyone predicting arrivals from it.

Each poll yields, per vehicle, its identity (a uuid that lasts as long as the
track), its position along the line and, where one could be established, the
trip, the service date and the delay at the last stop it called at.
"""
import json
import math
import uuid
from collections import defaultdict

import numpy as np
import pandas as pd

from ..punctuality import match, network, stopcalls

BRUSSELS = "Europe/Brussels"

# A vehicle in the alignment keeps its previous trip at this fraction of the
# deviation it would otherwise cost.
STICKY = 0.5
# Minutes early weigh this much more than minutes late when a vehicle is
# compared with a trip. Where the headway is about twice the typical delay, a
# whole line fits "each vehicle 2 min late" and "each vehicle 4 min early on the
# next trip" almost equally, and once taken the shifted reading holds (sticky,
# and every new vehicle finds its trip already held). Vehicles rarely run early
# (8% of observed calls over 2 min early against 27% over 2 min late), so early
# is the reading to distrust. Measured: line 82 on 2026-09-29 went from 48% to
# 94% agreement with hindsight, and the 2026-09-28 morning peak from 91.6% to
# 92.7% precision against the daily table.
EARLY_WEIGHT = 1.5
# Trips considered for the vehicles on the road: those whose schedule overlaps
# [now - LATE, now + EARLY]. Twenty minutes late is where the daily alignment
# stops trusting a match anyway (MAX_DEVIATION_MINUTES is twelve).
LATE_SECONDS = 25 * 60
EARLY_SECONDS = 10 * 60
# Stop calls a vehicle needs before it is compared with trips (see above).
MIN_SHARED_STOPS = 2
# A standing vehicle reports no more than this many metres past its stop.
AT_STOP_METRES = stopcalls.AT_STOP_METRES
# The four metro lines report stations, not metres (stopcalls.COARSE_METRES).
# Live there is no day of observations to measure that from, so they are named.
COARSE_LINES = frozenset({"1", "2", "5", "6"})
# Lines tracked per (line, direction) rather than per (line, direction,
# destination). A metro train cannot overtake, and STIB names one terminus by
# two stop ids (Erasme 8641/8642, Stockel 8161/8162, Herrmann-Debroux 8261/8262)
# and switches between them, and to short workings, mid-run. Keyed by
# destination, one direction's trains were split into groups that each saw only
# some of them, and a track whose train left its group grabbed another train
# stations away. Replayed on 2026-09-29: jumps 433 -> 244, trains lost while
# still in the feed 263 -> 54, metro tracks 1,206 -> 752 (median life 24 -> 35
# min, a full run). Buses keep the destination: on a street one can pass another.
ANY_DESTINATION_LINES = COARSE_LINES

_METRES_PER_DEGREE_LAT = 111320.0


class _Journey:
    __slots__ = ("id", "uuid", "line", "direction", "destination", "ts", "point",
                 "point_id", "progress", "point_metres", "distance", "calls",
                 "trip", "costs")

    def __init__(self, journey_id, line, direction, destination):
        self.id = journey_id
        self.uuid = str(uuid.uuid4())
        self.line, self.direction, self.destination = line, direction, destination
        self.ts, self.point, self.point_id = [], [], []
        self.progress, self.point_metres, self.distance = [], [], []
        self.calls = []          # (point, epoch seconds), in the order called at
        self.costs = {}          # run key -> deviation, until the calls change
        self.trip = None



class Timetable:
    """The trips that can be running around a moment, in epoch seconds.

    A Brussels service day runs past midnight (a night bus at 01:30 is 25:30 of
    the day before), so the trips of two service days are kept: the local date
    and the one before it. Each day is built once and kept while it is one of
    the two, so crossing midnight builds one day, not two.
    """

    _TABLES = ("routes", "trips", "stop_times", "calendar", "calendar_dates")
    _STOP_TIMES = ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"]

    def __init__(self, gtfs: dict):
        # Only what match.timetable reads: stop_times is two million rows, and
        # the tracker holds this for as long as the timetable is current.
        self.gtfs = {name: gtfs[name] for name in self._TABLES if name in gtfs}
        self.gtfs["stop_times"] = gtfs["stop_times"][self._STOP_TIMES]
        self.days = {}                      # date -> (runs, by_group)
        self.runs, self.by_group = {}, {}
        routes = gtfs["routes"].copy()
        routes["route_short_name"] = routes.route_short_name.astype(str)
        self.route_id = {r.route_short_name: str(r.route_id) for r in routes.itertuples()}
        self.route_color = {
            r.route_short_name: "#" + str(r.route_color).strip().lstrip("#").upper()
            for r in routes.itertuples() if isinstance(r.route_color, str) and r.route_color.strip()
        }

    def ensure(self, now: float):
        local = pd.Timestamp(now, unit="s", tz="UTC").tz_convert(BRUSSELS)
        wanted = (local.date() - pd.Timedelta(days=1), local.date())
        if set(self.days) == set(wanted):
            return
        self.days = {day: self.days.get(day) or self._build(day) for day in wanted}
        self.runs, groups = {}, defaultdict(list)
        for runs, by_group in self.days.values():
            self.runs.update(runs)
            for key, run_keys in by_group.items():
                groups[key].extend(run_keys)
        self.by_group = {k: sorted(v, key=lambda key: self.runs[key]["start"])
                         for k, v in groups.items()}

    def _build(self, day):
        times = match.timetable(self.gtfs, day)
        origin = match.service_day_origin(day).timestamp()
        start_date = day.strftime("%Y%m%d")
        times = times.assign(arrival=times.arrival_time + origin,
                             departure=times.departure_time + origin)
        times = times.sort_values(["trip_id", "stop_sequence"])
        if not len(times):
            # A timetable published today may no longer hold yesterday's service.
            return {}, {}

        trips = np.asarray(times.trip_id.astype(str), dtype=object)
        bounds = np.flatnonzero(np.r_[True, trips[1:] != trips[:-1]])
        ends = np.r_[bounds[1:], len(times)]
        arrival = times.arrival.values
        departure = times.departure.values
        points = np.asarray(times.point, dtype=object)
        stops = np.asarray(times.stop_id.astype(str), dtype=object)
        seq = times.stop_sequence.values
        departure_time = times.departure_time.values
        lines = np.asarray(times.route_short_name.astype(str), dtype=object)
        directions = times.direction_id.astype(int).values
        route_ids = np.asarray(times.route_id.astype(str), dtype=object)

        # One entry per trip run: (start_date, trip_id). The same trip id runs on
        # two service days when its service does, and those are two runs.
        runs, by_group = {}, defaultdict(list)
        for a, b in zip(bounds, ends):
            key = (start_date, trips[a])
            seconds = int(departure_time[a])
            run = {
                "trip_id": trips[a],
                "start_date": start_date,
                "start_time": f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}",
                "route_id": route_ids[a],
                "line": lines[a],
                "direction": int(directions[a]),
                "start": float(departure[a]),
                "end": float(arrival[b - 1]),
                "first_point": points[a],
                "last_point": points[b - 1],
                "points": points[a:b],
                "stops": stops[a:b],
                "sequence": seq[a:b],
            }
            # A loop visits its first stop again at the end, so a point can
            # have two scheduled times; a call is compared with the nearer.
            at = defaultdict(list)
            for point, seconds in zip(points[a:b], arrival[a:b]):
                at[point].append(float(seconds))
            run["at"] = dict(at)
            runs[key] = run
            by_group[(run["line"], run["direction"])].append(key)
        return runs, dict(by_group)

    def around(self, line, direction, now):
        return [k for k in self.by_group.get((line, direction), ())
                if self.runs[k]["start"] <= now + EARLY_SECONDS
                and self.runs[k]["end"] >= now - LATE_SECONDS]


class Geometry:
    """Where a vehicle is on the map: `distance` metres past `point` along the hop."""

    def __init__(self, lines: network.LineNetwork, segments: pd.DataFrame = None, gtfs: dict = None):
        self.lines = lines
        self.shapes = {}
        # The stop a vehicle is heading to is the next one on its own pattern.
        # The line's chain merges every pattern, so on a branching line the stop
        # after a point in the chain can be on another branch, kilometres away,
        # and the vehicle was drawn racing towards it.
        self.following, self.usual = _successors(gtfs) if gtfs is not None else ({}, {})
        if segments is not None and len(segments):
            for row in segments.itertuples():
                line = row.geometry
                if isinstance(line, str):
                    line = json.loads(line)
                if len(line) >= 2:
                    key = (str(row.line_id), network.normalise_stop(row.start),
                           network.normalise_stop(row.end))
                    self.shapes.setdefault(key, line)

    def position(self, line, direction, point, distance, destination=None):
        here = self.lines.coords.get(point)
        if here is None:
            return here
        following = (self.following.get((line, direction, destination, point))
                     or self.usual.get((line, direction, point)))
        if following is None and self.usual:
            # The last stop of every pattern: a vehicle past it is turning or
            # heading for the depot, not towards whatever the chain lists next.
            return here
        if following is None:
            chain = self.lines.chains.get((line, direction))
            index = self.lines.index.get((line, direction), {}).get(point)
            if chain is None or index is None or index + 1 >= len(chain):
                return here
            following = chain[index + 1]
        shape = self.shapes.get((line, point, following))
        if shape is None:
            there = self.lines.coords.get(following)
            if there is None:
                return here
            shape = [here, there]
        hop = self.lines.hop_length.get((line, direction, point), 400.0)
        return _along(shape, min(max(distance, 0) / hop, 1.0) if hop else 0.0)


def _successors(gtfs):
    """(line, direction, last point, point) -> the next point on the patterns
    ending there, and (line, direction, point) -> the most common next point."""
    routes = gtfs["routes"][["route_id", "route_short_name"]].astype({"route_short_name": str})
    trips = gtfs["trips"][["trip_id", "route_id", "direction_id"]].merge(routes, on="route_id")
    times = gtfs["stop_times"][["trip_id", "stop_id", "stop_sequence"]].sort_values(["trip_id", "stop_sequence"])
    trip_ids = np.asarray(times.trip_id.astype(str), dtype=object)
    points = np.asarray(times.stop_id.astype(str).map(network.normalise_stop), dtype=object)
    starts = np.flatnonzero(np.r_[True, trip_ids[1:] != trip_ids[:-1]]) if len(times) else []
    ends = np.r_[starts[1:], len(times)] if len(times) else []
    owner = {str(t): (str(l), int(d)) for t, l, d in
             zip(trips.trip_id, trips.route_short_name, trips.direction_id)}
    counts = defaultdict(lambda: defaultdict(int))
    for pattern, key in {(tuple(points[a:b]), owner.get(trip_ids[a])) for a, b in zip(starts, ends)}:
        if key is None:
            continue
        for a, b in zip(pattern, pattern[1:]):
            if a != b:
                counts[key + (pattern[-1], a)][b] += 1
                counts[key + (a,)][b] += 1
    following = {k: max(v, key=lambda b: (v[b], b)) for k, v in counts.items() if len(k) == 4}
    usual = {k: max(v, key=lambda b: (v[b], b)) for k, v in counts.items() if len(k) == 3}
    return following, usual


def _along(line, fraction):
    scale = math.cos(math.radians(50.85)) * _METRES_PER_DEGREE_LAT
    lengths = [math.hypot((x1 - x0) * scale, (y1 - y0) * _METRES_PER_DEGREE_LAT)
               for (x0, y0), (x1, y1) in zip(line, line[1:])]
    total = sum(lengths)
    if total == 0:
        return tuple(line[0])
    goal = fraction * total
    for (x0, y0), (x1, y1), length in zip(line, line[1:], lengths):
        if goal <= length and length > 0:
            f = goal / length
            return (x0 + (x1 - x0) * f, y0 + (y1 - y0) * f)
        goal -= length
    return tuple(line[-1])


class LiveTracker:
    """Feed it polls in time order; it keeps the vehicles and their trips."""

    def __init__(self, gtfs: dict, segments: pd.DataFrame = None, observations: pd.DataFrame = None):
        self.lines = network.LineNetwork.from_gtfs(gtfs, segments, observations)
        self.timetable = Timetable(gtfs)
        self.geometry = Geometry(self.lines, segments, gtfs)
        self.live = defaultdict(list)       # (line, direction, destination) -> [_Journey]
        self.last_ts = None
        self.seed = 0

    # -- one poll -------------------------------------------------------------

    def step(self, observations: pd.DataFrame, now: float, assign: bool = True):
        """Advance by one poll. `observations` has the raw feed's columns
        (line_id, direction_id, point_id, distance_from_point) for one instant."""
        if self.last_ts is not None and now <= self.last_ts:
            return None
        self.last_ts = now
        located = self.lines.locate(observations) if len(observations) else observations
        seen = []
        if len(located):
            # Plain lists: a poll is ~650 rows in ~250 groups, and pandas'
            # per-group and per-row machinery costs more than the tracking.
            line = [str(v) for v in located.line_id.tolist()]
            direction = [int(v) for v in located.direction.tolist()]
            destination = [str(v) for v in located.destination.tolist()]
            rows = list(zip(
                [str(v) for v in located.point.tolist()],
                [str(v) for v in located.point_id.tolist()],
                [float(v) for v in located.progress.tolist()],
                [float(v) for v in located.point_metres.tolist()],
                [float(v) for v in located.distance_from_point.tolist()],
                destination,
            ))
            groups = defaultdict(list)
            for i in range(len(rows)):
                grouped = None if line[i] in ANY_DESTINATION_LINES else destination[i]
                groups[(line[i], direction[i], grouped)].append(i)
            for key, members in groups.items():
                members.sort(key=lambda i: rows[i][2])
                seen.extend(self._track(key, [rows[i] for i in members], now))
        # Tracks unseen for longer than the tracker's timeout are gone.
        for key in list(self.live):
            self.live[key] = [j for j in self.live[key] if now - j.ts[-1] <= match.TRACK_TIMEOUT]
            if not self.live[key]:
                del self.live[key]
        if not assign:
            return None
        self.timetable.ensure(now)
        self._assign(seen, now)
        return [self._describe(j, now) for j in seen]

    def _track(self, key, rows, now):
        """`rows` are (point, point_id, progress, point_metres, distance,
        destination) of one (line, direction, destination) group, by progress;
        the group's destination is None on ANY_DESTINATION_LINES."""
        line, direction, _ = key
        live = sorted((j for j in self.live[key] if now - j.ts[-1] <= match.TRACK_TIMEOUT),
                      key=lambda j: j.progress[-1])
        here = np.array([row[2] for row in rows])
        slack = match.COARSE_SLACK if line in COARSE_LINES else match.ADVANCE_SLACK
        pairs = []
        if live and len(here):
            costs = np.full((len(live), len(here)), np.inf)
            for i, j in enumerate(live):
                elapsed = max(now - j.ts[-1], 1.0)
                advance = here - j.progress[-1]
                allowed = match.MAX_SPEED * elapsed + slack
                ok = (advance >= -match.BACKWARD_TOLERANCE) & (advance <= allowed)
                costs[i, ok] = np.abs(advance[ok]) / allowed + 0.15 * (elapsed > 45)
            pairs, _ = match.align(costs)
        owner = {b: live[a] for a, b in pairs}
        seen = []
        for index, row in enumerate(rows):
            journey = owner.get(index)
            if journey is None:
                self.seed += 1
                journey = _Journey(f"{line}-{direction}-{row[5]}-{self.seed:06d}",
                                   line, direction, row[5])
                self.live[key].append(journey)
            journey.destination = row[5]
            self._observe(journey, row, now)
            seen.append(journey)
        return seen

    def _observe(self, journey, row, now):
        """Append a sighting, and read a stop call off it when there is one.

        The same reading as stopcalls.journey_calls, done as the sightings
        arrive rather than over a finished journey: a call is where the reported
        point changes, dated by where the vehicle crossed the stop between the
        two polls either side; a stop the track began at is dated by when the
        vehicle left it.
        """
        point, point_id, progress, point_metres, distance = row[:5]
        count = len(journey.ts)
        moved_on = count == 0 or journey.point[-1] != point
        was_standing = count > 0 and journey.distance[-1] <= AT_STOP_METRES
        journey.ts.append(now)
        journey.point.append(point)
        journey.point_id.append(point_id)
        journey.progress.append(progress)
        journey.point_metres.append(point_metres)
        journey.distance.append(distance)
        if count == 0:
            return
        before = count - 1
        gap = now - journey.ts[before]
        if moved_on:
            if gap <= stopcalls.MAX_BRIDGE_SECONDS:
                approach = None
                if before:
                    approach = (journey.progress[before] - journey.progress[before - 1],
                                journey.ts[before] - journey.ts[before - 1])
                arrival = stopcalls._crossing(
                    journey.ts[before], now, journey.progress[before],
                    journey.progress[-1], journey.point_metres[-1], approach)
                self._call(journey, point, min(arrival, now))
        elif was_standing and distance > AT_STOP_METRES \
                and not any(p == point for p, _ in journey.calls[-1:]):
            # Leaving a stop it was already at when the track began.
            settled = journey.ts[before]
            self._call(journey, point,
                       0.5 * (settled + now) if gap <= stopcalls.MAX_BRIDGE_SECONDS else settled)

    @staticmethod
    def _call(journey, point, seconds):
        journey.calls.append((point, seconds))
        journey.costs = {}

    def adopt(self, vehicles, when: float):
        """Carry identities and trips over from a snapshot published before a
        rebuild, so a restart does not rename every vehicle.

        `vehicles` are the features' properties of the snapshot taken at `when`;
        a replayed track that was at exactly the same place at that poll is the
        same vehicle. Positions two vehicles share are left alone.
        """
        def key(line, destination, point, distance):
            return (str(line), str(destination), str(point), float(distance))

        published = defaultdict(list)
        for vehicle in vehicles:
            published[key(vehicle["lineId"], vehicle["directionId"], vehicle["pointId"],
                          vehicle["distanceFromPoint"])].append(vehicle)
        replayed = defaultdict(list)
        for journeys in self.live.values():
            for journey in journeys:
                if when in journey.ts:
                    i = journey.ts.index(when)
                    replayed[key(journey.line, journey.destination, journey.point_id[i],
                                 journey.distance[i])].append(journey)
        adopted = 0
        for k, journeys in replayed.items():
            if len(journeys) == 1 and len(published.get(k, ())) == 1:
                vehicle = published[k][0]
                journeys[0].uuid = vehicle["uuid"]
                if vehicle.get("tripId"):
                    journeys[0].trip = (vehicle["startDate"], vehicle["tripId"])
                adopted += 1
        return adopted

    # -- trips ----------------------------------------------------------------

    def _assign(self, seen, now):
        by_group = defaultdict(list)
        for journey in seen:
            by_group[(journey.line, journey.direction)].append(journey)
        for (line, direction), journeys in by_group.items():
            runs = self.timetable.around(line, direction, now)
            comparable = [j for j in journeys if _called(j) >= MIN_SHARED_STOPS]
            if comparable and runs:
                costs = np.full((len(comparable), len(runs)), np.inf)
                for i, journey in enumerate(comparable):
                    for k, run_key in enumerate(runs):
                        # Standing at the last stop of a run is having finished
                        # it: a vehicle laying over at its terminus is not still
                        # on the trip it arrived with, and must not hold it.
                        if journey.point[-1] == self.timetable.runs[run_key]["last_point"]:
                            continue
                        if run_key not in journey.costs:
                            journey.costs[run_key] = _deviation(
                                journey.calls, self.timetable.runs[run_key]["at"])
                        cost = journey.costs[run_key]
                        if cost is None or cost > match.MAX_DEVIATION_MINUTES:
                            continue
                        costs[i, k] = cost * STICKY if journey.trip == run_key else cost
                # In the daily alignment an unpaired journey and an unpaired trip
                # each cost the gap, so a pair is worth making up to twice it.
                pairs = _pair(costs, 2 * match.TRIP_GAP_COST)
                chosen = {comparable[i].id: runs[k] for i, k in pairs}
            else:
                chosen = {}
            for journey in journeys:
                journey.trip = chosen.get(journey.id)

    # -- output ---------------------------------------------------------------

    def _describe(self, journey, now):
        out = {
            "uuid": journey.uuid,
            "lineId": journey.line,
            "directionId": journey.destination,
            "direction": journey.direction,
            "pointId": journey.point_id[-1],
            "distanceFromPoint": journey.distance[-1],
            "color": self.timetable.route_color.get(journey.line),
            "routeId": self.timetable.route_id.get(journey.line),
            "timestamp": now,
            "tripId": None, "startDate": None, "startTime": None,
            "delay": None, "status": _status(journey),
            "stopId": None, "stopSequence": None,
        }
        run = self.timetable.runs.get(journey.trip) if journey.trip else None
        if run is not None:
            out.update(tripId=run["trip_id"], routeId=run["route_id"],
                       startDate=run["start_date"], startTime=run["start_time"])
            out["delay"] = _delay(journey, run, now)
            stop = _stop_in_trip(journey, run) if out["status"] else None
            if stop is not None:
                out["stopId"], out["stopSequence"] = str(run["stops"][stop]), int(run["sequence"][stop])
        out["geometry"] = self.geometry.position(journey.line, journey.direction,
                                                 journey.point[-1], journey.distance[-1],
                                                 network.normalise_stop(journey.destination))
        return out


def _status(journey):
    """STOPPED_AT or IN_TRANSIT_TO, or None where the feed cannot tell: the
    metro reports the station it is at or has just left, never metres, so
    standing and running look the same."""
    if journey.line in COARSE_LINES:
        return None
    return "STOPPED_AT" if journey.distance[-1] <= AT_STOP_METRES else "IN_TRANSIT_TO"


def _stop_in_trip(journey, run):
    """Index in the run of the stop the vehicle is at, or heading to."""
    points = list(run["points"])
    point = journey.point[-1]
    if point not in points:
        return None
    index = points.index(point)
    if journey.distance[-1] > AT_STOP_METRES and index + 1 < len(points):
        return index + 1
    return index


def _pair(costs, gap_cost):
    """Minimum-cost pairing of vehicles with trips, each free to stay unpaired
    at `gap_cost`.

    Not the order-preserving alignment the daily assignment uses. That orders
    journeys by when they began and trips by when they depart, and a live
    vehicle has no reliable "when it began": a track picked up mid-route, or a
    short-turn trip that departs from the middle of the line later than a
    full-length trip running ahead of it, puts the two orders out of step, and
    the alignment then hands out neighbouring trips. Minimising the total
    deviation keeps what no-overtaking was for, since swapping two vehicles'
    trips makes both fit worse.
    """
    from scipy.optimize import linear_sum_assignment

    n, m = costs.shape
    padded = np.full((n, m + n), 1e9)
    padded[:, :m] = np.where(np.isfinite(costs), costs, 1e9)
    padded[np.arange(n), m + np.arange(n)] = gap_cost
    rows, cols = linear_sum_assignment(padded)
    return [(i, k) for i, k in zip(rows, cols) if k < m and np.isfinite(costs[i, k])]


def _called(journey):
    return len({point for point, _ in journey.calls})


def _nearest(scheduled, seconds):
    return min(scheduled, key=lambda s: abs(s - seconds))


def _weighted_gap(seconds, scheduled):
    return seconds - scheduled if seconds >= scheduled else (scheduled - seconds) * EARLY_WEIGHT


def _deviation(calls, at):
    """match._deviation over a live track: the median of |observed - scheduled|
    in minutes over the stops both share, penalised for the calls the trip does
    not explain, or None under MIN_SHARED_STOPS. Early counts EARLY_WEIGHT
    times late. A loop's repeated stop is compared with its nearer visit."""
    gaps, shared = [], set()
    for point, seconds in calls:
        scheduled = at.get(point)
        if scheduled is None:
            continue
        gaps.append(min(_weighted_gap(seconds, s) for s in scheduled))
        shared.add(point)
    if len(shared) < MIN_SHARED_STOPS:
        return None
    coverage = len(gaps) / len(calls)
    return float(np.median(gaps)) / 60.0 + 3.0 * (1.0 - coverage)


def _delay(journey, run, now):
    """Seconds late at the last stop the vehicle called at that the trip serves."""
    for point, seconds in reversed(journey.calls):
        scheduled = run["at"].get(point)
        if scheduled is None:
            continue
        nearest = _nearest(scheduled, seconds)
        if abs(seconds - nearest) <= match.MAX_DEVIATION_MINUTES * 60 + LATE_SECONDS:
            return int(round(seconds - nearest))
        return None
    return None
