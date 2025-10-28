import requests, pandas as pd

# --- CONFIG ---
URL   = "https://api.mobilitytwin.brussels/traffic/tunnels"
TOKEN = "7eba4bf32fcb9502a0ff273fb3191db5b0bbde7cc7f75dc40304dcf2a91c07ed67a55cbbd4e26bf2675e01c5a19d4e7abf92849a5a9fe36d30b558d567dd10cc"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

def main():
    # Fetch tunnel traffic data
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    j = r.json()
    
    data_dict = j.get("data", {})
    if not data_dict:
        raise SystemExit("No tunnel data found.")

    # Collect 15-minute metrics for all detectors
    records = []
    for device_id, device_data in data_dict.items():
        results = device_data.get("results", {})
        interval_15m = results.get("15m", {})
        
        for track_name in ["t1", "t2"]:
            track_data = interval_15m.get(track_name, {})
            if track_data:
                occupancy = track_data.get("occupancy")
                records.append({
                    "device_id": device_id,
                    "track": track_name,
                    "count": track_data.get("count", 0),
                    "speed_kmh": track_data.get("speed", 0),
                    "occupancy_pct": (occupancy * 100) if occupancy is not None else 0,
                    "start_time": track_data.get("start_time", ""),
                    "end_time": track_data.get("end_time", "")
                })

    if not records:
        raise SystemExit("No 15-minute interval data available.")

    df = pd.DataFrame(records)

    # Find busiest tunnel sections
    df_sorted = df.sort_values("count", ascending=False).head(10)

    # Print summary
    print(f"\n{'='*70}")
    print(f"{'Brussels Tunnel Traffic — Top 10 Busiest Detectors (15-min)'}")
    print(f"{'='*70}\n")
    
    for idx, row in df_sorted.iterrows():
        print(f"Device: {row['device_id']:15s} | Track: {row['track']}")
        print(f"  Count:      {row['count']:5.0f} vehicles")
        print(f"  Speed:      {row['speed_kmh']:5.1f} km/h")
        print(f"  Occupancy:  {row['occupancy_pct']:5.1f}%")
        print(f"  Period:     {row['start_time']} → {row['end_time']}")
        print()

    print(f"{'='*70}")
    print(f"Total detectors with data: {len(df)}")
    print(f"{'='*70}\n")

    # Optionally save to CSV
    df.to_csv("tunnel_traffic_15min.csv", index=False)
    print(f"✅ Saved tunnel_traffic_15min.csv | Records: {len(df)}")

if __name__ == "__main__":
    main()
