import json
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from src.components import Harvester
from src.utilities.gtfs import load_gtfs_parquet_feed


BRUSSELS = ZoneInfo("Europe/Brussels")


def _service_clock(date: datetime):
    """The service day and the GTFS clock (seconds since noon minus 12 h, local)
    of a stored date, which is naive UTC. GTFS times are Brussels local: read
    against the UTC clock, trains were placed where the timetable had them two
    hours earlier in summer, one in winter."""
    moment = date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date
    day = moment.astimezone(BRUSSELS).date()
    origin = datetime.combine(day, time(12), BRUSSELS) - timedelta(hours=12)
    return day, (moment - origin).total_seconds()


class _CachedStopTimes:
    stop_times = None
    date = None


def _cached_stop_times(gtfs_feed, date):
    """Get stop_times for a date, using gtfs_parquet Feed with datetime.date."""
    if _CachedStopTimes.stop_times is None or _CachedStopTimes.date != date:
        _CachedStopTimes.stop_times = gtfs_feed.get_stop_times(date).to_pandas()[
            ["trip_id", "stop_id", "stop_sequence", "arrival_time", "departure_time"]
        ].copy()
        _CachedStopTimes.date = date

    return _CachedStopTimes.stop_times


class SNCBVehiclePositionGeometryHarvester(Harvester):
    def run(self, source, sncb_gtfs_parquet, infrabel_segments, infrabel_operational_points):
        operational_points = gpd.GeoDataFrame.from_features(
            infrabel_operational_points.data["features"]
        )[["longnamefrench", "ptcarid", "commerciallongnamefrench"]]

        segments = gpd.GeoDataFrame.from_features(infrabel_segments.data["features"])

        gtfs_static = load_gtfs_parquet_feed(sncb_gtfs_parquet.data)

        # Positions come from the timetable. The realtime feed's trip ids match
        # the published GTFS for only about half the trips, so its delays are
        # not applied; the poll only sets the moment.
        current_date, fetch_time_in_seconds = _service_clock(source.date)

        stop_times = _cached_stop_times(gtfs_static, current_date).copy()

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
        stops_df = gtfs_static.stops.to_pandas()[["stop_id", "stop_name", "stop_lat", "stop_lon"]]

        stop_times = stop_times.merge(
            stops_df,
            left_on="start_stop_id",
            right_on="stop_id",
        )

        stop_times = stop_times.merge(
            stops_df,
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
            ["trip_id", "stop_name_start", "stop_name_end", "percentage", "stop_lon_start", "stop_lat_start"]
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
            # No train on the network (nightly 01:00-04:00 UTC). An empty
            # collection is a real observation the API can serve; returning
            # None stored an empty row the API skips, so it kept serving the
            # last trains of the evening as the current positions all night.
            return {"type": "FeatureCollection", "features": []}

        # Interpolate point using geometry (linestring) and percentage. Infrabel
        # does not orient a segment from stationfrom to stationto (about half
        # run the other way), so a train is measured from whichever end lies
        # nearer the station it left; otherwise it ran backwards, and jumped
        # kilometres at the next segment.
        final["geometry"] = final.apply(_position, axis=1)

        # Merge with trips to get trip_headsign
        trips_df = gtfs_static.trips.to_pandas()[["trip_id", "trip_headsign"]]
        final = final.merge(trips_df, on="trip_id")

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


def _position(row):
    line, share = row["geometry"], row["percentage"]
    departure = Point(row["stop_lon_start"], row["stop_lat_start"])
    first, last = Point(line.coords[0]), Point(line.coords[-1])
    if departure.distance(last) < departure.distance(first):
        share = 1.0 - share
    return line.interpolate(share, normalized=True)
