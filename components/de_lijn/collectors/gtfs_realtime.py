import os

import requests

from src.components import Collector


class DeLijnGTFSRealtimeCollector(Collector):
    def run(self):
        endpoint = (
            "https://api.delijn.be/gtfs/v3/realtime?json=false&delay=true&canceled=true"
        )
        response_data = requests.get(
            endpoint, headers={"Ocp-Apim-Subscription-Key": os.environ["DE_LIJN_API_KEY"]}
        ).content

        return response_data
