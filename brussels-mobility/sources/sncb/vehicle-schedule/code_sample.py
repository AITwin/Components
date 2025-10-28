import requests
import geopandas as gpd
from datetime import datetime, timedelta, timezone

# API endpoint
url = "https://api.mobilitytwin.brussels/sncb/vehicle-schedule"

# Replace with your token before running
token = "MY_API_KEY"

# Build a short time window for the example
now = datetime.now(timezone.utc)
params = {
    "start_timestamp": int((now - timedelta(minutes=30)).timestamp()),
    "end_timestamp": int(now.timestamp())
}

# Call API
headers = {"Authorization": f"Bearer {token}"}
resp = requests.get(url, headers=headers, params=params)
data = resp.json()

# Convert to GeoDataFrame and plot
gdf = gpd.GeoDataFrame.from_features(data["features"])
print(gdf.head())   # show first few rows in console
gdf.plot()
