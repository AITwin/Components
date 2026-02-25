import json
import os

import geopandas as gpd
import pandas as pd
import requests
import shapely

from src.components import Collector

POSITION_SOURCE = {
    0: "ADS-B",
    1: "ASTERIX",
    2: "MLAT",
    3: "FLARM",
}

CATEGORY = {
    0: "No information at all",
    1: "No ADS-B Emitter Category Information",
    2: "Light (< 15500 lbs)",
    3: "Small (15500 to 75000 lbs)",
    4: "Large (75000 to 300000 lbs)",
    5: "High Vortex Large (aircraft such as B-757)",
    6: "Heavy (> 300000 lbs)",
    7: "High Performance (> 5g acceleration and 400 kts)",
    8: "Rotorcraft",
    9: "Glider / sailplane",
    10: "Lighter-than-air",
    11: "Parachutist / Skydiver",
    12: "Ultralight / hang-glider / paraglider",
    13: "Reserved",
    14: "Unmanned Aerial Vehicle",
    15: "Space / Trans-atmospheric vehicle",
    16: "Surface Vehicle – Emergency Vehicle",
    17: "Surface Vehicle – Service Vehicle",
    18: "Point Obstacle (includes tethered balloons)",
    19: "Cluster Obstacle",
    20: "Line Obstacle",
}

STATE_VECTOR_COLUMNS = [
    "icao24",
    "callsign",
    "origin_country",
    "time_position",
    "last_contact",
    "longitude",
    "latitude",
    "baro_altitude",
    "on_ground",
    "velocity",
    "true_track",
    "vertical_rate",
    "sensors",
    "geo_altitude",
    "squawk",
    "spi",
    "position_source",
    "category",
]


class OpenSkyPositionCollector(Collector):
    def _get_token(self):
        client_id = os.environ.get("OPENSKY_CLIENT_ID")
        client_secret = os.environ.get("OPENSKY_CLIENT_SECRET")
        if not client_id or not client_secret:
            return None
        response = requests.post(
            "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        return response.json()["access_token"]

    def run(self):
        endpoint = "https://opensky-network.org/api/states/all"

        params = {
            "extended": 1,
            "lamin": self.settings.get("lamin", 49.5294835476),
            "lomin": self.settings.get("lomin", 2.51357303225),
            "lamax": self.settings.get("lamax", 51.4750237087),
            "lomax": self.settings.get("lomax", 6.15665815596),
        }

        headers = {}
        token = self._get_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        response = requests.get(endpoint, params=params, headers=headers)
        response.raise_for_status()
        response_json = response.json()

        if not response_json.get("states"):
            return {"type": "FeatureCollection", "features": []}

        num_cols = len(response_json["states"][0])
        response_df = pd.DataFrame(
            response_json["states"], columns=STATE_VECTOR_COLUMNS[:num_cols]
        )
        response_df["callsign"] = response_df["callsign"].str.strip()
        response_df["position_source"] = response_df["position_source"].map(
            POSITION_SOURCE
        )
        response_df["category"] = response_df["category"].map(CATEGORY)

        response_df = response_df.dropna(subset=["longitude", "latitude"])

        response_gdf = gpd.GeoDataFrame(
            response_df,
            crs="epsg:4326",
            geometry=[
                shapely.geometry.Point(xy)
                for xy in zip(response_df["longitude"], response_df["latitude"])
            ],
        )
        response_gdf = response_gdf.drop(columns=["longitude", "latitude"])

        return json.loads(response_gdf.to_json())
