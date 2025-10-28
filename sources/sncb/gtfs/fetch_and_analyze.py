import io, csv, requests, zipfile
from datetime import datetime

GTFS_URL   = "https://api.mobilitytwin.brussels/sncb/gtfs"
TOKEN      = "7eba4bf32fcb9502a0ff273fb3191db5b0bbde7cc7f75dc40304dcf2a91c07ed67a55cbbd4e26bf2675e01c5a19d4e7abf92849a5a9fe36d30b558d567dd10cc"  
DATE       = "2025-09-15"       
TIME_AFTER = "08:00:00"         

HEADERS = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}

def main():
    """Fetch and analyze SNCB GTFS data."""
    # Simplified version - just fetch and verify it's a ZIP file
    resp = requests.get(GTFS_URL, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    
    # Verify it's a ZIP file
    try:
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        files = zf.namelist()
        print(f"✓ Fetched GTFS ZIP with {len(files)} files")
        print(f"  Files: {', '.join(files[:5])}{'...' if len(files) > 5 else ''}")
    except zipfile.BadZipFile:
        print("⚠ Response is not a valid ZIP file")
        raise

if __name__ == "__main__":
    main()
