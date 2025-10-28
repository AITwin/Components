import requests, pandas as pd

# --- CONFIG ---
URL   = "https://api.mobilitytwin.brussels/stib/speed"
TOKEN = "7eba4bf32fcb9502a0ff273fb3191db5b0bbde7cc7f75dc40304dcf2a91c07ed67a55cbbd4e26bf2675e01c5a19d4e7abf92849a5a9fe36d30b558d567dd10cc"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

CRS_WGS84  = "EPSG:4326"
CRS_METRIC = 3812

def main():
    # Fetch STIB speed data
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    
    if not data:
        raise SystemExit("No STIB speed data found.")

    df = pd.DataFrame(data)

    # Filter out zero or null speeds
    df = df[df["speed"] > 0].copy()
    if df.empty:
        raise SystemExit("No valid speed measurements.")

    # Group by line and calculate average speed
    line_speeds = df.groupby("lineId").agg({
        "speed": ["mean", "min", "max", "count"]
    }).reset_index()
    line_speeds.columns = ["line", "avg_speed", "min_speed", "max_speed", "count"]
    line_speeds = line_speeds.sort_values("avg_speed", ascending=False)

    # Print summary
    print(f"\n{'='*80}")
    print(f"{'STIB/MIVB Line Speeds (20-second interval average)'}")
    print(f"{'='*80}\n")
    
    print(f"{'Line':<6} | {'Avg Speed':>10} | {'Min':>8} | {'Max':>8} | {'Measurements':>12}")
    print(f"{'-'*80}")
    
    for _, row in line_speeds.iterrows():
        print(f"{row['line']:<6} | {row['avg_speed']:>9.2f} | {row['min_speed']:>8.2f} | "
              f"{row['max_speed']:>8.2f} | {int(row['count']):>12}")

    print(f"\n{'='*80}")
    print(f"Total lines: {len(line_speeds)}")
    print(f"Overall avg speed: {df['speed'].mean():.2f} km/h")
    print(f"Fastest line: {line_speeds.iloc[0]['line']} ({line_speeds.iloc[0]['avg_speed']:.2f} km/h)")
    print(f"Slowest line: {line_speeds.iloc[-1]['line']} ({line_speeds.iloc[-1]['avg_speed']:.2f} km/h)")
    print(f"{'='*80}\n")

    # Save to CSV
    line_speeds.to_csv("stib_line_speeds.csv", index=False)
    print(f"✅ Saved stib_line_speeds.csv | Lines: {len(line_speeds)}")
    
    # Create interactive chart
    import plotly.express as px
    fig = px.bar(
        line_speeds.head(30),
        x='line',
        y='avg_speed',
        title='STIB/MIVB Top 30 Line Speeds (20-second intervals)',
        labels={'line': 'Line', 'avg_speed': 'Average Speed (km/h)'},
        color='avg_speed',
        color_continuous_scale='RdYlGn',
        hover_data=['min_speed', 'max_speed', 'count']
    )
    fig.write_html("stib_speed_chart.html")
    print(f"✅ Saved stib_speed_chart.html")

if __name__ == "__main__":
    main()
