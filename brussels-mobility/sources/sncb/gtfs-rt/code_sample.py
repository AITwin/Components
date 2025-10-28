import requests
from google.transit import gtfs_realtime_pb2  # pip install gtfs-realtime-bindings

url = "https://api.mobilitytwin.brussels/sncb/gtfs-realtime"
data = requests.get(url, headers={"Authorization": "Bearer MY_API_KEY"}).content

feed = gtfs_realtime_pb2.FeedMessage()
feed.ParseFromString(data)
print(f"entities: {len(feed.entity)}")