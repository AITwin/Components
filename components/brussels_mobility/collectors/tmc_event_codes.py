import requests

from src.components import Collector


class BrusselsMobilityTMCEventCodesCollector(Collector):
    def run(self):
        return requests.get(
            "https://data.mobility.brussels/datasets/v1/traffic/collections/tmc_event_codes/items?f=json&limit=1000"
        ).json()