from src.components import Collector
from src.utilities.bmc import bmc_request


class SNCBBMCGTFSRTTripUpdateCollector(Collector):
    def run(self):
        response = bmc_request("/api/gtfs/feed/nmbssncb/rt/trip-update", params={"format": "json"})
        return response.json()
