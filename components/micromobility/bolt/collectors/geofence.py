import requests

from src.components import Collector


class BoltGeofenceCollector(Collector):
    def run(self):
        endpoint = "https://mds.bolt.eu/gbfs/2/336/geofencing_zones"
        response_json = requests.get(endpoint).json()
        return response_json["data"]["geofencing_zones"]
