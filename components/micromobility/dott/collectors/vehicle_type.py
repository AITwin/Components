import requests

from src.components import Collector


class DottVehicleTypeCollector(Collector):
    def run(self):
        endpoint = "https://gbfs.api.ridedott.com/public/v2/brussels/vehicle_types.json"
        response_json = requests.get(endpoint).json()
        return response_json
