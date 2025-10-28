import requests, geopandas as gpd, folium, pandas as pd
from branca.colormap import linear

# --- CONFIG ---
URL   = "https://api.mobilitytwin.brussels/infrabel/segments"
TOKEN = "7eba4bf32fcb9502a0ff273fb3191db5b0bbde7cc7f75dc40304dcf2a91c07ed67a55cbbd4e26bf2675e01c5a19d4e7abf92849a5a9fe36d30b558d567dd10cc"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

CRS_WGS84  = "EPSG:4326"
CRS_METRIC = 3812

def main():
    # Fetch railway track segments
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    features = r.json().get("features", [])
    if not features:
        raise SystemExit("No Infrabel segments found.")

    gdf = gpd.GeoDataFrame.from_features(features, crs=CRS_WGS84)
    gdf = gdf[gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
    if gdf.empty:
        raise SystemExit("No valid track segments.")

    # Convert length to numeric
    gdf["length_km"] = pd.to_numeric(gdf.get("length", 0), errors="coerce") / 1000.0

    # Color by segment length
    valid_lengths = gdf[gdf["length_km"] > 0].copy()
    if valid_lengths.empty:
        raise SystemExit("No segments with valid length data.")

    vmin, vmax = float(valid_lengths["length_km"].min()), float(valid_lengths["length_km"].max())
    cmap = linear.YlGnBu_09.scale(vmin, vmax)

    # Create map
    center = valid_lengths.geometry.iloc[0].centroid
    m = folium.Map([center.y, center.x], zoom_start=9)
    m.get_root().html.add_child(folium.Element(
        "<style>html,body{height:100%;margin:0}.folium-map{height:100vh;width:100%}</style>"
    ))

    # Draw segments
    for _, row in valid_lengths.iterrows():
        length_km = row["length_km"]
        from_station = row.get("stationfrom_name", "Unknown")
        to_station = row.get("stationto_name", "Unknown")
        
        color = cmap(length_km)
        label = f"{from_station} → {to_station}"
        popup = f"<b>{label}</b><br>Length: {length_km:.2f} km"
        
        folium.GeoJson(
            row.geometry.__geo_interface__,
            style_function=lambda f, c=color: {"color": c, "weight": 3, "opacity": 0.7},
            tooltip=label,
            popup=popup
        ).add_to(m)

    # Add legend
    cmap.caption = "Segment Length (km)"
    cmap.add_to(m)

    m.save("infrabel_segments.html")
    print(f"✅ Saved infrabel_segments.html | Segments: {len(valid_lengths)}")

if __name__ == "__main__":
    main()
