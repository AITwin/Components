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

        return self.to_geojson(all_records)

    @staticmethod
    def to_geojson(records):
        features = []
        for record in records:
            geo_point = record.get("geo_point_2d")
            if not geo_point:
                continue

            properties = {
                "number": record.get("number"),
                "name_fr": record.get("name_fr"),
                "name_nl": record.get("name_nl"),
                "address_fr": record.get("address_fr"),
                "address_nl": record.get("address_nl"),
                "municipality_fr": record.get("mu_fr"),
                "municipality_nl": record.get("mu_nl"),
                "available_bikes": record.get("available_bikes"),
                "available_bike_stands": record.get("available_bike_stands"),
                "bike_stands": record.get("bike_stands"),
                "last_update": record.get("last_update"),
            }

            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [geo_point["lon"], geo_point["lat"]],
                },
                "properties": properties,
            })

        return {
            "type": "FeatureCollection",
            "features": features,
        }
