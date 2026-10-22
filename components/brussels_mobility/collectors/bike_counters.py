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
            for field in COUNT_FIELDS:
                feature["properties"].pop(field, None)
            feature["properties"]["active"] = True

        return data
