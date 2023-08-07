import requests

from src.components import Collector


class PonyGeofenceCollector(Collector):
    def run(self):
        endpoint = "https://gbfs.getapony.com/v1/Brussels/en/geofencing_zones.json"
        response_json = requests.get(endpoint).json()
        return response_json["data"]["geofencing_zones"]
