import requests

from src.components import Collector


class TECGTFSRealtimeCollector(Collector):
    def run(self):
        endpoint = "https://gtfsrt.tectime.be/proto/RealTime/trips?key=DDEBFA42173D45C08E710C7E9DDE8BDE"

        return requests.get(endpoint).content
