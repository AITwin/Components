import requests, pandas as pd

# --- CONFIG ---
URL   = "https://api.mobilitytwin.brussels/traffic/bike-count"
TOKEN = "YOUR_BEARER_TOKEN_HERE"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

def main():
    # Fetch bike count data
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    j = r.json()
    
    data_dict = j.get("data", {})
    if not data_dict:
        raise SystemExit("No bike count data found.")

    # Collect hourly counts
    records = []
    for counter_id, counter_data in data_dict.items():
        hour_cnt = counter_data.get("hour_cnt", 0)
        day_cnt = counter_data.get("day_cnt", 0)
        year_cnt = counter_data.get("year_cnt", 0)
        cnt_time = counter_data.get("cnt_time", "")
        
        records.append({
            "counter_id": counter_id,
            "hour_count": hour_cnt,
            "day_count": day_cnt,
            "year_count": year_cnt,
            "timestamp": cnt_time
        })

    df = pd.DataFrame(records)
    df = df.sort_values("hour_count", ascending=False)

    # Print summary
    print(f"\n{'='*75}")
    print(f"{'Brussels Bike Counter Summary — Hourly Counts'}")
    print(f"{'='*75}\n")
    
    print(f"{'Counter ID':<12} | {'Hour':>6} | {'Day':>8} | {'Year':>10} | Timestamp")
    print(f"{'-'*75}")
    
    for _, row in df.iterrows():
        print(f"{row['counter_id']:<12} | {row['hour_count']:6} | {row['day_count']:8} | "
              f"{row['year_count']:10} | {row['timestamp']}")

    print(f"\n{'='*75}")
    print(f"Total counters: {len(df)}")
    print(f"Total bikes (hour): {df['hour_count'].sum()}")
    print(f"Busiest counter: {df.iloc[0]['counter_id']} ({df.iloc[0]['hour_count']} bikes/hour)")
    print(f"{'='*75}\n")

    # Save to CSV
    df.to_csv("bike_counts.csv", index=False)
    print(f"✅ Saved bike_counts.csv | Counters: {len(df)}")
    
    # Create visualizations
    import plotly.express as px
    
    # Bar chart of hourly counts
    fig = px.bar(
        df.head(20),
        x='counter_id',
        y='hour_count',
        title='Brussels Bike Counters — Top 20 Hourly Counts',
        labels={'counter_id': 'Counter ID', 'hour_count': 'Bikes in Last Hour'},
        color='hour_count',
        color_continuous_scale='Greens',
        hover_data=['day_count', 'year_count']
    )
    fig.write_html("bike_count_chart.html")
    print(f"✅ Saved bike_count_chart.html")

if __name__ == "__main__":
    main()
