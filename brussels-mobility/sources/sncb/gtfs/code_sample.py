import requests

# API endpoint
url = "https://api.mobilitytwin.brussels/sncb/gtfs"

# Replace with your token before running
token = "MY_API_KEY"

# Download GTFS ZIP
headers = {"Authorization": f"Bearer {token}"}
data = requests.get(url, headers=headers, timeout=60).content

# Save to disk
with open("sncb_gtfs.zip", "wb") as f:
    f.write(data)

print("Saved sncb_gtfs.zip")