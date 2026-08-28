#!/usr/bin/env python3
"""STIB's lines as ordered chains of stop points, so a vehicle has a position.

The realtime feed locates a vehicle as `(lineId, pointId, distanceFromPoint)`:
so many metres past one of STIB's own stop points, heading for `directionId`,
which is not a direction bit but the point the vehicle is running to — there are
418 of them across 74 lines, because every short turn and depot run names its own
destination.

Turning that into something orderable needs a stop order per (line, direction),
and three published tables offer one. Two are not good enough:

  * `/stib/segments` carries a `distance` field that looks like cumulative metres
    and is not — on line 1 it makes the line 22.7 km where the same table's own
    geometry measures 12.5 km, at no constant ratio. Its point ids also miss 16%
    of what the feed reports.
  * `/stib/stops` misses 9%.
  * The GTFS covers 98.5% of the point references the feed makes, and it is what
    the output has to be expressed in anyway.

So the chains are built from the GTFS. One line and direction runs several stop
patterns — a full run, short turns, branches, a median of 3 and up to 29 — and
the longest is a superset of the others in only 69 of 175 cases, so no single
pattern can stand for the line. They are merged instead: every pattern is a path
through the same stop graph, and a topological order of that graph is an order
all of them agree with.

Position along a chain is cumulative metres: the hop lengths up to a vehicle's
point, plus how far past it the feed says it is. Counting in stops instead — index
plus fraction of a hop — is tempting and wrong, because a merged chain contains
stops any one trip skips, so a vehicle crossing a branch it does not serve appears
to leap several units in one poll and a tracker that bounds movement per poll cuts
its journey in half there. In metres the same leap is the ordinary distance it
really covered.
"""
import re
from collections import defaultdict

import numpy as np
import pandas as pd

# GTFS writes the same stop as `7972B` or `0470F` where the feed says `7972` and
# `470`: a quay letter and zero padding. Stripping both maps every point id the
# feed uses onto a GTFS stop.
_SUFFIX = re.compile(r"[A-Za-z]+$")


def normalise_stop(stop_id) -> str:
    bare = _SUFFIX.sub("", str(stop_id)).lstrip("0")
    return bare or "0"


def _topological_chain(patterns):
    """One stop order consistent with every pattern, longest pattern as tie-break.

    Kahn's algorithm over the edges the patterns imply, breaking ties towards the
    order of the longest pattern so a branch does not get interleaved with the
    trunk arbitrarily. A cycle — a line that visits a stop twice, which some STIB
    loops do — cannot be ordered at all; the longest pattern is used alone then,
    and stops outside it are appended so nothing is lost.

    Every choice here is broken deterministically, and that is not cosmetic. The
    patterns arrive as a set, several of them commonly tie for longest, and
    picking one by set-iteration order made the chains — and so the placement,
    and so a handful of trip matches — depend on the interpreter's hash seed.
    Rebuilding months of history is only worth anything if the same day rebuilds
    the same way, so the longest pattern is chosen by (length, contents) and the
    leftovers are appended in sorted order.
    """
    longest = max(patterns, key=lambda pattern: (len(pattern), pattern))
    rank = {stop: i for i, stop in enumerate(longest)}

    successors, indegree = defaultdict(set), defaultdict(int)
    nodes = set()
    for pattern in patterns:
        nodes.update(pattern)
        for a, b in zip(pattern, pattern[1:]):
            if a != b and b not in successors[a]:
                successors[a].add(b)
                indegree[b] += 1
    for node in nodes:
        indegree.setdefault(node, 0)

    import heapq
    ready = [(rank.get(n, len(rank)), n) for n in nodes if indegree[n] == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        _, node = heapq.heappop(ready)
        order.append(node)
        for nxt in successors[node]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                heapq.heappush(ready, (rank.get(nxt, len(rank)), nxt))

    if len(order) != len(nodes):                       # a cycle: fall back
        order = list(longest) + sorted(n for n in nodes if n not in rank)
    return order


class LineNetwork:
    """Per (line, direction): the stop order, and how long each hop is."""

    def __init__(self, chains, hop_length, coords=None, names=None):
        self.chains = chains                            # (line, dir) -> [point]
        self.index = {key: {p: i for i, p in enumerate(points)}
                      for key, points in chains.items()}
        self.hop_length = hop_length                    # (line, dir, point) -> m
        self.metres = {}                                # (line, dir, point) -> m
        for key, points in chains.items():
            run = 0.0
            for point in points:
                self.metres[key + (point,)] = run
                run += hop_length.get(key + (point,), 0.0)
        self.coords = coords or {}
        self.names = names or {}
        self.directions = defaultdict(list)
        for line, direction in chains:
            self.directions[line].append(direction)

    # -- construction --------------------------------------------------------

    @classmethod
    def from_gtfs(cls, gtfs, segments=None, observations=None):
        routes = gtfs["routes"].copy()
        routes["route_short_name"] = routes.route_short_name.astype(str)
        trips = gtfs["trips"].merge(routes[["route_id", "route_short_name"]], on="route_id")
        times = gtfs["stop_times"].copy()
        times["p"] = times.stop_id.astype(str).map(normalise_stop)
        times = times.merge(trips[["trip_id", "route_short_name", "direction_id"]],
                            on="trip_id")
        times = times.sort_values(["trip_id", "stop_sequence"])

        patterns = times.groupby("trip_id").p.apply(tuple)
        owner = trips.set_index("trip_id")[["route_short_name", "direction_id"]]
        frame = pd.DataFrame({"pattern": patterns}).join(owner)

        chains = {}
        for (line, direction), rows in frame.groupby(["route_short_name", "direction_id"]):
            chains[(str(line), int(direction))] = _topological_chain(
                sorted(set(rows.pattern)))

        stops = gtfs["stops"].copy()
        stops["p"] = stops.stop_id.astype(str).map(normalise_stop)
        stops = stops.drop_duplicates("p").set_index("p")
        coords = {p: (r.stop_lon, r.stop_lat) for p, r in stops.iterrows()}
        names = stops.stop_name.astype(str).to_dict()

        return cls(chains, cls._hop_lengths(chains, coords, segments, observations),
                   coords, names)

    @staticmethod
    def _hop_lengths(chains, coords, segments, observations):
        """How many metres `distanceFromPoint` can reach inside each hop.

        Only used to turn metres into a fraction of a hop, so it need not be a
        true road distance — it needs to be the same quantity the feed counts in.
        The feed itself is the best witness: the largest `distanceFromPoint` ever
        seen at a point is about 0.90 of the hop ahead (it stops one poll short of
        the end), so where a hop was observed enough times its own observations
        set its length. Otherwise `/stib/segments` geometry, and failing that the
        straight line between the two stops with a detour allowance.
        """
        observed = {}
        if observations is not None:
            top = (observations.groupby(["line_id", "point_id"])
                   .distance_from_point.quantile(0.995))
            observed = {(str(l), str(p)): float(v) / 0.90
                        for (l, p), v in top.items() if v > 0}

        published = {}
        if segments is not None:
            for row in segments.itertuples():
                key = (str(row.line_id), normalise_stop(row.start))
                published[key] = max(published.get(key, 0.0), float(row.length_m))

        lengths = {}
        for (line, direction), points in chains.items():
            for i, point in enumerate(points[:-1]):
                metres = observed.get((line, point)) or published.get((line, point))
                if not metres:
                    a, b = coords.get(point), coords.get(points[i + 1])
                    metres = 1.25 * _crow(a, b) if a and b else 400.0
                lengths[(line, direction, point)] = max(metres, 50.0)
        return lengths

    # -- placing an observation ---------------------------------------------

    def resolve(self, line, destination, point):
        """Which of the line's chains a vehicle is on, or None.

        The chain must hold the point the vehicle is at and, ahead of it, the
        point it is running to. Where the destination is unknown to the GTFS —
        13% of observations name a terminus no timetabled trip ends at, depot
        runs mostly — the chain is taken only if exactly one of the two holds the
        vehicle's own point. Anything still ambiguous is left unplaced rather
        than guessed: a vehicle put on the wrong chain runs backwards through it
        and poisons every journey near it.
        """
        holding = [d for d in self.directions.get(line, ())
                   if point in self.index[(line, d)]]
        if not holding:
            return None
        ahead = [d for d in holding
                 if self.index[(line, d)].get(destination, -1) >= self.index[(line, d)][point]]
        if len(ahead) == 1:
            return ahead[0]
        if ahead:                       # both chains could serve it: take the
            return min(                 # one with least of the run left
                ahead,
                key=lambda d: self.index[(line, d)][destination] - self.index[(line, d)][point],
            )
        return holding[0] if len(holding) == 1 else None

    def locate(self, observations: pd.DataFrame) -> pd.DataFrame:
        """Add `point`, `destination`, `direction` and `progress`.

        `progress` is metres from the start of the chain — monotone increasing as
        the vehicle runs, and directly comparable between two vehicles on it.
        `point_metres` is where the vehicle's own stop point sits, which is where
        a stop call happens.
        """
        out = observations.copy()
        out["point"] = out.point_id.map(normalise_stop)
        out["destination"] = out.direction_id.map(normalise_stop)

        triples = out[["line_id", "destination", "point"]].drop_duplicates()
        direction = {
            (r.line_id, r.destination, r.point):
                self.resolve(r.line_id, r.destination, r.point)
            for r in triples.itertuples()
        }
        keys = list(zip(out.line_id, out.destination, out.point))
        out["direction"] = [direction[k] for k in keys]
        out = out[out.direction.notna()].copy()
        out["direction"] = out.direction.astype("int8")

        triples = list(zip(out.line_id, out.direction, out.point))
        out["point_metres"] = [self.metres[k] for k in triples]
        length = np.array([self.hop_length.get(k, 400.0) for k in triples])
        past = np.minimum(out.distance_from_point.values, length * 0.999)
        out["progress"] = out.point_metres.values + past
        return out


def _crow(a, b):
    return float(np.hypot((b[0] - a[0]) * 70300.0, (b[1] - a[1]) * 111320.0))


# `load()` lived here and pulled its own inputs from the API. Inside a harvester
# the inputs arrive as declared dependencies, so the caller builds the network
# with `LineNetwork.from_gtfs(gtfs, segments, observations)` directly.
