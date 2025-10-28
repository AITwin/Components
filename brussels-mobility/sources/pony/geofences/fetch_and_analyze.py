import requests, geopandas as gpd, folium, json

# --- CONFIG ---
URL   = "https://api.mobilitytwin.brussels/pony/geofences"
TOKEN = "7eba4bf32fcb9502a0ff273fb3191db5b0bbde7cc7f75dc40304dcf2a91c07ed67a55cbbd4e26bf2675e01c5a19d4e7abf92849a5a9fe36d30b558d567dd10cc"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

CRS_WGS84  = "EPSG:4326"
CRS_METRIC = 3812

def normalize_rules(val):
    if isinstance(val, list): return val
    if isinstance(val, str):
        try: return json.loads(val)
        except: return []
    return []

def main():
    # Fetch geofences
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    features = r.json().get("features", [])
    if not features:
        raise SystemExit("No Pony geofences found.")

    gdf = gpd.GeoDataFrame.from_features(features, crs=CRS_WGS84)
    gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    if gdf.empty:
        raise SystemExit("No valid polygon geofences.")

    # Normalize rules
    gdf["rules"] = gdf.get("rules", []).apply(normalize_rules)

    # Separate by zone type
    parking_zones = gdf[gdf["rules"].apply(lambda rs: any(r.get("station_parking") is True for r in rs))].copy()
    no_ride_zones = gdf[gdf["rules"].apply(lambda rs: any(r.get("ride_allowed") is False for r in rs))].copy()
    regular_zones = gdf[~gdf.index.isin(parking_zones.index) & ~gdf.index.isin(no_ride_zones.index)].copy()

    # Create map
    center = gdf.geometry.iloc[0].centroid
    m = folium.Map([center.y, center.x], zoom_start=12)
    m.get_root().html.add_child(folium.Element(
        "<style>html,body{height:100%;margin:0}.folium-map{height:100vh;width:100%}</style>"
    ))

    # Draw parking zones (green)
    for _, row in parking_zones.iterrows():
        name = row.get("name", "Parking zone")
        folium.GeoJson(
            row.geometry.__geo_interface__,
            style_function=lambda f: {"color": "#2ca02c", "weight": 2, "fill": True, "fillOpacity": 0.3},
            tooltip=f"{name} (Parking)"
        ).add_to(m)

    # Draw no-ride zones (red)
    for _, row in no_ride_zones.iterrows():
        name = row.get("name", "No-ride zone")
        folium.GeoJson(
            row.geometry.__geo_interface__,
            style_function=lambda f: {"color": "#d62728", "weight": 2, "fill": True, "fillOpacity": 0.3},
            tooltip=f"{name} (No-ride)"
        ).add_to(m)

    # Draw regular service zones (blue)
    for _, row in regular_zones.iterrows():
        name = row.get("name", "Service zone")
        folium.GeoJson(
            row.geometry.__geo_interface__,
            style_function=lambda f: {"color": "#1f77b4", "weight": 2, "fill": True, "fillOpacity": 0.2},
            tooltip=name
        ).add_to(m)

    m.save("pony_zones.html")
    print(f"✅ Saved pony_zones.html | Parking: {len(parking_zones)} | No-ride: {len(no_ride_zones)} | Regular: {len(regular_zones)}")

if __name__ == "__main__":
    main()
