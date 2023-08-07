import requests

from src.components import Collector


class BoltVehicleTypeCollector(Collector):
    def run(self):
        endpoint = "https://mds.bolt.eu/gbfs/2/336/vehicle_types"
        response_json = requests.get(endpoint).json()
        return response_json
