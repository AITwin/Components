from src.components import Collector
from src.utilities.bmc import bmc_request


class SNCBGTFSRTTripUpdateCollector(Collector):
    def run(self):
        response = bmc_request("/api/gtfs/feed/nmbssncb/rt/trip-update", params = dict(format="protobuf"))
        return response.content
