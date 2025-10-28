import requests
import sys

URL = "https://api.mobilitytwin.brussels/stib/vehicle-schedule"
TOKEN = "7eba4bf32fcb9502a0ff273fb3191db5b0bbde7cc7f75dc40304dcf2a91c07ed67a55cbbd4e26bf2675e01c5a19d4e7abf92849a5a9fe36d30b558d567dd10cc"
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
