import requests, geopandas as gpd, folium

# --- CONFIG ---
URL   = "https://api.mobilitytwin.brussels/traffic/bike-counters"
TOKEN = "YOUR_BEARER_TOKEN_HERE"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

CRS_WGS84  = "EPSG:4326"
CRS_METRIC = 3812

def main():
    # Fetch bike counter locations
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    features = r.json().get("features", [])
    if not features:
        raise SystemExit("No bike counters found.")

    gdf = gpd.GeoDataFrame.from_features(features, crs=CRS_WGS84)
    gdf = gdf[gdf.geometry.geom_type == "Point"].copy()
    if gdf.empty:
        raise SystemExit("No valid counter locations.")

    # Filter active counters
    active = gdf[gdf.get("active", False) == True].copy()
    inactive = gdf[gdf.get("active", False) == False].copy()

    # Create map
    center = gdf.geometry.iloc[0]
    m = folium.Map([center.y, center.x], zoom_start=12)
    m.get_root().html.add_child(folium.Element(
        "<style>html,body{height:100%;margin:0}.folium-map{height:100vh;width:100%}</style>"
    ))

    # Plot active counters (green)
    for _, row in active.iterrows():
        g = row.geometry
        device = row.get("device_name", "Unknown")
        road = row.get("road_en", row.get("road_fr", "Road"))
        descr = row.get("descr_en", row.get("descr_fr", "Counter"))
        
        label = f"{device} — {road}"
        popup = f"<b>{device}</b><br>{road}<br>{descr}<br>Status: Active"
        
        folium.CircleMarker([g.y, g.x], radius=6, color="#2ca02c", fill=True,
                            fill_opacity=0.9, tooltip=label, popup=popup).add_to(m)

    # Plot inactive counters (gray)
    for _, row in inactive.iterrows():
        g = row.geometry
        device = row.get("device_name", "Unknown")
        road = row.get("road_en", row.get("road_fr", "Road"))
        
        label = f"{device} — {road} (inactive)"
        
        folium.CircleMarker([g.y, g.x], radius=4, color="#7f7f7f", fill=True,
                            fill_opacity=0.5, tooltip=label).add_to(m)

    # Fit bounds
    lats = [g.y for g in gdf.geometry]
    lons = [g.x for g in gdf.geometry]
    m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])

    m.save("bike_counters_map.html")
    print(f"✅ Saved bike_counters_map.html | Active: {len(active)} | Inactive: {len(inactive)}")

if __name__ == "__main__":
    main()
