import random
import time

import requests
from google.transit import gtfs_realtime_pb2

from src.utilities.tokens import get_all_tokens

BMC_BASE_URL = "https://api-management-opendata-production.azure-api.net"

BMC_KEY = "BELGIAN_MOBILITY_API_KEY"

BMC_PAGE_SIZE = 1000


def bmc_request(path: str, params: dict = None) -> requests.Response:
    url = f"{BMC_BASE_URL}{path}"
    tokens = get_all_tokens(BMC_KEY)
    random.shuffle(tokens)

    for token in tokens:
        response = requests.get(
            url,
            headers={
                "Cache-Control": "no-cache",
                "bmc-partner-key": token,
            },
            params=params,
        )
        if response.ok:
            return response


    raise ValueError(f"BMC API error ({response.status_code}): {response.text}")


# BMC relayed the same De Lijn trip-update feed from 2026-10-22 14:20 UTC to
# the next morning, header and trips frozen, and every 20 s poll stored it.
# At night the SNCB and TEC feeds legitimately stand still for up to 4 h (week
# of 2026-10-16), so only a feed frozen longer than that is refused.
MAX_REALTIME_FEED_AGE = 6 * 3600  # seconds


def bmc_realtime_feed(path: str) -> bytes:
    """A GTFS-RT feed from BMC, refused when its header is too old to be live."""
    content = bmc_request(path, params=dict(format="protobuf")).content
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(content)
    age = time.time() - feed.header.timestamp
    if age > MAX_REALTIME_FEED_AGE:
        raise ValueError(f"BMC feed {path} is frozen: header is {age / 3600:.1f} h old")
    return content


def bmc_request_all(
    path: str, params: dict = None, page_size: int = BMC_PAGE_SIZE
) -> list:
    """Walk a paginated BMC opendatasoft endpoint and return every record.

    The opendatasoft API caps a single response at `limit` rows, so a plain
    `bmc_request` only sees the first page. Step through limit/offset until
    `total_count` is reached, or until a short page signals the tail when
    the server omits `total_count`.
    """
    base_params = dict(params or {})
    records = []
    offset = 0

    while True:
        response = bmc_request(
            path, params={**base_params, "limit": page_size, "offset": offset}
        )
        payload = response.json()
        page = payload.get("results", [])
        records.extend(page)

        total = payload.get("total_count")
        if total is not None:
            if offset + page_size >= total:
                break
        elif len(page) < page_size:
            break

        offset += page_size

    return records
