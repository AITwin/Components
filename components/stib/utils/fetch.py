import os
from typing import Union

import requests

from components.stib.utils.constant import STIB_OPEN_DATA_URL_DATASET


def fetch_stib_dataset_records(dataset: str, limit=100, offset=0) -> Union[dict, list]:
    assert limit <= 100, "Limit must be less than 100"

    url = f"{STIB_OPEN_DATA_URL_DATASET}/{dataset}/records?offset={offset}&limit={limit}&timezone=UTC"

    response = auth_request_to_stib(url)

    if response.ok:
        records = []
        for record in response.json()["records"]:
            records.append(record["record"])
        return records

    raise ValueError(
        f"Error while fetching STIB dataset {dataset} records: {response.text}"
    )


def auth_request_to_stib(url: str, headers=None) -> requests.Response:
    if headers is None:
        headers = {}

    response = requests.get(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Apikey {os.environ['STIB_API_KEY']}",
            **headers,
        },
    )

    return response
