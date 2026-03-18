from src.components import Collector
from src.utilities.bmc import bmc_request


class STIBStopsByLineCollector(Collector):
    def run(self):
        response = bmc_request("/api/datasets/stibmivb/static/stopsByLine")
        return response.json()
