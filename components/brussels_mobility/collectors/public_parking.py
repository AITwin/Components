import requests

from src.components import Collector


class BrusselsMobilityPublicParkingCollector(Collector):
    """Not scheduled any more: the `public-parkings` dataset disappeared from
    opendata.brussels.be in August 2025. Kept so it can be pointed at a
    replacement dataset; it now refuses anything that is not a feature
    collection, since for a year it stored the portal's "dataset does not
    exist" error body every five minutes."""

    def run(self):
        payload = requests.get(
            "https://opendata.brussels.be/api/explore/v2.1/catalog/datasets/public-parkings/exports/geojson?lang=en&timezone=Europe%2FBerlin"
        ).json()

        if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
            raise ValueError(f"Upstream did not return a FeatureCollection: {str(payload)[:200]}")

        return payload
