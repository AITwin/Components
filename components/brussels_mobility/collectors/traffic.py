import requests

from src.components import Collector


class BrusselsMobilityTrafficCountsCollector(Collector):
    def run(self):
        return requests.get(
            "https://data.mobility.brussels/traffic/api/counts/?request=live"
        ).json()
