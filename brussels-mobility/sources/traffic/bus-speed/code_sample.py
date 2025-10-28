import requests

url = "https://api.mobilitytwin.brussels/traffic/bus-speed"

data = requests.get(url, headers={
        'Authorization': 'Bearer [MY_API_KEY]'
}).json()