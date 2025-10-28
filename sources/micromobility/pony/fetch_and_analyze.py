import requests, geopandas as gpd, folium, pandas as pd
from branca.colormap import linear

# --- CONFIG ---
URL   = "https://api.mobilitytwin.brussels/micromobility/pony"
TOKEN = "7eba4bf32fcb9502a0ff273fb3191db5b0bbde7cc7f75dc40304dcf2a91c07ed67a55cbbd4e26bf2675e01c5a19d4e7abf92849a5a9fe36d30b558d567dd10cc"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

CRS_WGS84  = "EPSG:4326"
CRS_METRIC = 3812

def main():
    # Fetch Pony vehicles
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    features = r.json().get("features", [])
    if not features:
        raise SystemExit("No Pony vehicles found.")

    gdf = gpd.GeoDataFrame.from_features(features, crs=CRS_WGS84)
    
    # Filter available vehicles with good fuel
    available = gdf[(~gdf.get("is_disabled", True)) & (~gdf.get("is_reserved", True))].copy()
    available["fuel_pct"] = pd.to_numeric(available.get("current_fuel_percent", 0), errors="coerce")
    available = available[available["fuel_pct"] >= 20].copy()
    
    if available.empty:
        print(f"⚠️  No available Pony vehicles with ≥20% fuel (found {len(gdf)} total vehicles).")
        return

    # Color by fuel percentage
    vmin, vmax = 20.0, 100.0
    cmap = linear.RdYlGn_11.scale(vmin, vmax)

    # Create map
    center = available.geometry.iloc[0]
    m = folium.Map([center.y, center.x], zoom_start=13)
    m.get_root().html.add_child(folium.Element(
        "<style>html,body{height:100%;margin:0}.folium-map{height:100vh;width:100%}</style>"
    ))

    # Plot vehicles
    for _, row in available.iterrows():
        g = row.geometry
        fuel_pct = row["fuel_pct"]
        
        color = cmap(fuel_pct)
        label = f"Pony Scooter — {fuel_pct:.0f}% fuel"
        
        folium.CircleMarker([g.y, g.x], radius=4, color=color, fill=True,
                            fill_opacity=0.7, tooltip=label).add_to(m)

    # Add legend
    cmap.caption = "Fuel Level (%)"
    cmap.add_to(m)

    m.save("pony_micromobility_vehicles.html")
    print(f"✅ Saved pony_micromobility_vehicles.html | Available vehicles: {len(available)}")

if __name__ == "__main__":
    main()
