from src.components import Collector
from src.utilities.bmc import bmc_request_all


class STIBStopDetailsCollector(Collector):
    def run(self):
        return {
            "results": bmc_request_all(
                "/api/datasets/stibmivb/static/stopDetails"
            )
        }
