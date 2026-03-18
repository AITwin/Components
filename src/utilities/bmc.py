import os

import requests

BMC_BASE_URL = "https://api-management-opendata-production.azure-api.net"


def bmc_request(path: str, params: dict = None) -> requests.Response:
    url = f"{BMC_BASE_URL}{path}"
    response = requests.get(
        url,
        headers={
            "Cache-Control": "no-cache",
            "bmc-partner-key": os.environ["BELGIAN_MOBILITY_API_KEY"],
        },
        params=params,
    )

    if not response.ok:
        raise ValueError(f"BMC API error ({response.status_code}): {response.text}")

    return response
