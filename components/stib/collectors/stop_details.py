from src.components import Collector
from src.utilities.bmc import bmc_request_all

# STIB static data is about 2425 stops. BMC answered the 2026-11-05 refresh
# with an empty list, which was stored and left /stib/stops without input.
MIN_STOPS = 2000


class STIBStopDetailsCollector(Collector):
    def run(self):
        return {
            "results": bmc_request_all(
                "/api/datasets/stibmivb/static/stopDetails", min_records=MIN_STOPS
            )
        }
