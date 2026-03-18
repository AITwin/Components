from src.components import Collector
from src.utilities.bmc import bmc_request


class STIBTravellersInformationCollector(Collector):
    def run(self):
        response = bmc_request("/api/datasets/stibmivb/rt/TravellersInformation")
        return response.json()
