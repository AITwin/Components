import requests, geopandas as gpd, folium

# --- CONFIG ---
URL   = "https://api.mobilitytwin.brussels/traffic/tunnel-devices"
TOKEN = "7eba4bf32fcb9502a0ff273fb3191db5b0bbde7cc7f75dc40304dcf2a91c07ed67a55cbbd4e26bf2675e01c5a19d4e7abf92849a5a9fe36d30b558d567dd10cc"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

CRS_WGS84  = "EPSG:4326"
CRS_METRIC = 3812

def main():
    # Fetch tunnel device locations
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    features = r.json().get("features", [])
    if not features:
        raise SystemExit("No tunnel devices found.")

    gdf = gpd.GeoDataFrame.from_features(features, crs=CRS_WGS84)
    gdf = gdf[gdf.geometry.geom_type == "Point"].copy()
    # Filter out empty geometries
    gdf = gdf[~gdf.geometry.is_empty].copy()
    if gdf.empty:
        raise SystemExit("No valid device locations.")

    # Create map
    center = gdf.geometry.iloc[0]
    m = folium.Map([center.y, center.x], zoom_start=11)
    m.get_root().html.add_child(folium.Element(
        "<style>html,body{height:100%;margin:0}.folium-map{height:100vh;width:100%}</style>"
    ))

    # Plot each detector
    for _, row in gdf.iterrows():
        g = row.geometry
        traverse = row.get("traverse_name", "Unknown")
        descr = row.get("descr_en", row.get("descr_fr", "Detector"))
        lanes = row.get("number_of_lanes", "?")
        detectors = row.get("detectors", [])
        detector_list = ", ".join(detectors) if detectors else "N/A"
        
        label = f"{traverse} — {descr}"
        popup = f"<b>{traverse}</b><br>{descr}<br>Lanes: {lanes}<br>Detectors: {detector_list}"
        
        folium.CircleMarker([g.y, g.x], radius=5, color="#ff7f0e", fill=True,
                            fill_opacity=0.8, tooltip=label, popup=popup).add_to(m)

    # Fit bounds
    lats = [g.y for g in gdf.geometry]
    lons = [g.x for g in gdf.geometry]
    m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])

    m.save("tunnel_devices_map.html")
    print(f"✅ Saved tunnel_devices_map.html | Devices: {len(gdf)}")

if __name__ == "__main__":
    main()
