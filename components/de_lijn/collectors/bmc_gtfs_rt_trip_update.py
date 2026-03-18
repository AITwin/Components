from src.components import Collector
from src.utilities.bmc import bmc_request


class DeLijnBMCGTFSRTTripUpdateCollector(Collector):
    def run(self):
        response = bmc_request("/api/gtfs/feed/delijn/rt/trip-update", params={"format": "json"})
        return response.json()
