import requests, pandas as pd

# --- CONFIG ---
URL   = "https://api.mobilitytwin.brussels/stib/vehicle-distance"
TOKEN = "YOUR_BEARER_TOKEN_HERE"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

def main():
    # Fetch vehicle distances
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    
    if not data:
        raise SystemExit("No vehicle distance data found.")

    df = pd.DataFrame(data)
    
    # Analyze distances by line
    df["distanceFromPoint"] = pd.to_numeric(df["distanceFromPoint"], errors="coerce")
    
    line_stats = df.groupby("lineId").agg({
        "distanceFromPoint": ["mean", "min", "max", "count"]
    }).round(1)
    
    line_stats.columns = ["avg_distance", "min_distance", "max_distance", "vehicles"]
    line_stats = line_stats.sort_values("vehicles", ascending=False)
    
    print(f"\n{'='*90}")
    print(f"{'STIB Vehicle Distance Analysis — Distance from Last Stop'}")
    print(f"{'='*90}\n")
    
    print(f"{'Line':<8} | {'Vehicles':>8} | {'Avg Dist (m)':>12} | {'Min (m)':>8} | {'Max (m)':>8}")
    print(f"{'-'*90}")
    
    for line_id, row in line_stats.head(20).iterrows():
        print(f"{line_id:<8} | {int(row['vehicles']):>8} | {row['avg_distance']:>12.1f} | {row['min_distance']:>8.1f} | {row['max_distance']:>8.1f}")
    
    print(f"\n{'='*90}")
    print(f"Total vehicles tracked: {len(df)} | Lines: {len(line_stats)}")
    print(f"{'='*90}\n")
    
    # Save to CSV
    df.to_csv("stib_vehicle_distance.csv", index=False)
    print(f"✅ Saved stib_vehicle_distance.csv")
    
    # Create visualizations
    import plotly.express as px
    
    # Histogram of all distances
    fig1 = px.histogram(
        df,
        x='distanceFromPoint',
        nbins=50,
        title='STIB/MIVB Vehicle Distance from Last Stop Distribution',
        labels={'distanceFromPoint': 'Distance (meters)', 'count': 'Number of Vehicles'},
        color_discrete_sequence=['#1f77b4']
    )
    fig1.write_html("stib_distance_histogram.html")
    
    # Bar chart by line
    fig2 = px.bar(
        line_stats.head(30).reset_index(),
        x='lineId',
        y='avg_distance',
        title='STIB/MIVB Top 30 Lines by Average Distance from Last Stop',
        labels={'lineId': 'Line', 'avg_distance': 'Avg Distance (m)'},
        color='avg_distance',
        color_continuous_scale='RdYlGn_r',
        hover_data=['vehicles', 'min_distance', 'max_distance']
    )
    fig2.write_html("stib_distance_by_line.html")
    
    print(f"✅ Saved stib_distance_histogram.html and stib_distance_by_line.html")

if __name__ == "__main__":
    main()
