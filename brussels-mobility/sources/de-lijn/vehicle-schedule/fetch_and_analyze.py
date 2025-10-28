import requests, geopandas as gpd, pandas as pd
from datetime import datetime, timedelta

# --- CONFIG ---
URL   = "https://api.mobilitytwin.brussels/de-lijn/vehicle-schedule"
TOKEN = "7eba4bf32fcb9502a0ff273fb3191db5b0bbde7cc7f75dc40304dcf2a91c07ed67a55cbbd4e26bf2675e01c5a19d4e7abf92849a5a9fe36d30b558d567dd10cc"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

CRS_WGS84  = "EPSG:4326"
CRS_METRIC = 3812

def main():
    # Fetch schedule for next 2 hours
    now = int(datetime.now().timestamp())
    end = int((datetime.now() + timedelta(hours=2)).timestamp())
    
    try:
        r = requests.get(URL, headers=HEADERS, params={"start_timestamp": now, "end_timestamp": end}, timeout=45)
        r.raise_for_status()
        data = r.json()
    except (requests.Timeout, requests.ConnectionError) as e:
        print(f"⚠️  De Lijn API timeout or connection error. Service may be slow or unavailable.")
        print(f"   This is a known issue - the API can be very slow or unresponsive.")
        return
    except Exception as e:
        print(f"⚠️  De Lijn API error: {e}")
        return
    
    if isinstance(data, str):
        print(f"⚠️  API returned string data (check response format)")
        raise SystemExit("Unexpected response format")
    
    features = data.get("features", [])
    if not features:
        raise SystemExit("No De Lijn schedule data found.")

    gdf = gpd.GeoDataFrame.from_features(features, crs=CRS_WGS84)
    
    # Extract schedule details
    rows = []
    for _, row in gdf.iterrows():
        stop_name = row.get("stop_name", "Unknown")
        schedule = row.get("schedule", [])
        
        for trip in schedule:
            rows.append({
                "stop_name": stop_name,
                "route_id": trip.get("route_id", ""),
                "headsign": trip.get("trip_headsign", ""),
                "arrival": trip.get("arrival_time", ""),
                "departure": trip.get("departure_time", "")
            })
    
    df = pd.DataFrame(rows)
    
    # Find busiest stops
    busy_stops = df.groupby("stop_name").size().sort_values(ascending=False).head(20)
    
    print(f"\n{'='*80}")
    print(f"{'De Lijn Vehicle Schedule — Busiest Stops (Next 2 Hours)'}")
    print(f"{'='*80}\n")
    
    print(f"{'Stop Name':<50} | {'Buses':>10}")
    print(f"{'-'*80}")
    for stop, count in busy_stops.items():
        print(f"{stop[:50]:<50} | {count:>10}")
    
    print(f"\n{'='*80}")
    print(f"Total stops: {len(gdf)} | Total passages: {len(df)}")
    print(f"{'='*80}\n")
    
    # Save to CSV
    df.to_csv("de_lijn_schedule.csv", index=False)
    print(f"✅ Saved de_lijn_schedule.csv")
    
    # Create visualizations
    import plotly.express as px
    import folium
    from folium.plugins import MarkerCluster
    
    # Bar chart
    fig = px.bar(
        x=busy_stops.index[:20],
        y=busy_stops.values[:20],
        title='De Lijn Top 20 Busiest Stops (Next 2 Hours)',
        labels={'x': 'Stop Name', 'y': 'Number of Buses'},
        color=busy_stops.values[:20],
        color_continuous_scale='Oranges'
    )
    fig.update_xaxis(tickangle=-45)
    fig.write_html("de_lijn_schedule_chart.html")
    
    # Map
    m = folium.Map([51.0, 4.4], zoom_start=9)
    marker_cluster = MarkerCluster().add_to(m)
    
    for idx, row in gdf.head(200).iterrows():
        geom = row.geometry
        if geom.geom_type == "Point":
            folium.Marker(
                [geom.y, geom.x],
                popup=f"<b>{row.get('stop_name', 'Unknown')}</b>",
                icon=folium.Icon(color='orange', icon='bus', prefix='fa')
            ).add_to(marker_cluster)
    
    m.save("de_lijn_schedule_map.html")
    print(f"✅ Saved de_lijn_schedule_chart.html and de_lijn_schedule_map.html")

if __name__ == "__main__":
    main()
