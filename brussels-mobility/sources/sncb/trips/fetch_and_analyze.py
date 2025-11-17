import requests, geopandas as gpd, folium
from folium.plugins import MarkerCluster

URL = "https://api.mobilitytwin.brussels/sncb/trips"
TOKEN = "YOUR_BEARER_TOKEN_HERE"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

def main():
    """Fetch SNCB trip trajectories and create map."""
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=60)
        resp.raise_for_status()
    except requests.HTTPError as e:
        if e.response.status_code == 500:
            print(f"⚠️  SNCB trips API returned server error (500). Service may be temporarily unavailable.")
            return
        raise
    except (requests.Timeout, requests.ConnectionError) as e:
        print(f"⚠️  SNCB trips API timeout or connection error. Service may be slow or unavailable.")
        return
    
    try:
        data = resp.json()
        features = data.get("features", [])
        print(f"✓ Fetched {len(features)} trip trajectories")
        
        if not features:
            print("No trip data available")
            return
        
        # This API uses temporalGeometry (moving trajectories) not static geometry
        # Extract trajectory data
        import pandas as pd
        trips_data = []
        for f in features[:100]:  # Limit for performance
            props = f.get("properties", {})
            temp_geom = f.get("temporalGeometry", {})
            coords = temp_geom.get("coordinates", [])
            
            trip_id = props.get("trip_id", "Unknown")
            headsign = props.get("trip_headsign", "")
            
            if coords and len(coords) > 0:
                trips_data.append({
                    "trip_id": trip_id,
                    "headsign": headsign,
                    "coords": coords,
                    "num_points": len(coords)
                })
        
        if not trips_data:
            print("No valid trip trajectories found")
            return
        
        # Create map
        m = folium.Map([50.8503, 4.3517], zoom_start=10)
        
        # Add trip trajectories
        colors = ['blue', 'red', 'green', 'purple', 'orange', 'darkred', 'lightred', 'darkblue', 'darkgreen', 'cadetblue']
        for idx, trip in enumerate(trips_data):
            coords_latlon = [[lat, lon] for lon, lat in trip['coords']]
            color = colors[idx % len(colors)]
            
            folium.PolyLine(
                coords_latlon,
                color=color,
                weight=2,
                opacity=0.7,
                popup=f"<b>Trip:</b> {trip['trip_id']}<br><b>To:</b> {trip['headsign']}<br><b>Points:</b> {trip['num_points']}"
            ).add_to(m)
        
        m.save("sncb_trips_map.html")
        print(f"✅ Saved sncb_trips_map.html | Trips shown: {len(trips_data)}")
        
    except (requests.Timeout, requests.ConnectionError) as e:
        print(f"⚠️  SNCB trips API timeout or connection error. Service may be slow or unavailable.")
        return

if __name__ == "__main__":
    main()
