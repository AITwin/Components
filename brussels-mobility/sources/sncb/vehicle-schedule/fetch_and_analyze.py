import requests, geopandas as gpd, folium, pandas as pd
from folium.plugins import MarkerCluster

URL = "https://api.mobilitytwin.brussels/sncb/vehicle-schedule"
TOKEN = "7eba4bf32fcb9502a0ff273fb3191db5b0bbde7cc7f75dc40304dcf2a91c07ed67a55cbbd4e26bf2675e01c5a19d4e7abf92849a5a9fe36d30b558d567dd10cc"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

def main():
    """Fetch SNCB vehicle schedules and create map."""
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        
        data = resp.json()
        features = data.get("features", [])
        print(f"✓ Fetched {len(features)} vehicle schedules")
        
        if not features:
            print("No schedule data available")
            return
        
        # Create GeoDataFrame
        gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
        
        # Count stops
        stop_counts = gdf.groupby('stop_name').size().sort_values(ascending=False)
        
        # Create map
        m = folium.Map([50.8503, 4.3517], zoom_start=10)
        marker_cluster = MarkerCluster().add_to(m)
        
        for idx, row in gdf.head(200).iterrows():  # Limit to 200 for performance
            geom = row.geometry
            if geom.geom_type == "Point":
                folium.Marker(
                    [geom.y, geom.x],
                    popup=f"<b>{row.get('stop_name', 'Unknown')}</b><br>Line: {row.get('route_short_name', 'N/A')}",
                    icon=folium.Icon(color='blue', icon='train', prefix='fa')
                ).add_to(marker_cluster)
        
        m.save("sncb_schedule_map.html")
        print(f"✅ Saved sncb_schedule_map.html | Stops shown: {min(200, len(gdf))}")
        
        # Top stops
        print(f"\nTop 10 busiest stops:")
        for stop, count in stop_counts.head(10).items():
            print(f"  {stop}: {count} scheduled passages")
        
    except requests.HTTPError as e:
        if e.response.status_code == 500:
            print("⚠️  SNCB vehicle-schedule API returned server error (500). Service may be temporarily unavailable.")
            return
        raise

if __name__ == "__main__":
    main()
