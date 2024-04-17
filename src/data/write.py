import json
from datetime import datetime

from src.configuration.model import ComponentConfiguration
from src.data.client import client
from src.data.utils import convert_local_data_type_to_motion_lake_data_type


def write_result(
    component: ComponentConfiguration,
    data: bytes | dict | str | list,
    storage_date: datetime = None,
):
    """
    Write a result to a collection.
    :param component: The component configuration
    :param data: The data to write
    :param storage_date: The date to store the data under
    """

    if not isinstance(data, bytes):
        data = json.dumps(data).encode("utf-8")

    client.store(
        component.name,
        data,
        storage_date or datetime.now(),
        content_type=convert_local_data_type_to_motion_lake_data_type(component),
        create_collection=True
    )
