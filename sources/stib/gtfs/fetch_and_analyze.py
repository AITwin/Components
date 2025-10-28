import io, zipfile, requests, pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

TOKEN    = "7eba4bf32fcb9502a0ff273fb3191db5b0bbde7cc7f75dc40304dcf2a91c07ed67a55cbbd4e26bf2675e01c5a19d4e7abf92849a5a9fe36d30b558d567dd10cc"
GTFS_URL = "https://api.mobilitytwin.brussels/stib/gtfs"
HEADERS  = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/zip"}

CENTRAL_PAT = r"(bruxelles-?central|brussel-?centraal|gare centrale|centraal station|brussels-?central)"

def load_gtfs():
    r = requests.get(GTFS_URL, headers=HEADERS, timeout=60)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    rd = lambda name: pd.read_csv(z.open(name))
    cal_dates = rd("calendar_dates.txt") if "calendar_dates.txt" in z.namelist() else pd.DataFrame(columns=["service_id","date","exception_type"])
    return (
        rd("stops.txt"),
        rd("stop_times.txt"),
        rd("trips.txt"),
        rd("routes.txt"),
        rd("calendar.txt"),
        cal_dates,
    )

def active_service_ids(calendar, calendar_dates, yyyymmdd: str, weekday_idx: int):
    daycol = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"][weekday_idx]
    cal = calendar.copy()
    # coerce types (robust to string ints)
    cal["start_date"] = pd.to_numeric(cal["start_date"], errors="coerce").astype("Int64")
    cal["end_date"]   = pd.to_numeric(cal["end_date"], errors="coerce").astype("Int64")
    cal[daycol]       = pd.to_numeric(cal[daycol], errors="coerce").fillna(0).astype(int)

    today_int = int(yyyymmdd)
    base = cal[(cal[daycol]==1) & (cal["start_date"]<=today_int) & (cal["end_date"]>=today_int)]["service_id"].astype(str)

    cd = calendar_dates.copy()
    if not cd.empty:
        cd["date"] = pd.to_numeric(cd["date"], errors="coerce").astype("Int64")
        cd["exception_type"] = pd.to_numeric(cd["exception_type"], errors="coerce").astype("Int64")
        adds = cd[(cd["date"]==today_int) & (cd["exception_type"]==1)]["service_id"].astype(str)
        rems = cd[(cd["date"]==today_int) & (cd["exception_type"]==2)]["service_id"].astype(str)
    else:
        adds = pd.Series(dtype=str); rems = pd.Series(dtype=str)

    return (set(base) | set(adds)) - set(rems)

def main():
    now = datetime.now(ZoneInfo("Europe/Brussels"))
    today, wk = now.strftime("%Y%m%d"), now.weekday()

    stops, stop_times, trips, routes, calendar, calendar_dates = load_gtfs()

    # find Central stops (station + platforms that contain the name)
    central = stops[stops.stop_name.fillna("").str.contains(CENTRAL_PAT, case=False, regex=True)]
    if central.empty:
        print(" No Brussels-Central stops found")
        return
    central_ids = set(central.stop_id.astype(str))

    active = active_service_ids(calendar, calendar_dates, today, wk)

    # trips that call at Central and are active today
    at_central = stop_times[stop_times.stop_id.astype(str).isin(central_ids)][["trip_id"]].merge(trips, on="trip_id", how="inner")
    if active:
        at_central = at_central[at_central.service_id.astype(str).isin(active)]

    if at_central.empty:
        print(" No active trips at Brussels-Central today (per calendar).")
        return

    serving = (
        at_central[["route_id"]]
        .drop_duplicates()
        .merge(routes, on="route_id", how="left")
        .loc[:, ["route_short_name","route_long_name","route_id","route_type"]]
        .sort_values(by=["route_short_name","route_long_name"], na_position="last")
        .reset_index(drop=True)
    )

    # print just the names (short + long). Keep id/type as hint (optional).
    print("=== STIB lines serving Brussels-Central today ===")
    for _, row in serving.iterrows():
        short = str(row["route_short_name"]) if pd.notna(row["route_short_name"]) else ""
        long  = str(row["route_long_name"])  if pd.notna(row["route_long_name"])  else ""
        if short and long:
            print(f"{short} — {long}")
        elif short:
            print(short)
        elif long:
            print(long)
        else:
            print(f"(route_id {row['route_id']})")

if __name__ == "__main__":
    main()