import requests

from src.components import Collector


class DeLijnGTFSStaticCollector(Collector):
    def run(self):
        return requests.get("https://gtfs.irail.be/de-lijn/de_lijn-gtfs.zip").content
