import json

import geopandas as gpd
import pandas as pd
import shapely

from ..gbfs import fetch_feed
from src.components import Collector


def bikes_to_geojson(feed: dict) -> dict:
    data = feed["data"]
    bikes = data.get("bikes", data.get("vehicles", []))
    response_df = pd.json_normalize(bikes)
    if response_df.empty:
        return {"type": "FeatureCollection", "features": []}
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


class VoiVehiclePositionCollector(Collector):
    def run(self):
        feed = fetch_feed("free_bike_status")
        if feed is None:
            return None
        return bikes_to_geojson(feed)
