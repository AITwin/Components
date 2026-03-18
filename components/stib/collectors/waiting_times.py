from src.components import Collector
from src.utilities.bmc import bmc_request


class STIBWaitingTimesCollector(Collector):
    def run(self):
        response = bmc_request("/api/datasets/stibmivb/rt/WaitingTimes")
        return response.json()
