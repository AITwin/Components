import requests, geopandas as gpd, folium
from branca.colormap import linear

# --- CONFIG ---
URL   = "https://api.mobilitytwin.brussels/pony/vehicle-position"
TOKEN = "YOUR_BEARER_TOKEN_HERE"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

CRS_WGS84  = "EPSG:4326"
CRS_METRIC = 3812

def main():
    # Fetch live Pony scooters
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    features = r.json().get("features", [])
    if not features:
        raise SystemExit("No Pony vehicles found.")

    gdf = gpd.GeoDataFrame.from_features(features, crs=CRS_WGS84)
    gdf = gdf[gdf.geometry.geom_type == "Point"].copy()
    if gdf.empty:
        raise SystemExit("No valid Pony vehicles.")

    # Filter available scooters (not disabled, not reserved, with decent fuel)
    available = gdf[
        (gdf.get("is_disabled", True) == False) &
        (gdf.get("is_reserved", True) == False) &
        (gdf.get("current_fuel_percent", 0).astype(float) >= 20)
    ].copy()

    if available.empty:
        print(f"⚠️  No available Pony scooters with ≥20% fuel (found {len(gdf)} total vehicles).")
        available = gdf.copy()

    # Color by fuel percentage
    fuel_vals = available["current_fuel_percent"].dropna()
    if not fuel_vals.empty:
        vmin, vmax = float(fuel_vals.min()), float(fuel_vals.max())
        cmap = linear.RdYlGn_09.scale(vmin, vmax)
    else:
        vmin, vmax = 0.0, 100.0
        cmap = linear.RdYlGn_09.scale(vmin, vmax)

    # Create map
    center = available.geometry.iloc[0]
    m = folium.Map([center.y, center.x], zoom_start=13)
    m.get_root().html.add_child(folium.Element(
        "<style>html,body{height:100%;margin:0}.folium-map{height:100vh;width:100%}</style>"
    ))

    # Plot each scooter
    for _, row in available.iterrows():
        g = row.geometry
        fuel = row.get("current_fuel_percent")
        range_m = row.get("current_range_meters")
        bike_id = row.get("bike_id", "n/a")
        
        color = "#888888" if fuel is None else cmap(float(fuel))
        
        label = f"ID: {bike_id}"
        if fuel is not None:
            label += f" | Fuel: {float(fuel):.0f}%"
        if range_m is not None:
            label += f" | Range: {float(range_m)/1000:.1f} km"
        
        folium.CircleMarker([g.y, g.x], radius=5, color=color, fill=True,
                            fill_opacity=0.9, popup=label).add_to(m)

    # Add color legend
    if vmax > vmin:
        cmap.caption = "Fuel Level (%)"
        cmap.add_to(m)

    # Fit bounds
    lats = [g.y for g in available.geometry]
    lons = [g.x for g in available.geometry]
    m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])

    m.save("pony_scooters_fuel.html")
    print(f"✅ Saved pony_scooters_fuel.html | Available scooters: {len(available)}")

if __name__ == "__main__":
    main()
