# code_sample.py — mini generator for STIB/MIVB Stops
import os, json, requests, pathlib

URL = "https://api.mobilitytwin.brussels/stib/stops"
TOKEN = "YOUR_BEARER_TOKEN_HERE"  # replace if not using env var

here = pathlib.Path(__file__).resolve().parent
out_path = here / "response_sample.json"

r = requests.get(URL, headers={"Authorization": f"Bearer {TOKEN}"}, timeout=60)
r.raise_for_status()
data = r.json()

# Trim to 3 features (keep valid GeoJSON structure)
features = (data.get("features") or [])[:3]
trimmed = {"type": data.get("type", "FeatureCollection"), "features": features}

with open(out_path, "w", encoding="utf-8") as f:
  json.dump(trimmed, f, ensure_ascii=False, indent=2)

print(f"Wrote {len(features)} stops → {out_path}")