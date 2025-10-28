import requests, folium
from folium.plugins import MarkerCluster

TOKEN = "7eba4bf32fcb9502a0ff273fb3191db5b0bbde7cc7f75dc40304dcf2a91c07ed67a55cbbd4e26bf2675e01c5a19d4e7abf92849a5a9fe36d30b558d567dd10cc"   # replace with your real token
URL = "https://api.mobilitytwin.brussels/lime/vehicle-position"

MAX_RANGE_METERS = 60000.0      #full battery = 60 km
LOW_BATTERY_THRESHOLD = 15.0    # percent

def main():
    # Fetch live vehicle data
    response = requests.get(URL, headers={"Authorization": f"Bearer {TOKEN}"})
    response.raise_for_status()
    vehicles = response.json().get("features", []) or []
    if not vehicles:
        raise SystemExit("No vehicles found in snapshot")

    # Filter only scooters below threshold
    low_battery_scooters = []
    for vehicle in vehicles:
        props = vehicle.get("properties") or {}
        if (props.get("vehicle_type") or "").lower() != "scooter":
            continue

        current_range = props.get("current_range_meters")
        if current_range is None:
            continue
        current_range = float(current_range)

        battery_percent = (current_range / MAX_RANGE_METERS) * 100.0
        if battery_percent >= LOW_BATTERY_THRESHOLD:
            continue

        lon, lat = vehicle["geometry"]["coordinates"][:2]
        low_battery_scooters.append((lat, lon, current_range/1000.0, battery_percent))  # km + %

    if not low_battery_scooters:
        raise SystemExit("No scooters under 15% range right now.")

    # Build map
    map_center = [low_battery_scooters[0][0], low_battery_scooters[0][1]]
    map_object = folium.Map(location=map_center, zoom_start=12)
    cluster = MarkerCluster().add_to(map_object)

    for lat, lon, range_km, battery_pct in low_battery_scooters:
        folium.CircleMarker(
            [lat, lon],
            radius=5,
            color="red",
            fill=True,
            fill_opacity=0.9,
            popup=f"Range left: {range_km:.1f} km ({battery_pct:.1f}%)"
        ).add_to(cluster)

    map_object.save("map_low_range.html")
    print("✓ Saved map_low_range.html")

if __name__ == "__main__":
    main()