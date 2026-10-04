import json
import time

import geopandas as gpd
import pandas as pd
import requests
import shapely

from src.components import Collector

# ADS-B emitter category codes
CATEGORY = {
    "A0": "No information",
    "A1": "Light (< 15500 lbs)",
    "A2": "Small (15500 to 75000 lbs)",
    "A3": "Large (75000 to 300000 lbs)",
    "A4": "High Vortex Large",
    "A5": "Heavy (> 300000 lbs)",
    "A6": "High Performance",
    "A7": "Rotorcraft",
    "B1": "Glider / sailplane",
    "B2": "Lighter-than-air",
    "B3": "Parachutist / Skydiver",
    "B4": "Ultralight / hang-glider / paraglider",
    "B6": "Unmanned Aerial Vehicle",
    "B7": "Space / Trans-atmospheric",
    "C1": "Surface – Emergency Vehicle",
    "C2": "Surface – Service Vehicle",
    "C3": "Point Obstacle",
}

FT_TO_M = 0.3048
KT_TO_MS = 0.514444
FTMIN_TO_MS = 0.00508


def _alt(v):
    if v is None:
        return None
    if v == "ground":
        return 0.0
    try:
        return float(v) * FT_TO_M
    except (TypeError, ValueError):
        return None


class AdsbLolPositionCollector(Collector):
    """Snapshot of aircraft over a Belgian-centred radius from adsb.lol (ODbL).

    No API key required. Returns the same GeoJSON shape as
    :class:`OpenSkyPositionCollector` so the two feeds can be unioned. Replaces
    airplanes.live, whose API has been open to feeders only since 2026-08-12.
    """

    def run(self):
        # Centre/radius for the point query. Defaults cover
        # Belgium and a thin border margin; tighten via settings if needed.
        lat = self.settings.get("lat", 50.85)
        lon = self.settings.get("lon", 4.7)
        radius_nm = self.settings.get("radius_nm", 90)

        # Bounding box used to clip the response to Belgian airspace.
        # Same envelope as the OpenSky collector for consistency.
        lamin = self.settings.get("lamin", 49.5294835476)
        lomin = self.settings.get("lomin", 2.51357303225)
        lamax = self.settings.get("lamax", 51.4750237087)
        lomax = self.settings.get("lomax", 6.15665815596)

        endpoint = f"https://api.adsb.lol/v2/point/{lat}/{lon}/{radius_nm}"
        response = requests.get(endpoint, headers={"User-Agent": "CoDE-airplanes/1.0"}, timeout=20)
        response.raise_for_status()
        body = response.json()
        ac_list = body.get("ac") or []
        # `seen` and `seen_pos` are seconds before the response; OpenSky gives
        # epoch seconds, so convert to match.
        now = body.get("now", time.time() * 1000) / 1000

        if not ac_list:
            return {"type": "FeatureCollection", "features": []}

        rows = []
        for a in ac_list:
            lat_v, lon_v = a.get("lat"), a.get("lon")
            if lat_v is None or lon_v is None:
                continue
            if not (lamin <= lat_v <= lamax and lomin <= lon_v <= lomax):
                continue
            on_ground = a.get("alt_baro") == "ground"
            rows.append({
                "icao24": (a.get("hex") or "").lower(),
                "callsign": (a.get("flight") or "").strip(),
                "origin_country": None,
                "time_position": round(now - a["seen_pos"]) if a.get("seen_pos") is not None else None,
                "last_contact": round(now - a.get("seen", 0)),
                "longitude": lon_v,
                "latitude": lat_v,
                "baro_altitude": _alt(a.get("alt_baro")),
                "on_ground": on_ground,
                "velocity": (a.get("gs") * KT_TO_MS) if a.get("gs") is not None else None,
                "true_track": a.get("track"),
                "vertical_rate": (a.get("baro_rate") * FTMIN_TO_MS) if a.get("baro_rate") is not None else None,
                "sensors": None,
                "geo_altitude": _alt(a.get("alt_geom")),
                "squawk": a.get("squawk"),
                "spi": False,
                "position_source": "ADS-B",
                "category": CATEGORY.get(a.get("category")),
                "registration": a.get("r"),
                "aircraft_type": a.get("t"),
                "source_feed": "adsb.lol",
            })

        df = pd.DataFrame(rows)
        gdf = gpd.GeoDataFrame(
            df,
            crs="epsg:4326",
            geometry=[shapely.geometry.Point(xy) for xy in zip(df["longitude"], df["latitude"])],
        ).drop(columns=["longitude", "latitude"])

        return json.loads(gdf.to_json())
