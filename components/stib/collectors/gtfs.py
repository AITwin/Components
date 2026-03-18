from src.components import Collector
from src.utilities.bmc import bmc_request


class STIBGTFSCollector(Collector):
    def run(self) -> bytes:
        response = bmc_request("/api/gtfs/feed/stibmivb/static")
        return response.content
