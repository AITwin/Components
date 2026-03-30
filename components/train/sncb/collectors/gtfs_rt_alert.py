from src.components import Collector
from src.utilities.bmc import bmc_request


class SNCBGTFSRTAlertCollector(Collector):
    def run(self):
        response = bmc_request("/api/gtfs/feed/nmbssncb/rt/alert", params = dict(format="protobuf"))
        return response.content
