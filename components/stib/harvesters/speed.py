from collections import Counter

from src.components import Harvester

# How many earlier polls a value may have stood before it changed and still be
# measured: STIB refreshes a vehicle's distance about every 40 s, so its runs
# are one to three 20-second polls; longer ones are a vehicle standing, whose
# speed would be an average over the wait.
MAX_RUN = 3
# Above this the reading is a feed glitch, not a bus or tram (the metro, the
# fastest, tops out near 80 km/h).
MAX_SPEED_KMH = 90


class StibSegmentsSpeedHarvester(Harvester):
    """Speed of each vehicle over its last move, measured when its distance changed.

    The source is the newest snapshot only; the earlier ones arrive through the
    optional dependency on the same collector. STIB refreshes each vehicle's
    distance about every 40 s while it is polled every 20 s, so a distance often
    stands for one extra poll before it jumps. Dividing that jump by the 20 s
    between polls made every speed about 1.55 times too high (median 18.4 km/h
    against 11.8 over two polls, 2026-09-29) and produced the 100+ km/h buses the
    API health check flagged. A move is therefore timed from the poll where the
    previous distance first appeared to the poll where the new one did.

    Every snapshot reports each vehicle's latest measured move, so a payload
    STIB serves twice repeats the same speeds rather than coming out empty.
    """

    def run(self, source, stib_vehicle_distance=None):
        snapshots = [(source.date, source.data)] + [(row.date, row.data) for row in stib_vehicle_distance or []]
        return compute_speeds(snapshots)


def _key(vehicle):
    return vehicle["pointId"], vehicle["lineId"], vehicle["directionId"]


def _distances(data) -> dict:
    # A key seen twice in a snapshot is two vehicles: their distances cannot be paired.
    counts = Counter(_key(v) for v in data)
    return {_key(v): v["distanceFromPoint"] for v in data if counts[_key(v)] == 1}


def _run_start(polls, start, key, value):
    """Index of the oldest poll, from `start` backwards, that still has `value`."""
    i = start
    while i + 1 < len(polls) and polls[i + 1][1].get(key) == value:
        i += 1
    return i


def compute_speeds(snapshots):
    """Per (pointId, lineId, directionId), the speed in km/h of the last move.

    `snapshots` are (date, vehicle-distance payload), newest first.
    """
    polls = [(date, _distances(data)) for date, data in snapshots if data]
    if len(polls) < 2:
        return None

    out = []
    for key, value in polls[0][1].items():
        current = _run_start(polls, 0, key, value)
        if current + 1 >= len(polls):
            continue                                    # no earlier value in sight
        previous_value = polls[current + 1][1].get(key)
        if previous_value is None or previous_value >= value:
            continue                                    # new at this point, or not moving forward
        previous = _run_start(polls, current + 1, key, previous_value)
        if previous + 1 >= len(polls) or previous - current > MAX_RUN:
            continue                                    # when that value appeared is out of sight
        seconds = (polls[current][0] - polls[previous][0]).total_seconds()
        if seconds <= 0:
            continue
        speed = round((value - previous_value) / seconds * 3.6, 2)
        if speed <= MAX_SPEED_KMH:
            out.append({"pointId": key[0], "lineId": key[1], "directionId": key[2], "speed": speed})
    return out
