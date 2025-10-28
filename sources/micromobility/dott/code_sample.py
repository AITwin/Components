import requests
import geopandas as gpd

# API endpoint
url = "https://api.mobilitytwin.brussels/micromobility/dott"

# Replace with your token before running
token = "ebd2fc1bbdeac8d6ed38e3caeb423f8927f3a9bf3f6a2799de933384df4c8659dac3cb2e2b2240bbcc73877fc76675cb90239a80c99475ce070bacd1c3efbbd9"

# Call API
headers = {"Authorization": f"Bearer {token}"}
data = requests.get(url, headers=headers).json()

# Convert to GeoDataFrame and plot
gdf = gpd.GeoDataFrame.from_features(data["features"])
print(gdf.head())   # preview a few rows
gdf.plot()