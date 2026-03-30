import requests

from src.components import Collector
from src.utilities.bmc import bmc_request


class SNCBGTFSStaticCollector(Collector):
    def run(self):
        response = bmc_request("/api/gtfs/feed/nmbssncb/static")
        return response.content
