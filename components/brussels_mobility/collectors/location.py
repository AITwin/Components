import requests

from src.components import Collector


class BrusselsMobilityTrafficDevicesCollector(Collector):
    def run(self):
        data = requests.get(
            "https://data.mobility.brussels/traffic/api/counts/?request=devices"
        ).json()

        return data
