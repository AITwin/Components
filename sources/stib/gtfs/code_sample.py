import gtfs_kit as gk
import requests
import tempfile

url = "https://api.mobilitytwin.brussels/stib/gtfs"

data = requests.get(url,  headers={
        'Authorization': 'Bearer [MY_API_KEY]'
}).content

with tempfile.NamedTemporaryFile(delete=False) as f:
    f.write(data)

feed = gk.read_feed(f.name, 'm')