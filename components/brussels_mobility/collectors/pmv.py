import requests

from src.components import Collector


class BrusselsMobilityPMVDisplayCollector(Collector):
    def run(self):
        response = requests.get(
            "https://api.mobility.brussels/datasets/v1/traffic/collections/pmv_display/items/?f=json&limit=1000",
            timeout=30,
        )
        response.raise_for_status()

        return response.json()


class BrusselsMobilityPMVLocationsCollector(Collector):
    def run(self):
        response = requests.get(
            "https://data.mobility.brussels/geoserver/bm_mobiris/wfs"
            "?service=wfs&version=1.1.0&request=GetFeature&typeName=bm_mobiris:pmv"
            "&outputFormat=json&srsName=EPSG:4326",
            timeout=30,
        )
        response.raise_for_status()

        return response.json()
