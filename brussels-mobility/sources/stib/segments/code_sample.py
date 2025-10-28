import requests
import geopandas as gpd

# STIB Segments
url = "https://api.mobilitytwin.brussels/stib/segments"

# Replace with your token before running
token = "MY_API_KEY"

# Fetch latest segments
data = requests.get(url, headers={"Authorization": f"Bearer {token}"}).json()

# To GeoDataFrame and quick peek/plot
gdf = gpd.GeoDataFrame.from_features(data["features"])
print(gdf.head())   # first rows in console
gdf.plot()