from src.components import Handler

from src.utilities.mf_json import fetch_geojsons_and_return_mf_json


class STIBTripsHandler(Handler):
    def run(self, start_timestamp: int, end_timestamp: int):
        return fetch_geojsons_and_return_mf_json(
            self.get_table_by_name("stib_vehicle_identify"),
            start_timestamp,
            end_timestamp,
            "uuid",
            ["distance", "distanceFromPoint", "pointId"],
        )
