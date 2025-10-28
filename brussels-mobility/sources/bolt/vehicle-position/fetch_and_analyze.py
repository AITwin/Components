import requests, geopandas as gpd, folium

BOLT_URL = "https://api.mobilitytwin.brussels/bolt/vehicle-position"
STIB_URL = "https://api.mobilitytwin.brussels/stib/stops"
TOKEN    = "7eba4bf32fcb9502a0ff273fb3191db5b0bbde7cc7f75dc40304dcf2a91c07ed67a55cbbd4e26bf2675e01c5a19d4e7abf92849a5a9fe36d30b558d567dd10cc"

HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

def main():
    # fetch → GeoDataFrames (WGS84)
    bolt_js = requests.get(BOLT_URL, headers=HEADERS, timeout=30).json()
    stib_js = requests.get(STIB_URL, headers=HEADERS, timeout=30).json()

    bolt = gpd.GeoDataFrame.from_features(bolt_js.get("features", []), crs="EPSG:4326")
    stib = gpd.GeoDataFrame.from_features(stib_js.get("features", []), crs="EPSG:4326")

    bolt = bolt[bolt.geometry.geom_type == "Point"].copy()
    stib = stib[stib.geometry.geom_type == "Point"].copy()
    if bolt.empty or stib.empty:
        raise SystemExit("No Bolt vehicles or STIB stops.")

    # nearest stop within 50 m (metric CRS for meters)
    near = gpd.sjoin_nearest(
        bolt.to_crs(3812), stib.to_crs(3812),
        how="inner", max_distance=50, distance_col="dist_m"
    ).to_crs(4326)
    if near.empty:
        raise SystemExit("No Bolt vehicles within 50 m of a STIB stop.")

    # map (full page)
    pt = near.geometry.iloc[0]
    m = folium.Map([pt.y, pt.x], zoom_start=13)
    m.get_root().html.add_child(folium.Element(
        "<style>html,body{height:100%;margin:0} .folium-map{height:100vh;width:100%}</style>"
    ))

    # draw only matched stops once
    drawn_stops = set()
    for idx, row in near.iterrows():
        veh = row.geometry
        stop_idx = row["index_right"]          # index in the STIB GeoDataFrame
        stop = stib.loc[stop_idx].geometry     # WGS84 point
        stop_name = stib.loc[stop_idx].get("stop_name") or "STIB stop"
        bike_id = row.get("bike_id", "n/a")
        dist = row["dist_m"]

        # vehicle marker (purple) with popup mentioning the stop name + distance
        folium.CircleMarker([veh.y, veh.x], radius=4, color="#6a3d9a", fill=True,
                            fill_opacity=0.9,
                            popup=f"{bike_id} — ({dist:.0f} m)").add_to(m)

        # thin line from vehicle to that stop
        folium.PolyLine([[veh.y, veh.x], [stop.y, stop.x]], weight=1, opacity=0.7).add_to(m)

        # draw the matched stop (red) once
        if stop_idx not in drawn_stops:
            folium.CircleMarker([stop.y, stop.x], radius=3, color="red", fill=True,
                                fill_opacity=0.9, popup=stop_name).add_to(m)
            drawn_stops.add(stop_idx)

    # fit to all matched vehicles
    latlons = [(g.y, g.x) for g in near.geometry]
    m.fit_bounds([[min(lat for lat, _ in latlons), min(lon for _, lon in latlons)],
                  [max(lat for lat, _ in latlons), max(lon for _, lon in latlons)]])

    m.save("bolt_near_stib.html")
    print(f"✅ Saved bolt_near_stib.html | {len(near)} vehicles within 50 m")

if __name__ == "__main__":
    main()