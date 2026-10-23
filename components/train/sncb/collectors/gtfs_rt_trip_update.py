from src.components import Collector
from src.utilities.bmc import bmc_realtime_feed


class SNCBGTFSRTTripUpdateCollector(Collector):
    def run(self):
        return bmc_realtime_feed("/api/gtfs/feed/nmbssncb/rt/trip-update")
