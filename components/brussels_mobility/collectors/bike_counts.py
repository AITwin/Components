import requests

from src.components import Collector

# The bike/api/counts endpoint was removed in October 2026, the same live
# counts are now only published through the geoserver rt_counting layer.
RT_COUNTING_URL = (
    "https://data.mobility.brussels/geoserver/bm_bike/wfs"
    "?service=wfs&version=1.1.0&request=GetFeature&typeName=bm_bike:rt_counting"
    "&outputFormat=json&srsName=EPSG:4326"
)


class BrusselsMobilityBikeCountsCollector(Collector):
    def run(self):
        response = requests.get(RT_COUNTING_URL, timeout=30)
        response.raise_for_status()

        # Keep the shape of the old live API: counts keyed by device name
        return {
            "data": {
                feature["properties"]["device_name"]: {
                    "hour_cnt": feature["properties"]["hour_cnt"],
                    "day_cnt": feature["properties"]["day_cnt"],
                    "year_cnt": feature["properties"]["year_cnt"],
                    "cnt_time": feature["properties"]["cnt_time"],
                }
                for feature in response.json()["features"]
            }
        }
