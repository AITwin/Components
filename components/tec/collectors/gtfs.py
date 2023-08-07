import requests

from src.components import Collector


class TECGTFSStaticCollector(Collector):
    def run(self):
        endpoint = "https://opendata.tec-wl.be/Current%20GTFS/TEC-GTFS.zip"
        return requests.get(endpoint).content
