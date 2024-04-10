from datetime import datetime

from src.components import Handler
from src.data.retrieve import retrieve_latest_rows_before_datetime
from src.utilities.gtfs import schedule_from_gtfs, load_gtfs_kit_from_zip_string


class DeLijnVehicleScheduleHandler(Handler):
    def run(self, start_timestamp: int, end_timestamp: int):
        gtfs = retrieve_latest_rows_before_datetime(
            self.get_table_by_name("de_lijn_gtfs"),
            date=datetime.utcfromtimestamp(end_timestamp),
            limit=1,
        )

        if not gtfs:
            return

        gtfs = gtfs[0]

        return schedule_from_gtfs(
            load_gtfs_kit_from_zip_string(gtfs.data), start_timestamp, end_timestamp
        )
