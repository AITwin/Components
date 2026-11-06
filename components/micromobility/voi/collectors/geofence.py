from ..gbfs import fetch_feed
from src.components import Collector


class VoiGeofenceCollector(Collector):
    def run(self):
        feed = fetch_feed("geofencing_zones")
        if feed is None:
            return None
        return feed["data"]["geofencing_zones"]
