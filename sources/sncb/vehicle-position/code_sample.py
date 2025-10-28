import requests
import geopandas as gpd

# API endpoint
url = "https://api.mobilitytwin.brussels/sncb/vehicle-position"

# Replace with your token before running
token = "MY_API_KEY"

# Call API (latest snapshot if no params)
headers = {"Authorization": f"Bearer {token}"}
data = requests.get(url, headers=headers).json()

# Convert to GeoDataFrame and plot
gdf = gpd.GeoDataFrame.from_features(data["features"])
print(gdf.head())   # show first few rows in console
gdf.plot()
