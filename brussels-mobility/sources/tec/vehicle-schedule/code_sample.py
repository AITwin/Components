import requests
import geopandas as gpd

url = "https://api.mobilitytwin.brussels/tec/vehicle-schedule"

data = requests.get(url, headers={
        'Authorization': 'Bearer [MY_API_KEY]'
}).json()

gdf = gpd.GeoDataFrame.from_features(data["features"])
# Plot the GeoDataFrame
gdf.plot()