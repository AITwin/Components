import json
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from src.components import Harvester

class CountHarvester(Harvester):
   def run(self, sources, micromobility_area):
      # Load the GeoDataFrame directly from the JSON data
      shapefile = gpd.GeoDataFrame.from_features(json.loads(micromobility_area.data)["features"],crs="EPSG:4326")
      
      # Convert sources data to GeoDataFrame
      df = pd.json_normalize(sources[-1].data["features"])
      df['geometry_point'] = df['geometry.coordinates'].apply(Point)
      gdf = gpd.GeoDataFrame(df, geometry="geometry_point", crs="EPSG:4326")
      
      # Perform the spatial join
      data = gpd.sjoin(shapefile, gdf, how="left", op='contains')
      
      # Group by poly_id and count occurrences
      df2 = data.groupby(['poly_id'])['properties.bike_id'].count().reset_index()
      df2.rename(columns={'properties.bike_id': "ebike_availibility"}, inplace=True)
      
      # Convert the result to a dictionary
      result = df2.set_index('poly_id').to_dict(orient='index')
      
      return result