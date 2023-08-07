from components.stib.utils.fetch import auth_request_to_stib
from src.components import Collector


class STIBGTFSCollector(Collector):
    def run(self) -> bytes:
        response = auth_request_to_stib(
            "https://stibmivb.opendatasoft.com/api/explore/v2.1/catalog/datasets/gtfs-files-production"
            "/alternative_exports/gtfszip/"
        )

        return response.content
