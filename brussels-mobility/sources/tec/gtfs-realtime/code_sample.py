import requests
from google.transit import gtfs_realtime_pb2

url = "https://api.mobilitytwin.brussels/tec/gtfs-realtime"

data = requests.get(url, headers={
        'Authorization': 'Bearer MY_API_KEY'
}).content

feed = gtfs_realtime_pb2.FeedMessage()
feed.ParseFromString(data)