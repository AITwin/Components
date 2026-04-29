import random

import requests

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
