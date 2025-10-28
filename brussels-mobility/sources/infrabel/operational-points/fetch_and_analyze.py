import requests, geopandas as gpd, folium

# --- CONFIG ---
URL   = "https://api.mobilitytwin.brussels/infrabel/operational-points"
TOKEN = "YOUR_BEARER_TOKEN_HERE"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

CRS_WGS84  = "EPSG:4326"
CRS_METRIC = 3812

def main():
    # Fetch operational points (stations)
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    features = r.json().get("features", [])
    if not features:
        raise SystemExit("No operational points found.")

    gdf = gpd.GeoDataFrame.from_features(features, crs=CRS_WGS84)
    gdf = gdf[gdf.geometry.geom_type == "Point"].copy()
    if gdf.empty:
        raise SystemExit("No valid operational points.")

    # Classify by type
    gdf["class"] = gdf.get("class_en", "Unknown")
    
    # Separate stations from other points
    stations = gdf[gdf["class"].str.contains("station", case=False, na=False)].copy()
    other_points = gdf[~gdf.index.isin(stations.index)].copy()

    # Create map
    center = gdf.geometry.iloc[0]
    m = folium.Map([center.y, center.x], zoom_start=9)
    m.get_root().html.add_child(folium.Element(
        "<style>html,body{height:100%;margin:0}.folium-map{height:100vh;width:100%}</style>"
    ))

    # Plot stations (larger, blue)
    for _, row in stations.iterrows():
        g = row.geometry
        name_en = row.get("commercialshortnamedutch", row.get("shortnamedutch", "Station"))
        name_fr = row.get("commercialshortnamefrench", row.get("shortnamefrench", ""))
        class_type = row.get("class_en", "Station")
        
        label = name_en if name_en != name_fr else f"{name_en} / {name_fr}"
        popup = f"<b>{label}</b><br>Type: {class_type}"
        
        folium.CircleMarker([g.y, g.x], radius=6, color="#1f77b4", fill=True,
                            fill_opacity=0.8, tooltip=label, popup=popup).add_to(m)

    # Plot other operational points (smaller, orange)
    for _, row in other_points.iterrows():
        g = row.geometry
        name_en = row.get("shortnamedutch", "Point")
        class_type = row.get("class_en", "Point")
        
        folium.CircleMarker([g.y, g.x], radius=3, color="#ff7f0e", fill=True,
                            fill_opacity=0.6, tooltip=f"{name_en} ({class_type})").add_to(m)

    m.save("infrabel_operational_points.html")
    print(f"✅ Saved infrabel_operational_points.html | Stations: {len(stations)} | Other points: {len(other_points)}")

if __name__ == "__main__":
    main()
