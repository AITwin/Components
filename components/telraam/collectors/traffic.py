import os

import requests

from src.components import Collector


class TelraamTrafficCollector(Collector):
    def run(self):
        return requests.get(
            "https://telraam-api.net/v1/reports/traffic_snapshot_live",
            headers={"X-Api-Key": os.environ["TELRAAM_API_KEY"]},
        ).json()
