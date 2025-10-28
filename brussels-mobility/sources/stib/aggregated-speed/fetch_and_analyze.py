import requests, pandas as pd, plotly.express as px

URL = "https://api.mobilitytwin.brussels/stib/aggregated-speed"
TOKEN = "7eba4bf32fcb9502a0ff273fb3191db5b0bbde7cc7f75dc40304dcf2a91c07ed67a55cbbd4e26bf2675e01c5a19d4e7abf92849a5a9fe36d30b558d567dd10cc"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

def main():
    """Fetch STIB aggregated speed data and create visualizations."""
    resp = requests.get(URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    
    data = resp.json() if resp.headers.get('content-type', '').startswith('application/json') else []
    
    if isinstance(data, list):
        records = data
    else:
        features = data.get("features", [])
        records = [f.get("properties", {}) for f in features]
    
    if not records:
        print("No speed data available")
        return
    
    df = pd.DataFrame(records)
    print(f"✓ Fetched {len(df)} speed records")
    
    # Group by line and calculate average speed
    if 'line_id' in df.columns and 'speed' in df.columns:
        line_speeds = df.groupby('line_id')['speed'].mean().sort_values(ascending=False).head(30)
        
        # Create bar chart
        fig = px.bar(
            x=line_speeds.index,
            y=line_speeds.values,
            labels={'x': 'Line', 'y': 'Average Speed (km/h)'},
            title='STIB/MIVB Top 30 Line Speeds (Aggregated)',
            color=line_speeds.values,
            color_continuous_scale='RdYlGn'
        )
        fig.write_html("stib_aggregated_speed.html")
        print(f"✅ Saved stib_aggregated_speed.html | Lines: {len(line_speeds)}")

if __name__ == "__main__":
    main()
