import random

import requests

from src.utilities.tokens import get_all_tokens

BMC_BASE_URL = "https://api-management-opendata-production.azure-api.net"

BMC_KEY = "BELGIAN_MOBILITY_API_KEY"

DEFAULT_PAGE_LIMIT = 100


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
    path: str, params: dict = None, limit: int = DEFAULT_PAGE_LIMIT
) -> list:
    """Fetch every record from a paginated BMC opendatasoft endpoint.

    Walks limit/offset until total_count is reached, or until a short page
    signals the end when the server omits total_count.
    """
    base = dict(params or {})
    all_results = []
    offset = 0

    while True:
        response = bmc_request(
            path, params={**base, "limit": limit, "offset": offset}
        )
        data = response.json()
        page = data.get("results", [])
        all_results.extend(page)

        total = data.get("total_count")
        if total is None:
            if len(page) < limit:
                break
        elif offset + limit >= total:
            break
        offset += limit

    return all_results
