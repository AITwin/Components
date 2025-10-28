import requests, geopandas as gpd, folium

# --- CONFIG ---
URL   = "https://api.mobilitytwin.brussels/stib/segments"
TOKEN = "YOUR_BEARER_TOKEN_HERE"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

CRS_WGS84  = "EPSG:4326"
CRS_METRIC = 3812

def main():
    # Fetch STIB network segments
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    
    # API returns string, need special handling
    if isinstance(data, str):
        print(f"⚠️  Segments endpoint returns non-standard format")
        print(f"✅ Data retrieved: {len(data)} characters")
        print(f"First 200 chars: {data[:200]}")
        return
    
    features = data.get("features", [])
    if not features:
        raise SystemExit("No segments found.")

    gdf = gpd.GeoDataFrame.from_features(features, crs=CRS_WGS84)
    gdf = gdf[gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
    
    if gdf.empty:
        raise SystemExit("No valid segments.")

    # Create map
    center = gdf.geometry.iloc[0].centroid
    m = folium.Map([center.y, center.x], zoom_start=12)
    m.get_root().html.add_child(folium.Element(
        "<style>html,body{height:100%;margin:0}.folium-map{height:100vh;width:100%}</style>"
    ))

    # Draw segments
    for _, row in gdf.iterrows():
        folium.GeoJson(
            row.geometry.__geo_interface__,
            style_function=lambda f: {"color": "#1976d2", "weight": 2, "opacity": 0.6}
        ).add_to(m)

    m.save("stib_segments.html")
    print(f"✅ Saved stib_segments.html | Segments: {len(gdf)}")

if __name__ == "__main__":
    main()
