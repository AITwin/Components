import requests

from src.components import Collector


class SNCBGTFSRealtimeCollector(Collector):
    def run(self):
        endpoint = "https://sncb-opendata.hafas.de/gtfs/realtime/c21ac6758dd25af84cca5b707f3cb3de"

        response = requests.get(endpoint)

        if response.status_code >= 500:
            raise ValueError("SNCB gtfs realtime is down.")

        return response.content
