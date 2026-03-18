from src.components import Collector
from src.utilities.bmc import bmc_request


class SNCBBMCGTFSStaticCollector(Collector):
    def run(self) -> bytes:
        response = bmc_request("/api/gtfs/feed/nmbssncb/static")
        return response.content
