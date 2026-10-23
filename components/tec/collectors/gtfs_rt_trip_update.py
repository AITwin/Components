from src.components import Collector
from src.utilities.bmc import bmc_realtime_feed


class TECGTFSRTTripUpdateCollector(Collector):
    def run(self):
        return bmc_realtime_feed("/api/gtfs/feed/tec/rt/trip-update")
