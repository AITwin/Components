import requests

from src.components import Collector


class LimeVehicleTypeCollector(Collector):
    def run(self):
        endpoint = "https://data.lime.bike/api/partners/v2/gbfs/brussels/vehicle_types"
        response_json = requests.get(endpoint).json()
        return response_json
