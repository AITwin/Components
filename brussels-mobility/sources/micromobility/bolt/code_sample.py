import requests
import geopandas as gpd

# API endpoint
url = "https://api.mobilitytwin.brussels/micromobility/bolt"

# Replace with your token before running
token = "MY_API_KEY"

# Call API
headers = {"Authorization": f"Bearer {token}"}
data = requests.get(url, headers=headers).json()

# Convert to GeoDataFrame and plot
gdf = gpd.GeoDataFrame.from_features(data["features"])
print(gdf.head())   # preview a few rows
gdf.plot()