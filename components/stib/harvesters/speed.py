from datetime import datetime

import pandas as pd

from src.components import Harvester


class StibSegmentsSpeedHarvester(Harvester):
    """Speed of each vehicle between two consecutive vehicle-distance snapshots.

    The source is the newest snapshot only; the earlier ones arrive through the
    optional dependency on the same collector. Consuming the snapshots two by
    two as a strict source range did skipped every other pair and halved the
    cadence, and it produced an empty result whenever STIB served the same
    payload twice in a row (roughly one poll in ten), since nothing had moved
    between two identical snapshots. Here the previous snapshot is the newest
    one whose content differs from the current one, so a duplicate is measured
    against the last real position instead of against itself.
    """

    def run(self, source, stib_vehicle_distance=None):
        current = source
        previous = _last_distinct(current, stib_vehicle_distance or [])

        if previous is None:
            return None

        return compute_speeds(previous.data, previous.date, current.data, current.date)


def _last_distinct(current, earlier):
    current_data = current.data
    for row in earlier:
        if row.data != current_data:
            return row
    return None


def compute_speeds(previous_data, previous_date: datetime, current_data, current_date: datetime):
    time_delta = current_date - previous_date
    if time_delta.total_seconds() <= 0:
        return None

    try:
        df1 = pd.DataFrame(current_data)
        df2 = pd.DataFrame(previous_data)
    except ValueError:
        return None

    if "pointId" not in df1.columns or "pointId" not in df2.columns:
        return None

    keys = ["pointId", "lineId", "directionId"]
    df = df1.merge(df2, on=keys, suffixes=("", "_previous"))
    # A key seen twice in a snapshot is two vehicles: their distances cannot be paired.
    df = df.drop_duplicates(subset=keys, keep=False)
    df = df[df["distanceFromPoint_previous"] < df["distanceFromPoint"]]

    df["speed"] = (df["distanceFromPoint"] - df["distanceFromPoint_previous"]) / time_delta.total_seconds()
    df = df[keys + ["speed"]]
    df["speed"] = round(df["speed"] * 3.6, 2)

    return df.to_dict(orient="records")
