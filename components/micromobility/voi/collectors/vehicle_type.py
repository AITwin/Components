from ..gbfs import fetch_feed
from src.components import Collector


class VoiVehicleTypeCollector(Collector):
    def run(self):
        return fetch_feed("vehicle_types")
