import requests
import geopandas as gpd

url = "https://api.mobilitytwin.brussels/bolt/vehicle-position"
token = "MY_API_KEY"

headers = {"Authorization": f"Bearer {token}"}
data = requests.get(url, headers=headers).json()

gdf = gpd.GeoDataFrame.from_features(data["features"])
print(gdf.head())
gdf.plot()