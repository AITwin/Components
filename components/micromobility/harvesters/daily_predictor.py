import json
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from src.components import Harvester

class DailyPredictorHarvester(Harvester):
   def run(self, source, bolt_count):
      # print(bolt_count[0])
      # print("cd",source)
      for i in bolt_count:
         print(i[0])
      return {"test": "test"}
   