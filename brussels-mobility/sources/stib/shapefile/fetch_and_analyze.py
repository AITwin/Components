import requests, geopandas as gpd, folium

# --- CONFIG ---
URL   = "https://api.mobilitytwin.brussels/stib/shapefile"
TOKEN = "7eba4bf32fcb9502a0ff273fb3191db5b0bbde7cc7f75dc40304dcf2a91c07ed67a55cbbd4e26bf2675e01c5a19d4e7abf92849a5a9fe36d30b558d567dd10cc"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

CRS_WGS84  = "EPSG:4326"
CRS_METRIC = 3812

def main():
    # Fetch STIB shapefile (route network)
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    features = r.json().get("features", [])
    if not features:
        raise SystemExit("No STIB shapefile data found.")

    gdf = gpd.GeoDataFrame.from_features(features, crs=CRS_WGS84)
    gdf = gdf[gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
    if gdf.empty:
        raise SystemExit("No valid route lines.")

    # Create map
    center = gdf.geometry.iloc[0].centroid
    m = folium.Map([center.y, center.x], zoom_start=12)
    m.get_root().html.add_child(folium.Element(
        "<style>html,body{height:100%;margin:0}.folium-map{height:100vh;width:100%}</style>"
    ))

    # Group by line
    lines = gdf.groupby("ligne")

    # Draw each line with its official color
    for line_id, line_gdf in lines:
        # Get the color (use first variant's color)
        color = line_gdf.iloc[0].get("color_hex", "#888888")
        if not color.startswith("#"):
            color = f"#{color}"
        
        line_name = line_id
        
        # Draw all segments of this line
        for _, row in line_gdf.iterrows():
            folium.GeoJson(
                row.geometry.__geo_interface__,
                style_function=lambda f, c=color: {"color": c, "weight": 3, "opacity": 0.7},
                tooltip=f"Line {line_name}"
            ).add_to(m)

    m.save("stib_network_map.html")
    print(f"✅ Saved stib_network_map.html | Lines: {len(lines)} | Segments: {len(gdf)}")

if __name__ == "__main__":
    main()
