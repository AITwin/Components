from src.components import Collector
from src.utilities.bmc import bmc_request


class STIBShapeFilesCollector(Collector):
    def run(self) -> bytes:
        response = bmc_request("/api/datasets/stibmivb/static/shape-files")
        return response.content
