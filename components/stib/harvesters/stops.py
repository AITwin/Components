import json
import re

import geopandas as gpd
import pandas as pd
import shapely

from src.components import Harvester


def _clean_stop_id(stop_id: str) -> int:
    cleaned = re.sub(r"[A-Za-z]", "", str(stop_id))
    return int(cleaned) if cleaned else 0


class STIBStopsHarvester(Harvester):
    def run(self, source, stib_stop_details):
        stops_by_line = source.data
        stop_details = stib_stop_details.data

        # Build stop_id -> (lat, lon, name) lookup from stopDetails
        stop_coords = {}
        for stop in stop_details.get("results", stop_details if isinstance(stop_details, list) else []):
            raw_id = str(stop.get("id", ""))
            stop_id = _clean_stop_id(raw_id)
            coords = stop.get("gpscoordinates", "{}")
            if isinstance(coords, str):
                coords = json.loads(coords)
            lat = coords.get("latitude")
            lon = coords.get("longitude")

            name_raw = stop.get("name", "{}")
            if isinstance(name_raw, str):
                name_parsed = json.loads(name_raw)
                name = name_parsed.get("fr", name_parsed.get("nl", ""))
            else:
                name = name_raw.get("fr", name_raw.get("nl", ""))

            if stop_id and lat is not None and lon is not None:
                stop_coords[stop_id] = {"stop_lat": float(lat), "stop_lon": float(lon), "stop_name": name}

        # Build rows from stopsByLine
        data = []
        results = stops_by_line.get("results", stops_by_line if isinstance(stops_by_line, list) else [])
        for line_entry in results:
            line_id = str(line_entry.get("lineid", ""))
            direction_raw = line_entry.get("direction", "")
            direction_id = "V" if direction_raw == "City" else "F"
            direction = 0 if direction_id == "V" else 1

            points_raw = line_entry.get("points", "[]")
            if isinstance(points_raw, str):
                points = json.loads(points_raw)
            else:
                points = points_raw

            for point in sorted(points, key=lambda p: p.get("order", 0)):
                stop_id = _clean_stop_id(point.get("id", ""))
                coord = stop_coords.get(stop_id, {})
                data.append(
                    {
                        "route_short_name": line_id,
                        "direction_id": direction_id,
                        "direction": direction,
                        "stop_id": stop_id,
                        "stop_name": coord.get("stop_name", ""),
                        "stop_sequence": point.get("order", 0),
                        "stop_lat": coord.get("stop_lat"),
                        "stop_lon": coord.get("stop_lon"),
                    }
                )

        df = pd.DataFrame(data)

        with_lat_and_long = df[
            df["stop_lat"].notnull() & df["stop_lon"].notnull()
        ]

        response_gdf = gpd.GeoDataFrame(
            with_lat_and_long,
            crs="epsg:4326",
            geometry=[
                shapely.geometry.Point(xy)
                for xy in zip(
                    with_lat_and_long["stop_lon"], with_lat_and_long["stop_lat"]
                )
            ],
        )

        return json.loads(response_gdf.to_json())
