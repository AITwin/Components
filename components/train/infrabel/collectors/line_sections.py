import requests

from src.components import Collector


class InfrabelLineSectionCollector(Collector):
    def run(self):
        endpoint = (
            "https://opendata.infrabel.be/api/explore/v2.1/catalog/datasets/geosporen/exports/geojson?lang=fr"
            "&timezone=Europe%2FBerlin"
        )
        return requests.get(endpoint).json()
