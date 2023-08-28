import json
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from src.components import Harvester
from datetime import datetime


class AnomalyHarvester(Harvester):
    def run(self, sources, micromobility_area, bolt_daily_prediction, **kwargs):
        # Load the GeoDataFrame directly from the JSON data
        station_locations = gpd.GeoDataFrame.from_features(
            json.loads(micromobility_area.data)["features"], crs="EPSG:4326"
        )

        # Convert sources data to GeoDataFrame
        time_under_consideration = self.nearest_time(bolt_daily_prediction.data, sources[-1].date)
        ebike_dataframe = pd.json_normalize(sources[-1].data["features"])
        ebike_dataframe["geometry_point"] = ebike_dataframe["geometry.coordinates"].apply(Point)
        ebike_geodataframe = gpd.GeoDataFrame(ebike_dataframe, geometry="geometry_point", crs="EPSG:4326")

        # Perform the spatial join
        joined_dataframe = gpd.sjoin(station_locations, ebike_geodataframe, how="left", predicate="contains")

        # Group by poly_id and count occurrences
        aggregated_ebikes = joined_dataframe.groupby(["poly_id"])["properties.bike_id"].count().reset_index()
        aggregated_ebikes.rename(columns={"properties.bike_id": "ebike_availibility"}, inplace=True)

        # Convert the result to a dictionary
        result = aggregated_ebikes.set_index("poly_id").to_dict(orient="index")

        return result

    def nearest_time(self, predictions, target_time):
        # Initialize variables to keep track of the nearest time and its time difference
        nearest_time = None
        min_time_difference = float("inf")

        for timestamp in predictions.keys():
            # Convert the timestamp string to a datetime object
            timestamp_dt = datetime.strptime(timestamp, "%Y/%m/%d %H:%M:%S")

            # Calculate the time difference
            time_difference = abs((timestamp_dt - target_time).total_seconds())

            # Check if this is the closest time found so far
            if time_difference < min_time_difference:
                min_time_difference = time_difference
                nearest_time = timestamp

        return datetime.strptime(nearest_time, "%Y/%m/%d %H:%M:%S")
