import json

import geopandas as gpd
import pandas as pd
from geopandas import GeoDataFrame

# from components.stib.harvesters.identify_vehicle.algorithm import IdentifyVehicleAlgorithm
# from components.stib.utils.converter import convert_shapefile_line_to_stops_line
from src.components import Harvester




class LocationCreator(Harvester):
     def run(self):
        dataframe = gpd.read_parquet("area.parquet")
        return dataframe.to_json(drop_id=False)