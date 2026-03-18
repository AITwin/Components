from src.components import Collector
from src.utilities.bmc import bmc_request


class STIBStopDetailsCollector(Collector):
    def run(self):
        response = bmc_request("/api/datasets/stibmivb/static/stopDetails")
        return response.json()
