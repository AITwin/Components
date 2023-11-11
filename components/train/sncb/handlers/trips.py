from src.components import Handler
from src.utilities.mf_json import fetch_geojsons_and_return_mf_json


class SNCBTripsHandler(Handler):
    def run(self, start_timestamp: int = None, end_timestamp: int = None):
        return fetch_geojsons_and_return_mf_json(
            self.get_table_by_name("sncb_vehicle_position_geometry"),
            "trip_id",
            start_timestamp,
            end_timestamp,
        )
