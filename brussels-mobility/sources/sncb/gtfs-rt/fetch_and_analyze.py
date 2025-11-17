import requests

GTFS_RT_URL = "https://api.mobilitytwin.brussels/sncb/gtfs-rt"
TOKEN = "YOUR_BEARER_TOKEN_HERE"
HEADERS = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}

def main():
    """Fetch SNCB GTFS-RT data."""
    try:
        resp = requests.get(GTFS_RT_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        
        data = resp.content
        print(f"✓ Fetched GTFS-RT data: {len(data)} bytes")
        print(f"  Content type: {resp.headers.get('content-type', 'unknown')}")
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            print("⚠️  SNCB GTFS-RT endpoint not available (404). This endpoint may not be active.")
            return
        raise

if __name__ == "__main__":
    main()
