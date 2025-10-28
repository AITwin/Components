# pip install requests pandas shapely
import time, requests, pandas as pd, json, os
from math import radians, sin, cos, asin, sqrt
from shapely.geometry import Point, Polygon
from datetime import datetime, timezone
from pathlib import Path

TOKEN = "YOUR_BEARER_TOKEN_HERE"
URL   = "https://api.mobilitytwin.brussels/sncb/vehicle-position"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

# Local cache for snapshots
CACHE_FILE = Path(__file__).parent / "snapshot_cache.json"

# --- Replace with your real regions (lon,lat rings) ---
ECO_POLY_RING    = [[4.33,50.83],[4.43,50.83],[4.43,50.89],[4.33,50.89],[4.33,50.83]]
NORMAL_POLY_RING = [[4.20,50.85],[4.30,50.85],[4.30,50.91],[4.20,50.91],[4.20,50.85]]

MIN_TIME_GAP = 120  # minimum 2 minutes between snapshots for speed calc

def _parse_header_ts(hdr_val: str) -> int:
    try:
        return int(datetime.fromisoformat(hdr_val.replace("Z","+00:00")).timestamp())
    except Exception:
        return 0

def fetch_positions():
    """Fetch current vehicle positions (API only supports latest snapshot)."""
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    feats = (r.json() or {}).get("features", [])
    rows = []
    for f in feats:
        g = f.get("geometry") or {}
        coords = g.get("coordinates") or []
        if len(coords) < 2: continue
        lon, lat = float(coords[0]), float(coords[1])
        trip_id = (f.get("properties") or {}).get("trip_id","")
        if trip_id:
            rows.append({"trip_id": trip_id, "lat": lat, "lon": lon})
    df = pd.DataFrame(rows)
    if not df.empty:
        df = (df.dropna(subset=["trip_id","lat","lon"])
                .drop_duplicates("trip_id", keep="last")
                .set_index("trip_id"))
    snap_epoch = _parse_header_ts(r.headers.get("X-Data-Timestamp","")) or int(time.time())
    return df, snap_epoch

def load_cached_snapshot():
    """Load the most recent cached snapshot from disk."""
    if not CACHE_FILE.exists():
        return None, 0
    try:
        with open(CACHE_FILE, 'r') as f:
            data = json.load(f)
        df = pd.DataFrame(data['vehicles'])
        if not df.empty:
            df = df.set_index('trip_id')
        return df, data['timestamp']
    except Exception as e:
        print(f"Warning: Could not load cache: {e}")
        return None, 0

def save_snapshot(df, timestamp):
    """Save current snapshot to disk for future comparisons."""
    data = {
        'timestamp': timestamp,
        'vehicles': df.reset_index().to_dict('records') if not df.empty else []
    }
    with open(CACHE_FILE, 'w') as f:
        json.dump(data, f)

def nearest_earlier_snapshot(anchor_epoch: int):
    """Load cached snapshot if it's old enough for speed calculation."""
    df_cached, t_cached = load_cached_snapshot()
    if df_cached is None or df_cached.empty:
        return pd.DataFrame(), 0
    
    time_gap = anchor_epoch - t_cached
    if time_gap < MIN_TIME_GAP:
        print(f"Cached snapshot is only {time_gap}s old (need >{MIN_TIME_GAP}s). Wait and run again later.")
        return pd.DataFrame(), 0
    
    return df_cached, t_cached

def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1); dl = radians(lon2 - lon1)
    a = sin(dphi/2)**2 + cos(phi1)*cos(phi2)*sin(dl/2)**2
    return 2*R*asin(sqrt(a))

def main():
    # Latest snapshot (t1)
    print("Fetching latest snapshot...")
    try:
        df1, t1 = fetch_positions()
        print(f"✓ Got {len(df1)} vehicles at {datetime.fromtimestamp(t1, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}")
    except Exception as e:
        print("Failed to fetch latest snapshot:", e); return
    if df1.empty:
        print("Latest snapshot returned no vehicles."); return

    # Try to load earlier snapshot from cache
    df0, t0 = nearest_earlier_snapshot(t1)
    
    # Save current snapshot for next run
    save_snapshot(df1, t1)
    print(f"✓ Saved current snapshot to {CACHE_FILE}")
    
    if df0.empty:
        print("\n⚠️  No earlier snapshot available for speed comparison.")
        print("ℹ️  Run this script again in a few minutes to calculate speeds.")
        print(f"\nCurrent snapshot summary:")
        print(f"  Timestamp: {datetime.fromtimestamp(t1, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}")
        print(f"  Vehicles: {len(df1)}")
        
        # Show region distribution without speeds
        eco_poly, normal_poly = Polygon(ECO_POLY_RING), Polygon(NORMAL_POLY_RING)
        def bucket(row):
            pt = Point(row["lon"], row["lat"])
            if eco_poly.contains(pt):    return "eco"
            if normal_poly.contains(pt): return "normal"
            return "other"
        
        df1["region"] = df1.apply(bucket, axis=1)
        print(f"\nVehicle distribution by region:")
        print(f"  Eco region:    {(df1['region'] == 'eco').sum()} vehicles")
        print(f"  Normal region: {(df1['region'] == 'normal').sum()} vehicles")
        print(f"  Other:         {(df1['region'] == 'other').sum()} vehicles")
        return

    common = df1.index.intersection(df0.index)
    if common.empty:
        print("No overlapping trips between snapshots; cannot compute speeds."); return

    merged = pd.concat([df0.loc[common].add_prefix("t0_"),
                        df1.loc[common].add_prefix("t1_")], axis=1)

    dt = max(1, t1 - t0)  # actual seconds between snapshots
    dist_m = merged.apply(lambda r: haversine_m(r.t0_lat, r.t0_lon, r.t1_lat, r.t1_lon), axis=1)
    merged["speed_kmh"] = (dist_m / dt) * 3.6
    merged["mid_lat"] = (merged["t0_lat"] + merged["t1_lat"]) / 2
    merged["mid_lon"] = (merged["t0_lon"] + merged["t1_lon"]) / 2

    eco_poly, normal_poly = Polygon(ECO_POLY_RING), Polygon(NORMAL_POLY_RING)
    def bucket(row):
        pt = Point(row["mid_lon"], row["mid_lat"])
        if eco_poly.contains(pt):    return "eco"
        if normal_poly.contains(pt): return "normal"
        return "other"

    merged["region"] = merged.apply(bucket, axis=1)
    eco = merged[merged["region"] == "eco"]["speed_kmh"]
    nor = merged[merged["region"] == "normal"]["speed_kmh"]

    def fmt(epoch): return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    print(f"Latest snapshot:  {fmt(t1)}  (vehicles: {len(df1)})")
    print(f"Earlier snapshot: {fmt(t0)}  (vehicles: {len(df0)})")
    print(f"Δt used: {dt}s (~{dt/60:.1f} min)\n")
    print("Eco region:    n=%d | avg_speed=%.1f km/h"   % (eco.size, eco.mean() if eco.size else float('nan')))
    print("Normal region: n=%d | avg_speed=%.1f km/h"   % (nor.size, nor.mean() if nor.size else float('nan')))

if __name__ == "__main__":
    main()