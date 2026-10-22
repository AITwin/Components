import requests

from src.components import Collector
from .bike_counts import RT_COUNTING_URL

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

        return data
