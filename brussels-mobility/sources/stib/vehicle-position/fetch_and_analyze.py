# Nearest STIB vehicle to each main hub (Central, Midi, North) right now
import requests, geopandas as gpd, folium, re, pandas as pd
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

TOKEN = "YOUR_BEARER_TOKEN_HERE"
HDRS  = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

STOPS_URL = "https://api.mobilitytwin.brussels/stib/stops"
VEH_URL   = "https://api.mobilitytwin.brussels/stib/vehicle-position"
CRS_M     = 3857  # Web Mercator for meter distances

HUB_PATTERNS = {
    "Brussels-Central": re.compile(r"(bruxelles-?central|brussel-?centraal|brussels-?central|gare centrale)", re.I),
    "Brussels-Midi":    re.compile(r"(gare du midi|brussel[- ]?zuid|brussels[- ]?south|midi)", re.I),
    "Brussels-North":   re.compile(r"(bruxelles[- ]?nord|brussel[- ]?noord|brussels[- ]?north|nord|noord)", re.I),
}

def get(row, *keys, default="—"):
    for k in keys:
        if k in row and pd.notna(row[k]):
            return str(row[k])
    return default

def fmt_time(ts):
    try:
        t = float(ts)
        if t > 1e12: t /= 1000.0
        dt = datetime.fromtimestamp(t, tz=timezone.utc).astimezone(ZoneInfo("Europe/Brussels"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "—"

def main():
    # 1) Hubs from /stib/stops (mean centroid of all platform variants)
    s = requests.get(STOPS_URL, headers=HDRS, timeout=30); s.raise_for_status()
    stops = gpd.GeoDataFrame.from_features(s.json()["features"], crs="EPSG:4326")
    stops = stops[stops.geometry.geom_type == "Point"]

    hubs = []
    for name, pat in HUB_PATTERNS.items():
        subset = stops[stops["stop_name"].fillna("").str.contains(pat)]
        if subset.empty:
            continue
        pt = subset.unary_union.centroid
        hubs.append({"name": name, "geometry": pt})
    hubs_gdf = gpd.GeoDataFrame(hubs, crs="EPSG:4326")
    if hubs_gdf.empty:
        print("❌ No hubs matched. Check HUB_PATTERNS."); return

    # 2) Vehicles now
    v = requests.get(VEH_URL, headers=HDRS, timeout=30); v.raise_for_status()
    vfeats = v.json().get("features", [])
    if not vfeats:
        print("No vehicles in feed."); return
    veh = gpd.GeoDataFrame.from_features(vfeats, crs="EPSG:4326")
    veh = veh[veh.geometry.geom_type == "Point"]
    if veh.empty:
        print("No point geometries in vehicle feed."); return

    # 3) Compute nearest vehicle to each hub (in meters)
    hubs_m = hubs_gdf.to_crs(CRS_M)
    veh_m  = veh.to_crs(CRS_M)

    picks = []
    for i, h in hubs_m.iterrows():
        dists = veh_m.geometry.distance(h.geometry)
        j = dists.idxmin()
        picks.append({
            "hub": hubs_gdf.loc[i, "name"],
            "hub_geom": hubs_gdf.loc[i, "geometry"],
            "veh_idx": j,
            "veh_geom": veh.loc[j, "geometry"],
            "dist_m": float(dists.loc[j]),
        })

    # 4) Map (fullscreen)
    center = hubs_gdf.unary_union.centroid
    m = folium.Map([center.y, center.x], 12)
    m.get_root().html.add_child(folium.Element(
        "<style>html,body{height:100%;margin:0}.leaflet-container{width:100vw!important;height:100vh!important;}</style>"
    ))

    # plot all vehicles (grey dots with minimal tooltip)
    for _, r in veh.iterrows():
        tip_line = get(r, "route_short_name", "line")
        folium.CircleMarker([r.geometry.y, r.geometry.x], radius=3, color="#888",
                            fill=True, fill_opacity=0.85,
                            tooltip=f"Line: {tip_line or '—'}").add_to(m)

    # hubs (squares), nearest vehicles (red triangles), and lines
    for p in picks:
        hy, hx = p["hub_geom"].y, p["hub_geom"].x
        vy, vx = p["veh_geom"].y, p["veh_geom"].x
        r = veh.loc[p["veh_idx"]]  # vehicle row

        # --- HUB popup (square): only hub + distance ---
        folium.RegularPolygonMarker(
            [hy, hx],
            number_of_sides=4, radius=9, rotation=0,
            color="#1f77b4", fill=True, fill_opacity=0.95,
            tooltip=p["hub"],
            popup=folium.Popup(
                folium.IFrame(html=f"""
                    <div style="font:14px/1.35 -apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Arial">
                      <b>{p['hub']}</b><br/>
                      Nearest vehicle is <b>{int(p['dist_m'])} m</b> away.
                      <div style="color:#666">Click the red triangle for vehicle details.</div>
                    </div>
                """, width=260, height=90),
                max_width=300
            )
        ).add_to(m)

        # --- VEHICLE popup (triangle): vehicle-specific info only ---
        veh_id   = get(r, "vehicle_id", "id", "bike_id", "name")
        veh_type = get(r, "vehicle_type", "vehicle_type_id", "type")
        line     = get(r, "route_short_name", "line")
        direction= get(r, "direction_id", "direction")
        speed    = get(r, "speed")
        lastrep  = get(r, "last_reported")
        lastrep_fmt = fmt_time(lastrep) if lastrep != "—" else "—"

        rows = [
            ("Vehicle", veh_id),
            ("Type", veh_type),
            ("Line", line),
            ("Direction", direction),
            ("Distance to hub", f"{int(p['dist_m'])} m"),
            ("Last reported", lastrep_fmt),
        ]
        # include speed if numeric
        try:
            if speed != "—":
                s_val = float(speed)
                rows.insert(4, ("Speed", f"{s_val:.1f}"))
        except Exception:
            pass

        tbl = "".join(
            f"<tr><td style='padding:2px 8px;color:#666'>{k}</td>"
            f"<td style='padding:2px 0'><b>{v}</b></td></tr>"
            for k, v in rows
        )

        folium.RegularPolygonMarker(
            [vy, vx],
            number_of_sides=3, radius=10,
            color="#d62728", fill=True, fill_opacity=0.95,
            tooltip=f"Vehicle {veh_id or '—'} • {int(p['dist_m'])} m",
            popup=folium.Popup(
                folium.IFrame(html=f"""
                    <div style="font:14px/1.35 -apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Arial">
                      <div style="margin-bottom:4px"><b>Nearest vehicle details</b></div>
                      <table style="border-collapse:collapse">{tbl}</table>
                    </div>
                """, width=300, height=170),
                max_width=320
            )
        ).add_to(m)

        folium.PolyLine(
            [[hy, hx], [vy, vx]], color="#d62728", weight=3, opacity=0.85,
            tooltip=f"{p['hub']} ⇄ vehicle: {int(p['dist_m'])} m"
        ).add_to(m)

    m.save("stib_nearest_vehicle_to_hubs.html")
    print("✅ Saved stib_nearest_vehicle_to_hubs.html")
    for p in picks:
        print(f"{p['hub']}: ~{int(p['dist_m'])} m")

if __name__ == "__main__":
    main()