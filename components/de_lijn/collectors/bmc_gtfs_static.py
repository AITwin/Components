from src.components import Collector
from src.utilities.bmc import bmc_request


class DeLijnBMCGTFSStaticCollector(Collector):
    def run(self) -> bytes:
        response = bmc_request("/api/gtfs/feed/delijn/static")
        return response.content
