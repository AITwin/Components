from src.components import Collector
from src.utilities.bmc import bmc_request


class TECGTFSRTVehiclePositionCollector(Collector):
    def run(self):
        response = bmc_request("/api/gtfs/feed/tec/rt/vehicle-position", params = dict(format="protobuf"))
        return response.content
