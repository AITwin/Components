import requests

from src.components import Collector
from src.utilities.bmc import bmc_request

class TECGTFSStaticCollector(Collector):
    def run(self):
        response = bmc_request("/api/gtfs/feed/tec/static")
        return response.content
