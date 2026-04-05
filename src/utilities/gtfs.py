import json
import os
from datetime import datetime, timedelta
from functools import lru_cache
from tempfile import NamedTemporaryFile

import geopandas as gpd
import pandas as pd
from google.transit import gtfs_realtime_pb2
from gtfs_parquet import read_parquet
from pytz import timezone


@lru_cache(maxsize=32)
def load_gtfs_parquet_feed(zip_bytes: bytes):
    """
    Load GTFS feed from a parquet zip archive.
    @param zip_bytes: A parquet zip file in bytes
    @return: gtfs_parquet Feed
    """
    tmp = NamedTemporaryFile(delete=False, suffix=".zip")
    tmp.write(zip_bytes)
    tmp.close()

    feed = read_parquet(tmp.name)

    os.unlink(tmp.name)

    return feed


def load_gtfs_realtime_from_bytes_to_df(gtfs_realtime_bytes: bytes):
    """
    Load GTFS realtime feed from bytes to dataframe
    @param gtfs_realtime_bytes: GTFS realtime feed in bytes
    @return: GTFS realtime feed in dataframe
    """
    # noinspection PyUnresolvedReferences
    rt_feed = gtfs_realtime_pb2.FeedMessage()
    rt_feed.ParseFromString(gtfs_realtime_bytes)

    trip_updates = []

    for entity in rt_feed.entity:
        if entity.HasField("trip_update"):
            trip_update = entity.trip_update
            next_stops = [
                a for a in trip_update.stop_time_update if a.arrival.time != 0
            ]
            if len(next_stops) == 0:
                continue

            trip_updates.append(
                {
                    "trip_id": trip_update.trip.trip_id,
                    "start_time": trip_update.trip.start_time,
                    "start_date": trip_update.trip.start_date,
                    "stop_id": next_stops[0].stop_id,
                    "arrival_delay": next_stops[0].arrival.delay,
                    "arrival_time": next_stops[0].arrival.time,
                }
            )

    return pd.DataFrame(trip_updates)


def schedule_from_gtfs(gtfs_feed, start_timestamp: int, end_timestamp: int):
    brussels_timezone = timezone("Europe/Brussels")

    start_date = datetime.utcfromtimestamp(start_timestamp).astimezone(
        tz=brussels_timezone
    )
    end_date = datetime.utcfromtimestamp(end_timestamp).astimezone(tz=brussels_timezone)

    source_date = end_date.date()

    stops = gtfs_feed.get_stops(source_date).to_pandas()[
        ["stop_id", "stop_name", "stop_lat", "stop_lon"]
    ]

    output_data = []

    if start_date.day != end_date.day:
        midnight = datetime(
            year=end_date.year,
            month=end_date.month,
            day=end_date.day,
            hour=0,
            minute=0,
            second=0,
            tzinfo=brussels_timezone,
        )

        output_data += compute_data_for_one_date(
            gtfs_feed,
            stops,
            midnight,
            end_date - timedelta(seconds=1)
        )
        output_data += compute_data_for_one_date(gtfs_feed, stops, start_date, midnight)
    else:
        output_data += compute_data_for_one_date(gtfs_feed, stops, start_date, end_date)

    output_df = pd.DataFrame(output_data)

    gdf = gpd.GeoDataFrame(
        output_df,
        geometry=gpd.points_from_xy(output_df.stop_lon, output_df.stop_lat),
    )

    return json.loads(gdf.to_json())


def compute_data_for_one_date(gtfs_feed, stops, start_date, end_date):
    source_date = start_date.date()

    trips = gtfs_feed.get_trips(source_date).to_pandas()
    stop_times = gtfs_feed.get_stop_times(source_date).to_pandas()

    # arrival_time/departure_time are timedeltas from gtfs_parquet
    start_td = pd.to_timedelta(start_date.strftime("%H:%M:%S"))
    end_td = pd.to_timedelta(end_date.strftime("%H:%M:%S"))

    stop_times = stop_times[
        (stop_times["departure_time"] >= start_td)
        & (stop_times["arrival_time"] <= end_td)
    ]

    stop_times = stop_times.merge(trips, on="trip_id")

    # Keep only required columns if they exist, otherwise ignore.
    stop_times = stop_times[
        list(
            set(stop_times.columns).intersection(
                [
                    "trip_id",
                    "arrival_time",
                    "departure_time",
                    "stop_id",
                    "route_id",
                    "trip_headsign",
                    "trip_short_name",
                ]
            )
        )
    ]
    stop_times = stop_times.merge(stops, on="stop_id")
    output_data = []
    for (stop_id, stop_name, stop_lat, stop_lon), group in stop_times.groupby(
        ["stop_id", "stop_name", "stop_lat", "stop_lon"]
    ):
        # Convert timedeltas to HH:MM:SS strings for JSON output
        schedule_cols = list(
            set(group.columns).intersection(
                [
                    "trip_id",
                    "arrival_time",
                    "departure_time",
                    "route_id",
                    "trip_headsign",
                    "trip_short_name",
                ]
            )
        )
        schedule_df = group[schedule_cols].copy()
        for col in ["arrival_time", "departure_time"]:
            if col in schedule_df.columns:
                schedule_df[col] = schedule_df[col].apply(
                    lambda x: str(x).split(" ")[-1] if pd.notna(x) else None
                )

        output_data.append(
            {
                "stop_id": stop_id,
                "stop_name": stop_name,
                "stop_lat": stop_lat,
                "stop_lon": stop_lon,
                "schedule": schedule_df.to_dict(orient="records"),
            }
        )
    return output_data
