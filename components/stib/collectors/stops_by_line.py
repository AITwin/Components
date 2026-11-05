from src.components import Collector
from src.utilities.bmc import bmc_request_all

# STIB static data is 148 rows (74 lines, both directions). BMC answered the
# 2026-11-05 refresh with an empty list and the 2026-11-03 one with 49 of 74
# lines; both were stored as the new snapshot and emptied /stib/stops-by-line.
MIN_ROWS = 120


class STIBStopsByLineCollector(Collector):
    def run(self):
        return {
            "results": bmc_request_all(
                "/api/datasets/stibmivb/static/stopsByLine", min_records=MIN_ROWS
            )
        }
