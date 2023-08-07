from sqlalchemy import Row

from src.components import Harvester
from src.utilities.zip_to_dict import zip_to_dict


class SNCBGTFSJSONHarvester(Harvester):
    def run(self, source: Row):
        output = zip_to_dict(source.data)

        return output
