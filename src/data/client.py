import dataclasses
import json
import os
from datetime import datetime
from enum import Enum
from typing import Protocol, Dict, Any, List

import requests

__all__ = [
    "Item",
    "Collection",
    "NetworkClient",
    "RequestsClient",
    "InnerClient",
    "BaseClient",
    "ContentType",
    "MAX_DATE",
    "MIN_DATE",
]

# Hopefully, we have better storage systems in 2250...
MAX_DATE = datetime(2250, 12, 31, 23, 59, 59, 999999)
MIN_DATE = datetime(1971, 1, 1, 0, 0, 0, 0)


class ServerError(Exception):
    pass


@dataclasses.dataclass
class Item:
    """
    A data item in the collection.
    """

    timestamp: datetime
    data: bytes


@dataclasses.dataclass
class Collection:
    """
    A summary of a collection. A collection is a group of items.
    """

    name: str
    min_timestamp: datetime
    max_timestamp: datetime
    count: int


class ContentType(Enum):
    JSON = 0
    RAW = 1
    GTFS_RT = 2
    CSV = 3
    GTFS = 4


class NetworkClient(Protocol):
    """
    A network client to make requests to the storage server.
    """

    def get(self, url: str, query_params: Dict[str, Any] = None) -> dict: ...

    def post(self, url: str, body: dict) -> dict: ...

    def raw_post(self, url: str, body: bytes) -> dict: ...

    def delete(self, url: str, body: dict = None) -> dict: ...


class RequestsClient(NetworkClient):
    """
    A network client using the requests library.
    """

    def __init__(self, base_url: str, **kwargs):
        super().__init__(**kwargs)
        self.base_url = base_url

    def get(self, url: str, query_params: Dict[str, Any] = None) -> dict:
        try:
            response = requests.get(self.base_url + url, params=query_params)
            if response.status_code > 399:
                raise ServerError("Server error occurred, message: " + response.text)
            return response.json()
        except requests.exceptions.RequestException:
            return {"error": "A request error occurred."}
        except requests.exceptions.JSONDecodeError:
            return {"error": "The response could not be decoded."}

    def post(self, url: str, body: dict) -> dict:
        try:
            response = requests.post(self.base_url + url, json=body)
            if response.status_code > 399:
                raise ServerError("Server error occurred, message: " + response.text)
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": "A request error occurred."}
        except requests.exceptions.JSONDecodeError as e:
            return {"error": "The response could not be decoded."}
    def raw_post(self, url: str, body: bytes) -> dict:
        try:
            response = requests.post(self.base_url + url, data=body)
            if response.status_code > 399:
                raise ServerError("Server error occurred, message: " + response.text)
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": "A request error occurred."}
        except requests.exceptions.JSONDecodeError as e:
            return {"error": "The response could not be decoded."}

    def delete(self, url: str, body: dict = None) -> dict:
        try:
            response = requests.delete(self.base_url + url, json=body)
            if response.status_code > 399:
                raise ServerError("Server error occurred, message: " + response.text)
            return response.json()
        except requests.exceptions.RequestException:
            return {"error": "A request error occurred."}
        except requests.exceptions.JSONDecodeError:
            return {"error": "The response could not be decoded."}


class InnerClient:
    def __init__(self, network_client: NetworkClient):
        self.network_client = network_client

    def flush_buffer(self, collection_name: str) -> dict:
        """
        Flush the buffered data in the collection with the given name.
        :param collection_name: The name of the collection to flush
        :return: None
        """
        return self.network_client.post(f"/flush/{collection_name}/", {})

    def create_collection(self, collection_name: str) -> dict:
        """
        Create a new collection with the given name.
        :param collection_name: The name of the collection to create
        :return: None
        """
        return self.network_client.post(f"/collection/", {"name": collection_name})

    def store(
        self,
        collection_name: str,
        data: bytes,
        timestamp: int,
        content_type: ContentType = None,
        create_collection: bool = False,
    ) -> dict:
        """
        Store the given data in the collection with the given name.
        :param collection_name: The name of the collection to store the data in
        :param data: The data to store
        :param timestamp: The timestamp to associate with the data
        :param content_type: The type of the data
        :param create_collection: Whether to create the collection if it does not exist
        :return: None
        """
        metadata = {"timestamp": timestamp, "create_collection": create_collection}

        if content_type is not None:
            metadata["content_type"] = content_type.value

        out = json.dumps(metadata).encode("utf-8") + '\n'.encode("utf-8") + data

        return self.network_client.raw_post(
            f"/store/{collection_name}/",
            out,
        )

    def query(
        self,
        collection_name: str,
        min_timestamp: int,
        max_timestamp: int,
        ascending: bool,
        limit: int = None,
        skip_data: bool = False,
    ) -> dict:
        """
        Query the data in the collection with the given name.
        :param collection_name: The name of the collection to query
        :param min_timestamp: The minimum timestamp to filter the data
        :param max_timestamp: The maximum timestamp to filter the data
        :param ascending: Whether to sort the data in ascending order
        :param limit: The limit of the data to retrieve
        :param skip_data: Whether to skip the data in the results (data will be None)
        :return: The data in the collection as a list of tuples of bytes and datetime
        """
        return self.network_client.get(
            f"/query/{collection_name}",
            {
                "min_timestamp": min_timestamp,
                "max_timestamp": max_timestamp,
                "ascending": ascending,
                "limit": limit or 1,
                "skip_data": skip_data,
            },
        )

    def get_collections(self) -> List[Collection]:
        """
        Get a list of all collections.
        :return: A list of collections
        """
        collections = self.network_client.get("/collections")
        return [
            Collection(
                name=collection["name"],
                min_timestamp=(
                    datetime.fromisoformat(collection["min_timestamp"])
                    if collection["min_timestamp"]
                    else None
                ),
                max_timestamp=(
                    datetime.fromisoformat(collection["max_timestamp"])
                    if collection["max_timestamp"]
                    else None
                ),
                count=collection["count"],
            )
            for collection in collections
        ]

    def advanced_query(
        self,
        collection_name: str,
        query: str,
        min_timestamp: datetime,
        max_timestamp: datetime,
    ):
        assert (
            "[table]" in query
        ), """Query must contain [table] placeholder (it will be replaced with a view on a 
        table)"""

        return self.network_client.post(
            f"/advanced/{collection_name}/",
            {
                "query": query,
                "min_timestamp": int(min_timestamp.timestamp()),
                "max_timestamp": int(max_timestamp.timestamp()),
            },
        )

    def delete_collection(self, collection_name: str):
        return self.network_client.delete(f"/delete/{collection_name}/", {})

    def get_collection_size(self, collection_name) -> int:
        return self.network_client.get(f"/size/{collection_name}")["size"]


class BaseClient:
    def __init__(self, lake_url: str = "http://localhost:8000"):
        """
        Initialize the client with the base URL of the storage server.
        :param lake_url: The base URL of the storage server
        """
        self.inner_client = InnerClient(RequestsClient(lake_url))

    @staticmethod
    def _parse_server_timestamp(timestamp: int) -> datetime:
        return datetime.fromtimestamp(timestamp)

    def _parse_results(self, results: List[dict]) -> List[Item]:
        return [
            Item(
                timestamp=self._parse_server_timestamp(item["timestamp"]),
                data=bytes.fromhex(item["data"]),
            )
            for item in results
        ]

    def flush_buffer(self, collection_name: str) -> dict:
        return self.inner_client.flush_buffer(collection_name)

    def create_collection(self, collection_name: str) -> dict:
        return self.inner_client.create_collection(collection_name)

    def store(
        self,
        collection_name: str,
        data: bytes,
        timestamp: datetime,
        content_type: ContentType = None,
        create_collection: bool = False,
    ) -> dict:
        return self.inner_client.store(
            collection_name,
            data,
            int(timestamp.timestamp()),
            content_type,
            create_collection,
        )

    def query(
        self,
        collection_name: str,
        min_datetime: datetime,
        max_datetime: datetime,
        ascending: bool,
        limit: int = None,
        skip_data: bool = False,
    ) -> dict:
        min_datetime = min_datetime or MIN_DATE
        max_datetime = max_datetime or MAX_DATE

        return self.inner_client.query(
            collection_name,
            int(min_datetime.timestamp()),
            int(max_datetime.timestamp()),
            ascending,
            limit,
            skip_data,
        )

    def get_last_items(self, collection_name: str, limit: int, skip_data: bool = False) -> List[Item]:
        response = self.query(collection_name, MIN_DATE, datetime.now(), False, limit, skip_data)
        return self._parse_results(response["results"])

    def get_last_item(self, collection_name: str, skip_data: bool = False) -> Item:
        results = self.get_last_items(collection_name, 1, skip_data)
        return (results or [None])[0]

    def get_first_items(self, collection_name: str, limit: int, skip_data: bool = False) -> List[Item]:
        response = self.query(collection_name, MIN_DATE, datetime.now(), True, limit, skip_data)
        return self._parse_results(response["results"])

    def get_first_item(self, collection_name: str, skip_data: bool = False) -> Item:
        items = self.get_first_items(collection_name, 1, skip_data)

        return (items or [None])[0]

    def get_items_between(
        self,
        collection_name: str,
        min_datetime: datetime,
        max_datetime: datetime,
        ascending: bool = True,
        limit: int = None,
        skip_data: bool = False,
    ) -> List[Item]:
        response = self.query(
            collection_name, min_datetime, max_datetime, ascending, limit, skip_data
        )
        return self._parse_results(response["results"])

    def get_items_before(
        self, collection_name: str, date: datetime, limit: int, skip_data: bool = False
    ) -> List[Item]:
        return self.get_items_between(collection_name, MIN_DATE, date, False, limit, skip_data)

    def get_items_after(
        self, collection_name: str, timestamp: datetime, limit: int, skip_data: bool = False
    ) -> List[Item]:
        return self.get_items_between(collection_name, timestamp, MAX_DATE, True, limit, skip_data)

    def get_collections(self) -> List[Collection]:
        return self.inner_client.get_collections()

    def advanced_query(
        self,
        collection_name: str,
        query: str,
        min_timestamp: datetime,
        max_timestamp: datetime,
    ):
        assert (
            "[table]" in query
        ), """Query must contain [table] placeholder (it will be replaced with a view on a table)"""
        return self.inner_client.advanced_query(
            collection_name, query, min_timestamp, max_timestamp
        )

    def delete_collection(self, collection_name: str):
        return self.inner_client.delete_collection(collection_name)

    def get_collection_size(self, collection_name: str) -> int:
        return self.inner_client.get_collection_size(collection_name)

client = BaseClient(os.environ.get("MOTION_LAKE_URL", "http://localhost:8000"))
