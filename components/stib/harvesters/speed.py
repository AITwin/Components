import pandas as pd

from src.components import Harvester


class StibSegmentsSpeedHarvester(Harvester):
    def run(self, source, stib_vehicle_distance):
        if not stib_vehicle_distance:
            return

        previous = stib_vehicle_distance[0]

        time_delta = source.date - previous.date

        # Read both json into pandas
        df1 = pd.DataFrame(source.data)
        df2 = pd.DataFrame(previous.data)

        # Merge on point_id, line_id and direction
        df = df1.merge(df2, on=["pointId", "lineId", "directionId"], suffixes=("", "_previous"))
        # Get duplicate rows (same point_id, line_id and direction)
        df = df.drop_duplicates(subset=["pointId", "lineId", "directionId"], keep=False)

        # Keep only rows where distanceFromPoint_previous is < distanceFromPoint
        df = df[df["distanceFromPoint_previous"] < df["distanceFromPoint"]]

        # Compute speed
        df["speed"] = (df["distanceFromPoint"] - df["distanceFromPoint_previous"]) / time_delta.total_seconds()

        # Keep only relevant columns
        df = df[["pointId", "lineId", "directionId", "speed"]]

        # Transform speed from m/s to km/h
        df["speed"] = round(df["speed"] * 3.6,2)

        return df.to_dict(orient="records")
