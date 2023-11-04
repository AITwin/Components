import requests

from src.components import Collector


class BrusselsMobilityBikeCountersCollector(Collector):
    def run(self):
        data = requests.get(
            "https://data.mobility.brussels/bike/api/counts/?request=devices"
        ).json()

        return data
