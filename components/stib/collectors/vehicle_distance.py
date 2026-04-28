import json
from typing import Dict, List

from src.components import Collector
from src.utilities.bmc import bmc_request

LIMIT = 100


class STIBVehiclePositionsCollector(Collector):
    def run(self) -> List[Dict]:
        records = []
        offset = 0

        while True:
            response = bmc_request(
                "/api/datasets/stibmivb/rt/VehiclePositions",
                params={"limit": LIMIT, "offset": offset},
            )
            data = response.json()
            page = data.get("results", [])
            records.extend(page)

            total_count = data.get("total_count")
            if total_count is None:
                if len(page) < LIMIT:
                    break
            elif offset + LIMIT >= total_count:
                break
            offset += LIMIT

        results = []
        for record in records:
            line_id = str(record.get("lineid", ""))
            vehicle_positions = record.get("vehiclepositions", "[]")
            if isinstance(vehicle_positions, str):
                vehicle_positions = json.loads(vehicle_positions)

            for vehicle_position in vehicle_positions:
                results.append({**vehicle_position, "lineId": line_id})

        return results
