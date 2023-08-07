from components.stib.utils.fetch import auth_request_to_stib
from src.components import Collector


class STIBShapeFilesCollector(Collector):
    def run(self) -> dict:
        response = auth_request_to_stib(
            "https://stibmivb.opendatasoft.com/api/explore/v2.1/catalog/datasets/shapefiles-production/exports/geojson"
        )

        return response.json()
