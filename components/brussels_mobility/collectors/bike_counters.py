import requests

from src.components import Collector
from .bike_counts import RT_COUNTING_URL, request_date

COUNT_FIELDS = ("hour_cnt", "day_cnt", "year_cnt", "cnt_time")


class BrusselsMobilityBikeCountersCollector(Collector):
    def run(self):
        response = requests.get(RT_COUNTING_URL, timeout=30)
        response.raise_for_status()
        data = response.json()

        # The layer only lists counters that are reporting, and carries the
        # live counts, which belong to bike_counts
        for feature in data["features"]:
            properties = feature["properties"]
            for field in COUNT_FIELDS + ("id",):
                properties.pop(field, None)
            # Same pictures as the old API, renamed
            properties["picture_1"] = properties.pop("pic_a", None)
            properties["picture_2"] = properties.pop("pic_b", None)
            properties["active"] = True
            # The old API's feature id and geometry_name placement
            feature["id"] = f"device.{properties['device_name']}"
            feature["geometry"]["geometry_name"] = feature.pop("geometry_name", "geom")

        # geoserver gives "unknown" here, the old API the number of counters
        data["totalFeatures"] = len(data["features"])
        data["requestDate"] = request_date()
        return data
