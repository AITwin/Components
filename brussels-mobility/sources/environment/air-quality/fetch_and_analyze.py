import requests, geopandas as gpd, folium
from branca.colormap import linear

# --- CONFIG ---
URL   = "https://api.mobilitytwin.brussels/environment/air-quality"
TOKEN = "7eba4bf32fcb9502a0ff273fb3191db5b0bbde7cc7f75dc40304dcf2a91c07ed67a55cbbd4e26bf2675e01c5a19d4e7abf92849a5a9fe36d30b558d567dd10cc"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

CRS_WGS84  = "EPSG:4326"
CRS_METRIC = 3812

def main():
    # Fetch air quality data
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    features = r.json().get("features", [])
    if not features:
        raise SystemExit("No air quality data found.")

    gdf = gpd.GeoDataFrame.from_features(features, crs=CRS_WGS84)
    gdf = gdf[gdf.geometry.geom_type == "Point"].copy()
    if gdf.empty:
        raise SystemExit("No valid air quality stations.")

    # Extract phenomenon (pollutant type)
    gdf["pollutant"] = gdf.get("parameters.phenomenon.label", "Unknown")
    gdf["station"] = gdf.get("station.properties.label", "Station")
    gdf["last_value"] = gdf.get("lastValue.value").apply(lambda x: float(x) if x is not None else None)
    gdf["uom"] = gdf.get("uom", "")

    # Focus on NO2 (nitrogen dioxide) measurements
    no2 = gdf[gdf["pollutant"].str.contains("NO2|nitrogen dioxide", case=False, na=False)].copy()
    
    if no2.empty:
        print("⚠️  No NO2 measurements found, showing all available pollutants.")
        no2 = gdf.copy()

    # Filter stations with valid measurements
    with_data = no2[no2["last_value"].notna()].copy()
    if with_data.empty:
        raise SystemExit("No stations with valid measurements.")

    # Color by concentration level
    vmin, vmax = float(with_data["last_value"].min()), float(with_data["last_value"].max())
    cmap = linear.YlOrRd_09.scale(vmin, vmax)

    # Create map
    center = with_data.geometry.iloc[0]
    m = folium.Map([center.y, center.x], zoom_start=12)
    m.get_root().html.add_child(folium.Element(
        "<style>html,body{height:100%;margin:0}.folium-map{height:100vh;width:100%}</style>"
    ))

    # Plot each station
    for _, row in with_data.iterrows():
        g = row.geometry
        value = row["last_value"]
        station = row["station"]
        pollutant = row["pollutant"]
        unit = row["uom"]
        
        color = cmap(value)
        label = f"{station} — {pollutant}"
        popup = f"<b>{station}</b><br>{pollutant}<br>Value: {value:.2f} {unit}"
        
        folium.CircleMarker([g.y, g.x], radius=7, color=color, fill=True,
                            fill_opacity=0.8, tooltip=label, popup=popup).add_to(m)

    # Add legend
    cmap.caption = f"{with_data['pollutant'].iloc[0]} ({with_data['uom'].iloc[0]})"
    cmap.add_to(m)

    # Fit bounds
    lats = [g.y for g in with_data.geometry]
    lons = [g.x for g in with_data.geometry]
    m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])

    m.save("air_quality_map.html")
    print(f"✅ Saved air_quality_map.html | Stations: {len(with_data)}")

if __name__ == "__main__":
    main()
