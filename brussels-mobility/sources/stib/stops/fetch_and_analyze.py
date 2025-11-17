import requests, pandas as pd, plotly.express as px, plotly.graph_objects as go

URL   = "https://api.mobilitytwin.brussels/stib/speed"
TOKEN = "YOUR_BEARER_TOKEN_HERE"

def main():
    r = requests.get(URL, headers={"Authorization": f"Bearer {TOKEN}"})
    r.raise_for_status()
    df = pd.DataFrame(r.json())

    # average speed per line
    avg = df.groupby("lineId")["speed"].mean().sort_values()

    print("Slowest lines right now:")
    for line, spd in avg.head(5).items():
        print(f"Line {line} : {spd:.2f} km/h")
    
    # Create visualization
    fig = px.bar(
        x=avg.head(20).index,
        y=avg.head(20).values,
        title='STIB/MIVB 20 Slowest Lines (Current Speed)',
        labels={'x': 'Line', 'y': 'Speed (km/h)'},
        color=avg.head(20).values,
        color_continuous_scale='RdYlGn_r'
    )
    fig.write_html("stib_slowest_lines.html")
    print(f"\n✅ Saved stib_slowest_lines.html")

if __name__ == "__main__":
    main()