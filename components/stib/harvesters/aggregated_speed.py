from datetime import timedelta

import pandas as pd

from src.components import Harvester

WINDOW = timedelta(minutes=10)


class StibSegmentsAggregatedSpeedHarvester(Harvester):
    """Rolling 10-minute mean of the per-segment speeds, refreshed with every speed snapshot.

    The source is the newest speed snapshot; the ones before it come from the
    optional dependency on the speed table. Averaging a source range instead
    only ever saw the rows produced since the previous run, which is a single
    snapshot, so the "aggregated" output was a copy of the speed output.
    """

    def run(self, source, stib_speed=None):
        since = source.date - WINDOW
        rows = [source] + [row for row in (stib_speed or []) if row.date >= since]

        return aggregate([row.data for row in rows])


def aggregate(snapshots):
    flat = []
    for snapshot in snapshots:
        if snapshot:
            flat.extend(snapshot)

    df = pd.DataFrame(flat)
    if df.empty:
        return []

    df = df.groupby(["pointId", "lineId", "directionId"], as_index=False)["speed"].mean()
    df["speed"] = round(df["speed"], 2)

    return df.to_dict(orient="records")
