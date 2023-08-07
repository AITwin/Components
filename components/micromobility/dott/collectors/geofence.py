import requests

from src.components import Collector


class DottGeofenceCollector(Collector):
    def run(self):
        endpoint = "https://gbfs.api.ridedott.com/public/v2/brussels/geofencing_zones.json"
        response_json = requests.get(endpoint).json()
        return response_json["data"]["geofencing_zones"]
