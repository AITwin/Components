import requests, geopandas as gpd, folium
from branca.colormap import linear

# --- CONFIG ---
URL   = "https://api.mobilitytwin.brussels/micromobility/lime"
TOKEN = "YOUR_BEARER_TOKEN_HERE"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

CRS_WGS84  = "EPSG:4326"
CRS_METRIC = 3812

def main():
    # Fetch Lime vehicles
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    features = r.json().get("features", [])
    if not features:
        raise SystemExit("No Lime vehicles found.")

    gdf = gpd.GeoDataFrame.from_features(features, crs=CRS_WGS84)
    
    # Filter available vehicles
    available = gdf[(~gdf.get("is_disabled", True)) & (~gdf.get("is_reserved", True))].copy()
    if available.empty:
        raise SystemExit("No available Lime vehicles.")

    # Calculate range in km
    available["range_km"] = available.get("current_range_meters", 0) / 1000.0
    available = available[available["range_km"] > 0].copy()
    
    # Color by range
    vmin, vmax = float(available["range_km"].min()), float(available["range_km"].max())
    cmap = linear.YlGnBu_09.scale(vmin, vmax)

    # Create map
    center = available.geometry.iloc[0]
    m = folium.Map([center.y, center.x], zoom_start=13)
    m.get_root().html.add_child(folium.Element(
        "<style>html,body{height:100%;margin:0}.folium-map{height:100vh;width:100%}</style>"
    ))

    # Plot vehicles
    for _, row in available.iterrows():
        g = row.geometry
        range_km = row["range_km"]
        vehicle_type = row.get("vehicle_type", "Unknown")
        
        color = cmap(range_km)
        label = f"{vehicle_type} — {range_km:.1f} km"
        
        folium.CircleMarker([g.y, g.x], radius=4, color=color, fill=True,
                            fill_opacity=0.7, tooltip=label).add_to(m)

    # Add legend
    cmap.caption = "Range (km)"
    cmap.add_to(m)

    m.save("lime_vehicles.html")
    print(f"✅ Saved lime_vehicles.html | Available vehicles: {len(available)}")

if __name__ == "__main__":
    main()
