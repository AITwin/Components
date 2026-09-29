"""STIB GTFS-RT feeds, built on request from the `vehicle_trip` snapshot in
force at `end_timestamp` (now, by default): the live feed, or the feed as it
stood at any moment `vehicle_trip` covers."""
from datetime import datetime, timedelta

from src.components import Handler
from src.data.retrieve import retrieve_latest_rows_before_datetime

from ..harvesters.vehicle_trip import trip_updates, vehicle_positions

# A snapshot older than this at the requested moment means the harvester was
# not running then; an old feed presented as current would mislead a planner.
MAX_AGE = timedelta(minutes=2)


def _snapshot(handler, table, end_timestamp):
    moment = datetime.utcfromtimestamp(end_timestamp)
    # Rows strictly before the date; a snapshot taken at the second asked for counts.
    rows = retrieve_latest_rows_before_datetime(
        table=handler.get_table_by_name(table), date=moment + timedelta(seconds=1), limit=1)
    if not rows or moment - rows[0].date > MAX_AGE:
        return None
    return rows[0]


class STIBGTFSRTVehiclePositionHandler(Handler):
    def run(self, start_timestamp: int, end_timestamp: int):
        row = _snapshot(self, "stib_vehicle_trip", end_timestamp)
        return vehicle_positions(row.data) if row is not None else None


class STIBGTFSRTTripUpdateHandler(Handler):
    def run(self, start_timestamp: int, end_timestamp: int):
        row = _snapshot(self, "stib_vehicle_trip", end_timestamp)
        if row is None:
            return None
        gtfs = retrieve_latest_rows_before_datetime(
            table=self.get_table_by_name("stib_gtfs_parquet"), date=row.date, limit=1)
        return trip_updates(row.data, gtfs[0]) if gtfs else None
