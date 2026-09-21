import requests

from src.components import Collector


class TECGTFSRealtimeCollector(Collector):
    def run(self):
        endpoint = "https://gtfsrt.tectime.be/proto/RealTime/trips?key=DDEBFA42173D45C08E710C7E9DDE8BDE"

        response = requests.get(endpoint, timeout=30)
        response.raise_for_status()
        # The feed intermittently answers 200 with an empty body; storing that
        # made the API serve a feed with no entities for that snapshot.
        if not response.content:
            raise ValueError("TEC GTFS-RT feed returned an empty body")

        return response.content
