import requests, geopandas as gpd, folium, json

# --- CONFIG ---
URL   = "https://api.mobilitytwin.brussels/bolt/geofences"
TOKEN = "YOUR_BEARER_TOKEN_HERE"   # replace with your real token

def normalize_rules(val):
    if isinstance(val, list): return val
    if isinstance(val, str):
        try: return json.loads(val)
        except: return []
    return []

def main():
    # fetch
    r = requests.get(URL, headers={"Authorization": f"Bearer {TOKEN}"}, timeout=30)
    r.raise_for_status()
    features = r.json().get("features", []) or []
    if not features:
        raise SystemExit("No geofences found")

    # to GeoDataFrame
    gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
    gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()

    # keep zones with 0 < maximum_speed_kph <= 10
    gdf["rules"] = gdf.get("rules", []).apply(normalize_rules)
    slow = gdf[gdf["rules"].apply(lambda rs: any(
        (r.get("maximum_speed_kph") is not None)
        and (0 < float(r["maximum_speed_kph"]) <= 10)
        for r in rs
    ))]

    if slow.empty:
        raise SystemExit("No zones with max speed ≤ 10 kph and > 0.")

    # map (shade slow zones translucent blue)
    center = slow.geometry.iloc[0].centroid
    m = folium.Map(location=[center.y, center.x], zoom_start=13)
    for _, row in slow.iterrows():
        name = row.get("name") or "Slow zone"
        limits = [float(r["maximum_speed_kph"]) for r in row["rules"]
                  if r.get("maximum_speed_kph") is not None and r["maximum_speed_kph"] > 0]
        label = f"{name} — max {min(limits):.0f} kph" if limits else name

        folium.GeoJson(
            row.geometry.__geo_interface__,
            style_function=lambda f: {"color":"#1f77b4","weight":2,"fill":True,"fillOpacity":0.25},
            tooltip=label
        ).add_to(m)

    m.save("bolt_speed_10kph.html")
    print(f"✅ Saved bolt_speed_10kph.html | Zones: {len(slow)}")

if __name__ == "__main__":
    main()