import requests

from src.components import Collector


class InfrabelPunctualityCollector(Collector):
    def run(self):
        return requests.get(
            "https://opendata.infrabel.be/api/explore/v2.1/catalog/datasets/ruwe-gegevens-van-stiptheid-d-1/exports"
            "/json?lang=fr&timezone=Europe%2FBerlin"
        ).json()
