import requests

from src.components import Collector


class BrusselsMobilityPublicParkingCollector(Collector):
    def run(self):
        return requests.get(
            "https://opendata.brussels.be/api/explore/v2.1/catalog/datasets/public-parkings/exports/geojson?lang=en&timezone=Europe%2FBerlin"
        ).json()
