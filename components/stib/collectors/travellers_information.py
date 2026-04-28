from src.components import Collector
from src.utilities.bmc import bmc_request

LIMIT = 100


class STIBTravellersInformationCollector(Collector):
    def run(self):
        all_results = []
        offset = 0

        while True:
            response = bmc_request(
                "/api/datasets/stibmivb/rt/TravellersInformation",
                params={"limit": LIMIT, "offset": offset},
            )
            data = response.json()
            results = data.get("results", [])
            all_results.extend(results)

            total_count = data.get("total_count")
            if total_count is None:
                if len(results) < LIMIT:
                    break
            elif offset + LIMIT >= total_count:
                break
            offset += LIMIT

        return {"results": all_results, "total_count": len(all_results)}
