import requests, json, geopandas as gpd, folium
from branca.colormap import linear

GEOFENCE_URL = "https://api.mobilitytwin.brussels/dott/geofences"
VEHICLE_URL  = "https://api.mobilitytwin.brussels/dott/vehicle-position"
TOKEN        = "YOUR_BEARER_TOKEN_HERE"   # <- put your token here
HEADERS      = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}
MAX_NO_RIDE_AREA_KM2 = 5.0  # drop giant service polygon

def normalize_rules(val):
    if isinstance(val, list): return val
    if isinstance(val, str):
        try: return json.loads(val)
        except: return []
    return []

def main():
    # fetch → GeoDataFrames (WGS84)
    zones_js = requests.get(GEOFENCE_URL, headers=HEADERS, timeout=30).json()
    veh_js   = requests.get(VEHICLE_URL,  headers=HEADERS, timeout=30).json()
    zones = gpd.GeoDataFrame.from_features(zones_js.get("features", []), crs="EPSG:4326")
    vehicles = gpd.GeoDataFrame.from_features(veh_js.get("features", []),  crs="EPSG:4326")

    zones = zones[zones.geometry.geom_type.isin(["Polygon","MultiPolygon"])].copy()
    vehicles = vehicles[vehicles.geometry.geom_type.eq("Point")].copy()
    if zones.empty or vehicles.empty:
        raise SystemExit("No zones or vehicles found.")

    # keep only no-ride zones (ride_allowed == False)
    zones["rules"] = zones["rules"].apply(normalize_rules)
    noride = zones[zones["rules"].apply(lambda rs: any(r.get("ride_allowed") is False for r in rs))].copy()
    if noride.empty:
        raise SystemExit("No no-ride zones detected.")

    # drop huge polygons (> 5 km²)
    noride_m = noride.to_crs(3812)
    noride_m["area_km2"] = noride_m.geometry.area / 1_000_000
    noride_m = noride_m[noride_m["area_km2"] <= MAX_NO_RIDE_AREA_KM2]
    if noride_m.empty:
        raise SystemExit("All candidate no-ride polygons were huge; nothing to show.")

    vehicles_m = vehicles.to_crs(3812)

    # vehicles inside no-ride zones
    inside_m = gpd.sjoin(vehicles_m, noride_m[["geometry"]], predicate="within", how="inner")
    if inside_m.empty:
        raise SystemExit("No vehicles inside no-ride zones right now.")

    # back to WGS84 for mapping
    inside = inside_m.to_crs(4326)
    noride = noride_m.to_crs(4326)

    # color scale by current_range_meters
    rng = inside["current_range_meters"].dropna()
    vmin, vmax = (float(rng.min()), float(rng.max())) if not rng.empty else (0.0, 1.0)
    cmap = linear.YlOrRd_09.scale(vmin, vmax)

    # map (full-page CSS)
    c = noride.geometry.iloc[0].centroid
    m = folium.Map([c.y, c.x], zoom_start=13)
    m.get_root().html.add_child(folium.Element(
        "<style>html,body{height:100%;margin:0}.folium-map{height:100vh;width:100%}</style>"
    ))

    # shade no-ride zones (translucent red)
    for geom in noride.geometry:
        folium.GeoJson(
            geom.__geo_interface__,
            style_function=lambda _:{ "color":"#d62728","weight":2,"fill":True,"fillOpacity":0.25 }
        ).add_to(m)

    # plot vehicles inside zones, colored by range
    for _, row in inside.iterrows():
        g = row.geometry
        r_m = row.get("current_range_meters")
        color = "#888888" if r_m is None else cmap(float(r_m))
        label = f"bike_id: {row.get('bike_id','n/a')}"
        if r_m is not None:
            label += f" | range: {float(r_m)/1000:.1f} km"
        folium.CircleMarker([g.y, g.x], radius=4, color=color, fill=True,
                            fill_opacity=0.9, popup=label).add_to(m)

    if vmax > vmin:
        cmap.caption = "Current range (meters)"
        cmap.add_to(m)

    m.save("dott_noride_with_battery.html")
    print(f" Saved dott_noride_with_battery.html | Zones: {len(noride)} | Vehicles inside: {len(inside)}")

if __name__ == "__main__":
    main()