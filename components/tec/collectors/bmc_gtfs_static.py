from src.components import Collector
from src.utilities.bmc import bmc_request


class TECBMCGTFSStaticCollector(Collector):
    def run(self) -> bytes:
        response = bmc_request("/api/gtfs/feed/tec/static")
        return response.content
