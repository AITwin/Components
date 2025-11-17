import requests
import tempfile
import gtfs_kit as gk

url = "https://api.mobilitytwin.brussels/tec/gtfs"

data = requests.get(url, headers={
    'Authorization': 'Bearer [MY_API_KEY]'
}).content

with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
    f.write(data)
    tmp_path = f.name  # path to the downloaded GTFS zip

feed = gk.read_feed(tmp_path, 'm')  # distance units in meters