import requests
import json

url = "https://api.mobilitytwin.brussels/traffic/tunnel-devices"

data = requests.get(url, headers={
        'Authorization': 'Bearer [MY_API_KEY]'
}).json()