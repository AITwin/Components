from src.components import Collector
from src.utilities.bmc import bmc_request


class DeLijnBMCGTFSRTAlertCollector(Collector):
    def run(self):
        response = bmc_request("/api/gtfs/feed/delijn/rt/alert", params={"format": "json"})
        return response.json()
