import requests

from src.components import Collector


class BrusselsMobilityBikeCountsCollector(Collector):
    def run(self):
        data = requests.get(
            "https://data.mobility.brussels/bike/api/counts/?request=live"
        ).json()

        return data
