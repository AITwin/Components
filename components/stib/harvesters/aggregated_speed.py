import pandas as pd

from src.components import Harvester


class StibSegmentsAggregatedSpeedHarvester(Harvester):
    def run(self, sources):
        sources = list(([
            row.data
            for row in sources
        ]))
        sources_flat = []

        for source in sources:
            sources_flat.extend(source)
        df = pd.DataFrame.from_records(sources_flat)

        if df.empty:
            return []
        # Merge on pointId, lineId and directionId and average speed
        df = df.groupby(["pointId", "lineId", "directionId"]).mean()
        # Reset index
        df = df.reset_index()

        return df.to_dict(orient="records")
