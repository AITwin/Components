import requests
import folium
from folium.plugins import MarkerCluster

TOKEN = "7eba4bf32fcb9502a0ff273fb3191db5b0bbde7cc7f75dc40304dcf2a91c07ed67a55cbbd4e26bf2675e01c5a19d4e7abf92849a5a9fe36d30b558d567dd10cc"  
URL = "https://api.mobilitytwin.brussels/dott/vehicle-position"

def main():
    r = requests.get(URL, headers={"Authorization": f"Bearer {TOKEN}"})
    if not r.ok:
        raise SystemExit(f"Error: {r.status_code} {r.text}")

    features = r.json().get("features", [])
    if not features:
        raise SystemExit("No data")

    points = [(f["geometry"]["coordinates"][1], f["geometry"]["coordinates"][0]) for f in features]

    m = folium.Map(location=points[0], zoom_start=12)
    mc = MarkerCluster().add_to(m)
    for lat, lon in points:
        folium.CircleMarker([lat, lon], radius=3).add_to(mc)

    m.save("map.html")
    print("✓ Map saved to map.html — open it in your browser.")

if __name__ == "__main__":
    main()