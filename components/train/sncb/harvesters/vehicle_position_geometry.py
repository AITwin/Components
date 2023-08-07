import json
from datetime import datetime
from typing import List, Type

import geopandas as gpd
import pandas as pd

from src.components import Harvester
from src.utilities.gtfs import (
    load_gtfs_realtime_from_bytes_to_df,
    load_gtfs_kit_from_zip_string,
)


class SNCBVehiclePositionGeometryHarvester(Harvester):
    def run(self, source, sncb_gtfs, infrabel_segments, infrabel_operational_points):
        operational_points = gpd.GeoDataFrame.from_features(
            infrabel_operational_points.data["features"]
        )[["longnamefrench", "ptcarid", "commerciallongnamefrench"]]

        segments = gpd.GeoDataFrame.from_features(infrabel_segments.data["features"])

        gtfs_static = load_gtfs_kit_from_zip_string(sncb_gtfs.data)

        gtfs_rt = load_gtfs_realtime_from_bytes_to_df(source.data)

        current_date = source.date.strftime("%Y%m%d")

        stop_times = gtfs_static.get_stop_times(current_date)[
            ["trip_id", "stop_id", "stop_sequence", "arrival_time", "departure_time"]
        ].copy()

        stop_times["arrival_delay"] = 0

        stop_times.update(gtfs_rt)

        stop_times["next_stop_sequence"] = stop_times["stop_sequence"] + 1

        # Merge with next stop
        stop_times = stop_times.merge(
            stop_times[["trip_id", "stop_sequence", "arrival_time", "stop_id"]],
            left_on=["trip_id", "next_stop_sequence"],
            right_on=["trip_id", "stop_sequence"],
            suffixes=("", "_next"),
        )

        stop_times["start_seconds"] = stop_times["arrival_time"].apply(
            lambda x: pd.to_timedelta(x).total_seconds()
        )
        stop_times["end_seconds"] = stop_times["arrival_time_next"].apply(
            lambda x: pd.to_timedelta(x).total_seconds()
        )

        fetch_time_in_seconds = source.date.time().strftime("%H:%M:%S")
        fetch_time_in_seconds = pd.to_timedelta(fetch_time_in_seconds).total_seconds()

        # Filter where fetch_time_in_seconds is between start_seconds and end_seconds
        stop_times = stop_times[
            (stop_times["start_seconds"] < fetch_time_in_seconds)
            & (stop_times["end_seconds"] > fetch_time_in_seconds)
        ]

        # Compute percentage of completion between start_seconds and end_seconds based on fetch_time_in_seconds
        stop_times["percentage"] = (
            fetch_time_in_seconds - stop_times["start_seconds"]
        ) / (stop_times["end_seconds"] - stop_times["start_seconds"])

        stop_times = stop_times[
            [
                "trip_id",
                "stop_id",
                "stop_id_next",
                "arrival_time",
                "arrival_time_next",
                "percentage",
            ]
        ]

        # Rename stop_id to start_stop_id and stop_id_next to end_stop_id. Also rename arrival_time to start_time and arrival_time_next to end_time.
        stop_times = stop_times.rename(
            columns={
                "stop_id": "start_stop_id",
                "stop_id_next": "end_stop_id",
                "arrival_time": "start_time",
                "arrival_time_next": "end_time",
            }
        )

        # Merge with stops to get stop lat/lon and name for both start and end
        stop_times = stop_times.merge(
            gtfs_static.stops[["stop_id", "stop_name", "stop_lat", "stop_lon"]],
            left_on="start_stop_id",
            right_on="stop_id",
        )

        stop_times = stop_times.merge(
            gtfs_static.stops[["stop_id", "stop_name", "stop_lat", "stop_lon"]],
            left_on="end_stop_id",
            right_on="stop_id",
            suffixes=("_start", "_end"),
        )

        rows = []

        for index, row in operational_points.iterrows():
            rows.append(
                {
                    "name": row["longnamefrench"]
                    .upper()
                    .replace(" ", "")
                    .replace("'", ""),
                    "ptcarid": row["ptcarid"],
                }
            )
            rows.append(
                {
                    "name": row["commerciallongnamefrench"]
                    .upper()
                    .replace(" ", "")
                    .replace("'", ""),
                    "ptcarid": row["ptcarid"],
                }
            )

        stop_names_clean = pd.DataFrame(rows).drop_duplicates()

        work = stop_times[
            ["trip_id", "stop_name_start", "stop_name_end", "percentage"]
        ].copy()
        # Convert both to uppercase
        work["stop_name_start"] = work["stop_name_start"].apply(lambda x: x.upper())
        work["stop_name_end"] = work["stop_name_end"].apply(lambda x: x.upper())

        work["stop_name_start"] = work["stop_name_start"].apply(
            lambda x: x.replace(" ", "").replace("(b)", "").replace("(a)", "")
        )

        # Merge shortnamefrench on stop_name_start
        work = work.merge(
            stop_names_clean[["name", "ptcarid"]],
            left_on="stop_name_start",
            right_on="name",
            how="left",
        )

        # Merge name on stop_name_end
        work = work.merge(
            stop_names_clean[["name", "ptcarid"]],
            left_on="stop_name_end",
            right_on="name",
            how="left",
            suffixes=("_start", "_end"),
        )

        # Remove where either ptcarid_start or ptcarid_end is null
        work = work[(work["ptcarid_start"].notnull()) & (work["ptcarid_end"].notnull())]

        # Merge work on stationfrom_id and stationto_id
        final = segments.merge(
            work,
            left_on=["stationfrom_id", "stationto_id"],
            right_on=["ptcarid_start", "ptcarid_end"],
        )

        # Drop where geometry is null
        final = final[final["geometry"].notnull()]

        if final.empty:
            return

        # Interpolate point using geometry (linestring) and percentage
        final["geometry"] = final.apply(
            lambda row: row["geometry"].interpolate(row["percentage"], normalized=True),
            axis=1,
        )

        # Merge with trips to get trip_headsign
        final = final.merge(
            gtfs_static.trips[["trip_id", "trip_headsign"]], on="trip_id"
        )

        final = final[
            [
                "trip_id",
                "trip_headsign",
                "name_start",
                "name_end",
                "ptcarid_start",
                "ptcarid_end",
                "geometry",
            ]
        ]

        return json.loads(final.to_json())
