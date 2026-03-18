import requests

from src.components import Collector

ENDPOINT = "https://opendata.brussels.be/api/explore/v2.1/catalog/datasets/disponibilite-en-temps-reel-des-velos-villo-rbc/records"
LIMIT = 100


class BrusselsMobilityVilloCollector(Collector):
    def run(self):
        all_records = []
        offset = 0

        while True:
            response = requests.get(
                ENDPOINT, params={"limit": LIMIT, "offset": offset}
            )
            response.raise_for_status()
            data = response.json()

            all_records.extend(data["results"])

            if offset + LIMIT >= data["total_count"]:
                break
            offset += LIMIT

        return all_records
