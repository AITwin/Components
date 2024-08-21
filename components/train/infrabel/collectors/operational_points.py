import requests

from src.components import Collector


class InfrabelOperationalPointsCollector(Collector):
    def run(self):
        endpoint = (
            "https://opendata.infrabel.be/api/explore/v2.1/catalog/datasets/operationele-punten-van-het-netwerk/exports/geojson?lang=fr&timezone=Europe%2FBerlin"
        )
        return requests.get(endpoint).json()
