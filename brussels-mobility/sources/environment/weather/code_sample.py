import requests
import json

url = "https://api.mobilitytwin.brussels/environment/weather"

data = requests.get(url, headers={
    "Authorization": "Bearer YOUR_BEARER_TOKEN_HERE"
}).json()

# optional: pretty print the response
print(json.dumps(data, indent=2))