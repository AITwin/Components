import requests, pandas as pd
from datetime import datetime

# --- CONFIG ---
URL   = "https://api.mobilitytwin.brussels/infrabel/punctuality"
TOKEN = "YOUR_BEARER_TOKEN_HERE"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

def main():
    # Fetch train punctuality data
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    
    if not data:
        raise SystemExit("No punctuality data found.")

    df = pd.DataFrame(data)

    # Parse delays (in seconds)
    df["delay_dep"] = pd.to_numeric(df.get("delay_dep"), errors="coerce")
    df["delay_arr"] = pd.to_numeric(df.get("delay_arr"), errors="coerce")

    # Convert to minutes
    df["delay_dep_min"] = df["delay_dep"] / 60.0
    df["delay_arr_min"] = df["delay_arr"] / 60.0

    # Find most delayed trains
    delayed = df[df["delay_arr_min"].notna() & (df["delay_arr_min"] > 0)].copy()
    delayed = delayed.sort_values("delay_arr_min", ascending=False).head(20)

    # Print summary
    print(f"\n{'='*90}")
    print(f"{'Infrabel Train Punctuality Report — Top 20 Most Delayed Arrivals'}")
    print(f"{'='*90}\n")
    
    print(f"{'Train':<10} | {'Service':<8} | {'Station':<25} | {'Planned':>8} | {'Delay (min)':>12}")
    print(f"{'-'*90}")
    
    for _, row in delayed.iterrows():
        train = row.get("train_no", "N/A")
        service = row.get("train_serv", "N/A")
        station = row.get("ptcar_lg_nm_nl", "Unknown")[:25]
        planned_time = row.get("planned_time_arr", "")
        delay_min = row["delay_arr_min"]
        
        print(f"{train:<10} | {service:<8} | {station:<25} | {planned_time:>8} | {delay_min:>11.1f}")

    print(f"\n{'='*90}")
    
    # Overall statistics
    avg_delay_arr = df["delay_arr_min"].mean()
    avg_delay_dep = df["delay_dep_min"].mean()
    on_time_arr = len(df[(df["delay_arr_min"] >= -1) & (df["delay_arr_min"] <= 5)])
    total = len(df[df["delay_arr_min"].notna()])
    on_time_pct = (on_time_arr / total * 100) if total > 0 else 0
    
    print(f"Total trains: {len(df)}")
    print(f"Avg arrival delay: {avg_delay_arr:.1f} min")
    print(f"Avg departure delay: {avg_delay_dep:.1f} min")
    print(f"On-time arrivals (±5 min): {on_time_arr}/{total} ({on_time_pct:.1f}%)")
    print(f"{'='*90}\n")

    # Save to CSV
    df.to_csv("infrabel_punctuality.csv", index=False)
    print(f"✅ Saved infrabel_punctuality.csv | Records: {len(df)}")

if __name__ == "__main__":
    main()
