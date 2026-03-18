import requests

from src.components import Collector


class BrusselsMobilityTrafficEventsCollector(Collector):
    def run(self):
        return requests.get(
            "https://data.mobility.brussels/datasets/v1/traffic/collections/traffic_events/items?f=json&limit=10000"
        ).json()