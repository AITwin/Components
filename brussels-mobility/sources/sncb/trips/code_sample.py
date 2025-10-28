import requests, time, json

# API endpoint
url = "https://api.mobilitytwin.brussels/sncb/trips"

# Replace with your token before running
token = "MY_API_KEY"

# Minimal time window: last 30 minutes
end_ts = int(time.time())
start_ts = end_ts - 1800

# Call API
headers = {"Authorization": f"Bearer {token}"}
params = {"start_timestamp": start_ts, "end_timestamp": end_ts}
data = requests.get(url, headers=headers, params=params).json()

# Some deployments return a JSON *string*; handle both
if isinstance(data, str):
    data = json.loads(data)

# Show a tiny preview (first 3 trips)
features = data.get("features", [])[:3]
print(f"Trips returned: {len(data.get('features', []))}. Showing {len(features)}:")
for f in features:
    p = f.get("properties", {})
    print(p.get("trip_id"), "→", p.get("trip_headsign"), "|", p.get("name_start"), "→", p.get("name_end"))