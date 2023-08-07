import json
from collections import defaultdict
from typing import Dict, List, Tuple

import geopandas as gpd
import pandas as pd

from src.components import Harvester


class StibSegmentsSpeedHarvester(Harvester):

    def run(self, sources: List, stib_segments):
        segment_gdf = gpd.GeoDataFrame.from_features(stib_segments.data["features"])

        def get_features_from_component_result(component_result):
            features_timestamp = component_result.timestamp

            for feature in component_result.data["features"]:
                feature["properties"]["timestamp"] = features_timestamp

            return component_result.data["features"]

        # Concatenate all the dataframes
        geo_df = pd.concat(
            [
                gpd.GeoDataFrame.from_features(
                    get_features_from_component_result(q)
                )
                for q in sources
            ]
        )

        # If geo_df is empty (typically when there are no vehicles), return empty result
        if geo_df.empty:
            return

            # Max number of datapoints per trip
        expected_min_number_of_datapoint_per_trip = (
                geo_df.groupby("uuid").size().max() / 2
        )

        def filter_by_line_id(x):
            return len(x) >= expected_min_number_of_datapoint_per_trip

        # Drop all uuids if less than expected_min_number_of_datapoint_per_trip
        geo_df = geo_df.groupby("uuid").filter(filter_by_line_id)

        speeds: Dict[Tuple[str, str, str], List[float]] = defaultdict(list)
        average_speeds: Dict[Tuple[str, str, str], List[float]] = defaultdict(list)

        # Group by uuid, compute delta with shift for both timestamp and distanceFromPoint
        for (uuid, line, direction, point), group in geo_df.groupby(
                ["uuid", "lineId", "direction", "pointId"]
        ):
            # Get min and max timestamp
            min_timestamp = group["timestamp"].min()
            max_timestamp = group["timestamp"].max()

            # Get min and max distance from point
            min_distance_from_point = group["distanceFromPoint"].min()
            max_distance_from_point = group["distanceFromPoint"].max()

            # Get average speed
            timestamp_delta = max_timestamp - min_timestamp
            distance_delta = max_distance_from_point - min_distance_from_point
            average_speed = (
                (distance_delta / timestamp_delta * 3.6) if timestamp_delta > 0 else 0
            )  # m/s to km/h

            # Compute speed using shift
            group["speed"] = (
                    (group["distanceFromPoint"].shift(-1) - group["distanceFromPoint"])
                    / (group["timestamp"].shift(-1) - group["timestamp"])
                    * 3.6
            )

            # Exclude where speed is 0
            group = group[group["speed"] != 0]

            # Add to the dict
            speeds[(line, direction, point)].append(group["speed"].mean())
            average_speeds[(line, direction, point)].append(average_speed)

        def get_average_speed_for_segment(segment):
            data = speeds.get(
                (
                    segment["line_id"],
                    segment["direction"],
                    segment["start"],
                ),
                None,
            )

            if data:
                # Return average speed, round
                return round(sum(data) / len(data), 2)

            return None

        # Compute average speed by segment
        segment_gdf["averageSpeed"] = segment_gdf.apply(
            get_average_speed_for_segment, axis=1
        )

        # Rename column line_id into lineId
        segment_gdf = segment_gdf.rename({"line_id": "lineId"})

        # Return only one result for the whole granularity (
        #   aggregate of all data between timestamp and timestamp + granularity
        #   into one result.
        return json.loads(segment_gdf.to_json())
