import json
import os

import geopandas as gpd
import pandas as pd
import requests
import shapely

from src.components import Collector


class FixMyStreetIncidentsCollector(Collector):
    def run(self):
        endpoint = "https://api.brussels/api/fixmystreet/1.0.0/incidents"
        headers = {"Authorization": f"Bearer {os.environ['FIXMYSTREET_API_KEY']}"}
        page_size = 1000

        all_incidents = []
        page = 0

        while True:
            response = requests.get(
                endpoint,
                headers=headers,
                params={"page": page, "size": page_size},
            )
            response.raise_for_status()
            data = response.json()

            incidents = data.get("_embedded", {}).get("response", [])
            all_incidents.extend(incidents)

            page_info = data.get("page", {})
            if page >= page_info.get("totalPages", 1) - 1:
                break
            page += 1

        if not all_incidents:
            return {"type": "FeatureCollection", "features": []}

        response_df = pd.json_normalize(all_incidents)

        valid_df = response_df.dropna(
            subset=["location.coordinates.x", "location.coordinates.y"]
        )

        response_gdf = gpd.GeoDataFrame(
            valid_df,
            crs="epsg:31370",
            geometry=[
                shapely.geometry.Point(xy)
                for xy in zip(
                    valid_df["location.coordinates.x"],
                    valid_df["location.coordinates.y"],
                )
            ],
        )
        response_gdf = response_gdf.drop(
            columns=["location.coordinates.x", "location.coordinates.y"]
        )
        response_gdf = response_gdf.to_crs(epsg=4326)

        return json.loads(response_gdf.to_json())
