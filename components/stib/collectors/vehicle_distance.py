import json
from typing import Dict, List

from src.components import Collector
from src.utilities.bmc import bmc_request_all


class STIBVehiclePositionsCollector(Collector):
    def run(self) -> List[Dict]:
        results = []
        for record in bmc_request_all(
            "/api/datasets/stibmivb/rt/VehiclePositions"
        ):
            line_id = str(record.get("lineid", ""))
            vehicle_positions = record.get("vehiclepositions", "[]")
            if isinstance(vehicle_positions, str):
                vehicle_positions = json.loads(vehicle_positions)

            for vehicle_position in vehicle_positions:
                results.append({**vehicle_position, "lineId": line_id})

        return results
