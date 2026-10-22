import requests

from src.components import Collector


class BrusselsMobilityPublicParkingCollector(Collector):
    """The `public-parkings` dataset disappeared from opendata.brussels.be in
    August 2025, Brussels Mobility still publishes the same car parks (without
    occupancy) through its geoserver. It refuses anything that is not a
    feature collection, since for a year the old source stored the portal's
    "dataset does not exist" error body every five minutes."""

    def run(self):
        response = requests.get(
            "https://data.mobility.brussels/geoserver/bm_parking/wfs"
            "?service=wfs&version=1.1.0&request=GetFeature&typeName=bm_parking:parkingpublic"
            "&outputFormat=json&srsName=EPSG:4326",
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()

        if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
            raise ValueError(f"Upstream did not return a FeatureCollection: {str(payload)[:200]}")

        return payload
