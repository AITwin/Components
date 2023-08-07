import requests

from src.components import Collector


class InfrabelSegmentsCollector(Collector):
    def run(self):
        endpoint = (
            "https://infrabel.opendatasoft.com/api/explore/v2.1/catalog/datasets/station_to_station/exports"
            "/geojson?lang=fr&timezone=Europe%2FBerlin"
        )
        return requests.get(endpoint).json()
