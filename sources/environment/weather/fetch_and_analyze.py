# weather_current_card_aligned.py — perfectly aligned current-conditions card

import requests, math, unicodedata
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL   = "https://api.mobilitytwin.brussels/environment/weather"
TOKEN = "7eba4bf32fcb9502a0ff273fb3191db5b0bbde7cc7f75dc40304dcf2a91c07ed67a55cbbd4e26bf2675e01c5a19d4e7abf92849a5a9fe36d30b558d567dd10cc"  # put token if required
HDRS  = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
TZ    = ZoneInfo("Europe/Brussels")

# change to '-' if your terminal renders '—' wider than 1 char
DASH = "—"

def k_to_c(v):
    if v is None:
        return float("nan")
    try:
        v = float(v)
    except (TypeError, ValueError):
        return float("nan")
    return v - 273.15 if v > 200 else v

def wind_dir(deg):
    if deg is None: return "—"
    pts=["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
    i=int((deg%360)/22.5+0.5)%16
    return f"{pts[i]} ({int(round(deg))}°)"

def main():
    r = requests.get(URL, headers=HDRS, timeout=15); r.raise_for_status()
    j = r.json() or {}

    main_data = j.get("main", {})
    wx   = (j.get("weather") or [{}])[0]
    wind = j.get("wind", {})
    sys  = j.get("sys", {})
    name = j.get("name") or "Brussels"

    temp_c  = k_to_c(main_data.get("temp"))
    feels_c = k_to_c(main_data.get("feels_like", temp_c))
    hum     = main_data.get("humidity")
    press   = main_data.get("pressure")
    w_ms    = wind.get("speed")
    w_kmh   = None if w_ms is None else w_ms*3.6
    w_dir   = wind_dir(wind.get("deg"))
    sky_main= (wx.get("main") or "—").strip()
    sky_desc= (wx.get("description") or "").strip()
    skyline = sky_main if sky_desc.lower()==sky_main.lower() else f"{sky_main} {DASH} {sky_desc}"

    dt = j.get("dt")
    if isinstance(dt,(int,float)) and dt>1e12: dt/=1000.0
    ts = (datetime.fromtimestamp(dt, tz=timezone.utc) if isinstance(dt,(int,float)) else datetime.now(timezone.utc)).astimezone(TZ)

    sunrise=sys.get("sunrise"); sunset=sys.get("sunset")
    def to_local(x):
        if not isinstance(x,(int,float)): return None
        if x>1e12: x/=1000.0
        return datetime.fromtimestamp(x, tz=timezone.utc).astimezone(TZ)
    sr=to_local(sunrise); ss=to_local(sunset)
    dayflag = ("Day" if (sr and ss and sr<=ts<=ss) else "Night") if (sr and ss) else None

    humtxt  = f"{hum}%" if hum is not None else "—"
    prestxt = f"{press} hPa" if press is not None else "—"
    windspd = "—" if w_ms is None else f"{w_ms:.1f} m/s ({w_kmh:.0f} km/h)"

    lines = [
        f"{name} {DASH} {ts:%Y-%m-%d %H:%M} ({TZ.key})",
        f"Temp:   {temp_c:.1f} °C    Feels: {feels_c:.1f} °C",
        f"Sky:    {skyline}",
        f"Humid:  {humtxt}   Press: {prestxt}",
        f"Wind:   {windspd}   Dir: {w_dir}",
    ]
    if dayflag:
        lines.append(f"Light:  {dayflag}")

    # compute inner width from the longest line
    inner = max(len(s) for s in lines)
    top    = "┌" + "─" * (inner + 2) + "┐"
    rule   = "├" + "─" * (inner + 2) + "┤"
    bottom = "└" + "─" * (inner + 2) + "┘"

    print(top)
    # header
    print("│ " + lines[0].ljust(inner) + " │")
    print(rule)
    # rest
    for s in lines[1:]:
        print("│ " + s.ljust(inner) + " │")
    print(bottom)

if __name__ == "__main__":
    main()