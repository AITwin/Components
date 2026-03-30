from src.components import Collector
from src.utilities.bmc import bmc_request


class TECGTFSRTTripUpdateCollector(Collector):
    def run(self):
        response = bmc_request("/api/gtfs/feed/tec/rt/trip-update", params = dict(format="protobuf"))
        return response.content
