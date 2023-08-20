import os

import requests

from src.components import Collector


class OpenWeatherCollector(Collector):
    def run(self):
        return requests.get(
            f"https://api.openweathermap.org/data/2.5/weather?lat=50.8504500&lon=4.3487800&appid={os.environ['OPENWEATHER_API_KEY']}"
        ).json()
