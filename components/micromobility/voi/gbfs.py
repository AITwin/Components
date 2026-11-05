"""Voi GBFS access for Brussels.

Voi does not publish a public GBFS feed for Brussels: its endpoints answer 401
without a partner token. The feed is configured through the environment:

- VOI_GBFS_URL: the gbfs.json discovery URL Voi gives partners
- VOI_GBFS_TOKEN: optional, sent as a Bearer token

Until VOI_GBFS_URL is set the collectors log a warning and store nothing.
"""
import logging
import os

import requests

logger = logging.getLogger("Voi")

TIMEOUT = 30

# GBFS 3 renamed free_bike_status to vehicle_status
FEED_ALIASES = {
    "free_bike_status": ("free_bike_status", "vehicle_status"),
    "vehicle_types": ("vehicle_types",),
    "geofencing_zones": ("geofencing_zones",),
}


def _headers() -> dict:
    token = os.environ.get("VOI_GBFS_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _get(url: str) -> dict:
    response = requests.get(url, headers=_headers(), timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def feed_urls(discovery: dict) -> dict:
    """Map feed name to URL from a GBFS 2 (data.<lang>.feeds) or GBFS 3 (data.feeds) discovery file."""
    data = discovery["data"]
    if "feeds" in data:
        feeds = data["feeds"]
    else:
        lang = "en" if "en" in data else next(iter(data))
        feeds = data[lang]["feeds"]
    return {feed["name"]: feed["url"] for feed in feeds}


def fetch_feed(name: str):
    """Return the JSON of one Voi feed, or None when the feed is not configured."""
    discovery_url = os.environ.get("VOI_GBFS_URL")
    if not discovery_url:
        logger.warning("VOI_GBFS_URL is not set, skipping Voi %s", name)
        return None
    urls = feed_urls(_get(discovery_url))
    for alias in FEED_ALIASES[name]:
        if alias in urls:
            return _get(urls[alias])
    raise KeyError(f"Voi discovery file has no {name} feed (has: {', '.join(sorted(urls))})")
