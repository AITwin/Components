import json
from typing import Dict, List

from components.stib.utils.constant import VEHICLE_POSITION_DATASET
from components.stib.utils.fetch import fetch_stib_dataset_records
from src.components import Collector


class STIBVehiclePositionsCollector(Collector):
    def run(self) -> List[Dict]:
        raw_results = fetch_stib_dataset_records(
            dataset=VEHICLE_POSITION_DATASET,
            limit=100,  # less than 100 lines
        )

        results = []

        for raw_result in map(lambda x: x["fields"], raw_results):
            for vehicle_position in json.loads(raw_result["vehiclepositions"]):
                results.append(
                    {**vehicle_position, "lineId": str(raw_result["lineid"])}
                )

        return results
