import requests, geopandas as gpd, folium
import sys
from branca.colormap import linear

# --- CONFIG ---
URL   = "https://api.mobilitytwin.brussels/traffic/telraam"
TOKEN = "7eba4bf32fcb9502a0ff273fb3191db5b0bbde7cc7f75dc40304dcf2a91c07ed67a55cbbd4e26bf2675e01c5a19d4e7abf92849a5a9fe36d30b558d567dd10cc"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

CRS_WGS84  = "EPSG:4326"
CRS_METRIC = 3812

def to_float(val):
    """Convert value to float, handle string 'None' or actual None."""
    if val is None or val == "None" or val == "":
        return None
    try:
        return float(val)
    except:
        return None

def main():
    # Fetch Telraam traffic data
    try:
        r = requests.get(URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 500:
            print("⚠️  API temporarily unavailable (500 error)")
            sys.exit(0)
        raise
    except (requests.exceptions.ChunkedEncodingError, 
            requests.exceptions.ConnectionError) as e:
        print("⚠️  Network connection issue, API may be unstable")
        sys.exit(0)  # Exit successfully since this is a network issue
    
    features = r.json().get("features", [])
    if not features:
        raise SystemExit("No Telraam data found.")

    gdf = gpd.GeoDataFrame.from_features(features, crs=CRS_WGS84)
    gdf = gdf[gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
    if gdf.empty:
        raise SystemExit("No valid Telraam segments.")

    # Parse traffic counts
    for col in ["car", "bike", "pedestrian", "heavy"]:
        gdf[col] = gdf.get(col, None).apply(to_float)

    # Calculate total traffic
    gdf["total"] = gdf[["car", "bike", "pedestrian", "heavy"]].sum(axis=1, skipna=True)

    # Filter segments with data
    with_data = gdf[gdf["total"] > 0].copy()
    if with_data.empty:
        raise SystemExit("No segments with traffic data.")

    # Color by total traffic volume
    vmin, vmax = float(with_data["total"].min()), float(with_data["total"].max())
    cmap = linear.YlOrRd_09.scale(vmin, vmax)

    # Create map
    center_pt = with_data.geometry.iloc[0].centroid
    m = folium.Map([center_pt.y, center_pt.x], zoom_start=12)
    m.get_root().html.add_child(folium.Element(
        "<style>html,body{height:100%;margin:0}.folium-map{height:100vh;width:100%}</style>"
    ))

    # Draw each segment
    for _, row in with_data.iterrows():
        total = row["total"]
        car = row.get("car", 0) or 0
        bike = row.get("bike", 0) or 0
        ped = row.get("pedestrian", 0) or 0
        heavy = row.get("heavy", 0) or 0
        
        color = cmap(total)
        label = f"Total: {int(total)} | Car: {int(car)} | Bike: {int(bike)} | Pedestrian: {int(ped)} | Heavy: {int(heavy)}"
        
        folium.GeoJson(
            row.geometry.__geo_interface__,
            style_function=lambda f, c=color: {"color": c, "weight": 4, "opacity": 0.7},
            tooltip=label
        ).add_to(m)

    # Add legend
    cmap.caption = "Total Traffic Count"
    cmap.add_to(m)

    m.save("telraam_traffic.html")
    print(f"✅ Saved telraam_traffic.html | Segments: {len(with_data)}")

if __name__ == "__main__":
    main()
