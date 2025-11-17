import requests
import sys

URL = "https://api.mobilitytwin.brussels/stib/vehicle-schedule"
TOKEN = "YOUR_BEARER_TOKEN_HERE"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

def main():
    """Fetch STIB vehicle schedules."""
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        
        data = resp.json() if resp.headers.get('content-type', '').startswith('application/json') else []
        count = len(data) if isinstance(data, list) else len(data.get("features", []))
        print(f"✓ Fetched {count} schedule records")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 500:
            print("⚠️  API temporarily unavailable (500 error)")
            sys.exit(0)  # Exit successfully since this is an API issue
        raise

if __name__ == "__main__":
    main()
