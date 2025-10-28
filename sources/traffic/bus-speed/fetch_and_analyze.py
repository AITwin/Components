import requests, pandas as pd

# --- CONFIG ---
URL   = "https://api.mobilitytwin.brussels/traffic/bus-speed"
TOKEN = "7eba4bf32fcb9502a0ff273fb3191db5b0bbde7cc7f75dc40304dcf2a91c07ed67a55cbbd4e26bf2675e01c5a19d4e7abf92849a5a9fe36d30b558d567dd10cc"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

def main():
    # Fetch bus speeds (same as STIB speed endpoint)
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    
    if not data:
        raise SystemExit("No bus speed data found.")

    df = pd.DataFrame(data)
    df["speed"] = pd.to_numeric(df["speed"], errors="coerce")
    
    # Analyze by line
    line_stats = df.groupby("lineId")["speed"].agg(["mean", "min", "max", "count"]).round(2)
    line_stats.columns = ["avg_speed", "min_speed", "max_speed", "readings"]
    line_stats = line_stats.sort_values("avg_speed", ascending=False)
    
    print(f"\n{'='*90}")
    print(f"{'Bus Speed Analysis (20-sec intervals) — Fastest Lines'}")
    print(f"{'='*90}\n")
    
    print(f"{'Line':<8} | {'Readings':>8} | {'Avg Speed (km/h)':>16} | {'Min':>8} | {'Max':>8}")
    print(f"{'-'*90}")
    
    for line_id, row in line_stats.head(20).iterrows():
        print(f"{line_id:<8} | {int(row['readings']):>8} | {row['avg_speed']:>16.2f} | {row['min_speed']:>8.2f} | {row['max_speed']:>8.2f}")
    
    print(f"\n{'='*90}")
    print(f"Total speed readings: {len(df)} | Lines monitored: {len(line_stats)}")
    print(f"Overall avg speed: {df['speed'].mean():.2f} km/h")
    print(f"{'='*90}\n")
    
    # Save to CSV
    df.to_csv("bus_speed.csv", index=False)
    print(f"✅ Saved bus_speed.csv")
    
    # Create visualizations
    import plotly.express as px
    
    fig = px.bar(
        line_stats.head(30).reset_index(),
        x='lineId',
        y='avg_speed',
        title='Brussels Bus Speed — Top 30 Fastest Lines (20-sec intervals)',
        labels={'lineId': 'Line', 'avg_speed': 'Average Speed (km/h)'},
        color='avg_speed',
        color_continuous_scale='RdYlGn',
        hover_data=['min_speed', 'max_speed', 'readings']
    )
    fig.write_html("bus_speed_chart.html")
    print(f"✅ Saved bus_speed_chart.html")

if __name__ == "__main__":
    main()
