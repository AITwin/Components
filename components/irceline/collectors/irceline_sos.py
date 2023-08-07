import json

import geopandas as gpd
import pandas as pd
import requests

from src.components import Collector


class IrcelineSOSCollector(Collector):
    def run(self):
        sso_url = "https://geo.irceline.be/sos/api/v1/"
        endpoint = sso_url + "timeseries/?expanded=true"
        response_json = requests.get(endpoint).json()

        the_df_col = "station.geometry.coordinates"

        response_df = pd.json_normalize(response_json, max_level=4)

        col_list = ["latitude", "longitude", "nan"]

        response_df[col_list] = pd.DataFrame(
            response_df[the_df_col].tolist(), index=response_df.index
        )

        gdf = gpd.GeoDataFrame(
            response_df,
            geometry=gpd.points_from_xy(response_df.latitude, response_df.longitude),
            crs="EPSG:4326",
        )

        columns_to_remove = [
            "referenceValues",
            "extras",
            "station.geometry.type",
            "station.type",
            "parameters.service.id",
            "parameters.service.label",
            "statusIntervals",
            "station.geometry.coordinates",
            *col_list,
        ]

        gdf.drop(columns_to_remove, axis=1, inplace=True)

        return json.loads(gdf.to_json())
