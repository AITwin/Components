import requests

from src.components import Collector


class PonyVehicleTypeCollector(Collector):
    def run(self):
        endpoint = "https://gbfs.getapony.com/v1/Brussels/en/vehicle_types.json"
        response_json = requests.get(endpoint).json()
        return response_json
