import requests, pandas as pd
from datetime import datetime, timedelta

# --- CONFIG ---
URL   = "https://api.mobilitytwin.brussels/stib/trips"
TOKEN = "7eba4bf32fcb9502a0ff273fb3191db5b0bbde7cc7f75dc40304dcf2a91c07ed67a55cbbd4e26bf2675e01c5a19d4e7abf92849a5a9fe36d30b558d567dd10cc"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

def main():
    # Fetch trips for last hour
    end = int(datetime.now().timestamp())
    start = int((datetime.now() - timedelta(hours=1)).timestamp())
    
    r = requests.get(URL, headers=HEADERS, params={"start_timestamp": start, "end_timestamp": end}, timeout=60)
    r.raise_for_status()
    data = r.json()
    
    # Parse MF-JSON trajectories
    if isinstance(data, str):
        print(f"⚠️  API returned string data")
        raise SystemExit("Check API response format")
    
    if not data or "features" not in data:
        raise SystemExit("No trip data found.")
    
    features = data["features"]
    
    # Analyze trip statistics
    trip_stats = []
    for feature in features:
        props = feature.get("properties", {})
        coords = feature.get("geometry", {}).get("coordinates", [])
        
        uuid = props.get("uuid", "Unknown")
        line_id = props.get("lineId", "")
        
        # Calculate trajectory points
        total_points = len(coords)
        
        trip_stats.append({
            "uuid": uuid,
            "lineId": line_id,
            "points": total_points
        })
    
    df = pd.DataFrame(trip_stats)
    
    # Analyze by line
    line_summary = df.groupby("lineId").agg({"uuid": "count", "points": "mean"}).round(1)
    line_summary.columns = ["trips", "avg_points"]
    line_summary = line_summary.sort_values("trips", ascending=False)
    
    print(f"\n{'='*70}")
    print(f"{'STIB Trip Analysis — Last Hour'}")
    print(f"{'='*70}\n")
    
    print(f"{'Line':<10} | {'Trips':>8} | {'Avg Data Points':>15}")
    print(f"{'-'*70}")
    for line_id, row in line_summary.head(20).iterrows():
        print(f"{line_id:<10} | {int(row['trips']):>8} | {row['avg_points']:>15.1f}")
    
    print(f"\n{'='*70}")
    print(f"Total trips: {len(df)} | Lines: {len(line_summary)}")
    print(f"{'='*70}\n")
    
    # Save to CSV
    df.to_csv("stib_trips.csv", index=False)
    print(f"✅ Saved stib_trips.csv")
    
    # Create visualization
    import plotly.express as px
    fig = px.bar(
        line_summary.head(30).reset_index(),
        x='lineId',
        y='trips',
        title='STIB/MIVB Top 30 Lines by Trip Count (Last Hour)',
        labels={'lineId': 'Line', 'trips': 'Number of Trips'},
        color='trips',
        color_continuous_scale='Blues',
        hover_data=['avg_points']
    )
    fig.write_html("stib_trips_chart.html")
    print(f"✅ Saved stib_trips_chart.html")

if __name__ == "__main__":
    main()
