import requests

from src.components import Collector
from src.utilities.bmc import bmc_request


class DeLijnGTFSStaticCollector(Collector):
    def run(self):
        response = bmc_request("/api/gtfs/feed/delijn/static")
        return response.content
