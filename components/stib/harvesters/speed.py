import pandas as pd

from src.components import Harvester


class StibSegmentsSpeedHarvester(Harvester):
    def run(self, source):
        previous = source[0]
        current = source[1]

        time_delta = current.date - previous.date

        # Read both json into pandas
        try:
            df1 = pd.DataFrame(current.data)
            df2 = pd.DataFrame(previous.data)
        except ValueError:
            return

        # Make sure pointId is in both dataframes
        if "pointId" not in df1.columns or "pointId" not in df2.columns:
            return

        # Merge on point_id, line_id and direction
        df = df1.merge(
            df2, on=["pointId", "lineId", "directionId"], suffixes=("", "_previous")
        )
        # Get duplicate rows (same point_id, line_id and direction)
        df = df.drop_duplicates(subset=["pointId", "lineId", "directionId"], keep=False)

        # Keep only rows where distanceFromPoint_previous is < distanceFromPoint
        df = df[df["distanceFromPoint_previous"] < df["distanceFromPoint"]]

        # Compute speed
        df["speed"] = (
            df["distanceFromPoint"] - df["distanceFromPoint_previous"]
        ) / time_delta.total_seconds()

        # Keep only relevant columns
        df = df[["pointId", "lineId", "directionId", "speed"]]

        # Transform speed from m/s to km/h
        df["speed"] = round(df["speed"] * 3.6, 2)

        return df.to_dict(orient="records")
