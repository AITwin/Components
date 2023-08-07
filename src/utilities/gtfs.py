import json
import os
from datetime import datetime, timedelta
from tempfile import NamedTemporaryFile

import geopandas as gpd
import gtfs_kit as gk
import pandas as pd
from google.transit import gtfs_realtime_pb2
from pytz import timezone


def load_gtfs_kit_from_zip_string(zip_bytes: bytes):
    """
    Load GTFS feed from zip string
    @param zip_bytes: A zip file in bytes
    @return: GTFS feed
    """

    tmp = NamedTemporaryFile(delete=False)
    tmp.write(zip_bytes)

    # Close temporary file to allow GTFS kit to read it
    tmp.close()

    # Load GTFS feed from temporary file
    feed = gk.read_feed(tmp.name, dist_units="km")

    # Remove temporary file to avoid clutter
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
    # Check if both timestamps are for the same day, Brussels time
    brussels_timezone = timezone("Europe/Brussels")

    start_date = datetime.utcfromtimestamp(start_timestamp).astimezone(
        tz=brussels_timezone
    )
    end_date = datetime.utcfromtimestamp(end_timestamp).astimezone(tz=brussels_timezone)

    source_date = end_date.strftime("%Y%m%d")

    stops = gtfs_feed.get_stops(source_date)[
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
            end_date - timedelta(seconds=1)  # We need the time just
            # before midnight.
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
    source_date = start_date.strftime("%Y%m%d")

    # Compute feed time series
    trips = gtfs_feed.get_trips(source_date)
    stop_times = gtfs_feed.get_stop_times(source_date)
    # Filter departure_time and arrival_time
    stop_times = stop_times[
        (stop_times["departure_time"] >= start_date.strftime("%H:%M:%S"))
        & (stop_times["arrival_time"] <= end_date.strftime("%H:%M:%S"))
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
                    # Headsign or short name, depending on the agency
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
        output_data.append(
            {
                "stop_id": stop_id,
                "stop_name": stop_name,
                "stop_lat": stop_lat,
                "stop_lon": stop_lon,
                "schedule": group[
                    list(
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
                ].to_dict(orient="records"),
            }
        )
    return output_data
