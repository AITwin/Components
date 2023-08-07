import requests

from src.components import Collector


class SNCBGTFSStaticCollector(Collector):
    def run(self):
        endpoint = "https://sncb-opendata.hafas.de/gtfs/static/c21ac6758dd25af84cca5b707f3cb3de"

        return requests.get(endpoint).content
