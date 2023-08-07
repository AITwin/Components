import json

import geopandas as gpd
import pandas as pd
import requests
import shapely

from src.components import Collector


class BoltVehiclePositionCollector(Collector):
    def run(self):
        endpoint = "https://mds.bolt.eu/gbfs/2/336/free_bike_status"
        response_json = requests.get(endpoint).json()
        response_df = pd.json_normalize(response_json["data"]["bikes"])
        response_gdf = gpd.GeoDataFrame(
            response_df,
            crs="epsg:4326",
            geometry=[
                shapely.geometry.Point(xy)
                for xy in zip(response_df["lon"], response_df["lat"])
            ],
        )
        # Drop lat and lon columns
        response_gdf = response_gdf.drop(columns=["lat", "lon"])

        return json.loads(response_gdf.to_json())
