import requests
import json

url = "https://api.mobilitytwin.brussels/environment/weather"

data = requests.get(url, headers={
    "Authorization": "Bearer ebd2fc1bbdeac8d6ed38e3caeb423f8927f3a9bf3f6a2799de933384df4c8659dac3cb2e2b2240bbcc73877fc76675cb90239a80c99475ce070bacd1c3efbbd9"
}).json()

# optional: pretty print the response
print(json.dumps(data, indent=2))