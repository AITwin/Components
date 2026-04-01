import random

import requests

from src.utilities.tokens import get_all_tokens

BMC_BASE_URL = "https://api-management-opendata-production.azure-api.net"

BMC_KEY = "BELGIAN_MOBILITY_API_KEY"


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
        if response.status_code != 429:
            break

    raise ValueError(f"BMC API error ({response.status_code}): {response.text}")
