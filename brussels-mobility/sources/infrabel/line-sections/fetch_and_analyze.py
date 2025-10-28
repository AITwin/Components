import requests, geopandas as gpd, folium

# --- CONFIG ---
URL   = "https://api.mobilitytwin.brussels/infrabel/line-sections"
TOKEN = "7eba4bf32fcb9502a0ff273fb3191db5b0bbde7cc7f75dc40304dcf2a91c07ed67a55cbbd4e26bf2675e01c5a19d4e7abf92849a5a9fe36d30b558d567dd10cc"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

CRS_WGS84  = "EPSG:4326"
CRS_METRIC = 3812

def main():
    # Fetch Infrabel line sections
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    features = r.json().get("features", [])
    if not features:
        raise SystemExit("No Infrabel line sections found.")

    gdf = gpd.GeoDataFrame.from_features(features, crs=CRS_WGS84)
    
    # Filter valid geometries
    valid = gdf[gdf.geometry.notna() & gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
    if valid.empty:
        raise SystemExit("No valid line sections.")

    # Filter active/operational lines
    operational = valid[valid.get("status", "").str.contains("EN SERVICE|IN USE", case=False, na=False)].copy()
    if operational.empty:
        print("⚠️  No explicitly operational lines found, showing all lines.")
        operational = valid.copy()

    # Create map
    center = operational.geometry.iloc[0].centroid
    m = folium.Map([center.y, center.x], zoom_start=9)
    m.get_root().html.add_child(folium.Element(
        "<style>html,body{height:100%;margin:0}.folium-map{height:100vh;width:100%}</style>"
    ))

    # Draw line sections
    for _, row in operational.iterrows():
        line_name = row.get("trackname", "Unknown")
        line_code = row.get("trackcode", "")
        exploitation = row.get("exploitation", "")
        
        label = f"{line_name} ({line_code})"
        popup = f"<b>{line_name}</b><br>Code: {line_code}<br>Type: {exploitation}"
        
        folium.GeoJson(
            row.geometry.__geo_interface__,
            style_function=lambda f: {"color": "#1f77b4", "weight": 2, "opacity": 0.7},
            tooltip=label,
            popup=popup
        ).add_to(m)

    m.save("infrabel_line_sections.html")
    print(f"✅ Saved infrabel_line_sections.html | Line sections: {len(operational)}")

if __name__ == "__main__":
    main()
