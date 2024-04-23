import dataclasses
import json
from datetime import datetime
from typing import Union, List

from motion_lake_client import Item

from src.configuration.model import ComponentConfiguration
from src.data.client import client


@dataclasses.dataclass
class Data:
    date: datetime
    data: Union[dict, list, str, bytes]


def convert_result(component_configuration: ComponentConfiguration, data: Item) -> Data:
    if data is None:
        return None

    if component_configuration.data_type == "json":
        try:
            return Data(
                date=data.timestamp,
                data=json.loads(data.data) if data.data else None
            )
        except json.JSONDecodeError:
            print(data.data[:100])

    return Data(
        data.timestamp,
        data.data
    )


def _results_wrapper(func):
    def wrapper(component_configuration: ComponentConfiguration, *args, **kwargs) -> List[Data] or Data:
        results = func(component_configuration, *args, **kwargs)
        if not isinstance(results, list):
            return convert_result(component_configuration, results)
        return [convert_result(component_configuration, result) for result in results]

    return wrapper


@_results_wrapper
def retrieve_latest_row(component_configuration: ComponentConfiguration, skip_data: bool = False) -> Data:
    """
    Get the latest row from a table.
    :param component_configuration: The name of the collection
    :param skip_data: Whether to include the data in the results
    :return: The latest row
    """
    return client.get_last_item(component_configuration.name, skip_data)


@_results_wrapper
def retrieve_first_row(component_configuration: ComponentConfiguration, skip_data: bool = False) -> Data:
    """
    Get the first row from a table.
    :param component_configuration: The name of the collection
    :param skip_data: Whether to include the data in the results
    :return: The first row
    """
    return client.get_first_item(component_configuration.name, skip_data)


@_results_wrapper
def retrieve_after_datetime(component_configuration: ComponentConfiguration, date: datetime, limit: int,skip_data: bool = False) -> List[Data]:
    """
    Get rows after a certain date.
    :param component_configuration: The name of the collection
    :param date: The date to get rows after
    :param limit: The maximum number of rows to return
    :param skip_data: Whether to include the data in the results
    :return: A list of rows
    """
    return client.get_items_after(component_configuration.name, date, limit,skip_data)


@_results_wrapper
def retrieve_before_datetime(component_configuration: ComponentConfiguration, date: datetime, limit: int,skip_data: bool = False) -> List[Data]:
    """
    Get rows before a certain date.
    :param component_configuration: The name of the collection
    :param date: The date to get rows before
    :param limit: The maximum number of rows to return
    :param skip_data: Whether to include the data in the results
    :return: A list of rows
    """
    return client.get_items_before(component_configuration.name, date, limit,skip_data)


@_results_wrapper
def retrieve_between_datetime(
        component_configuration: ComponentConfiguration, start_date: datetime, end_date: datetime, limit: int,
        ascending: bool = True, skip_data: bool = False
) -> List[Data]:
    """
    Get rows between two dates.
    :param component_configuration: The name of the collection
    :param start_date: The start date
    :param end_date: The end date
    :param limit: The maximum number of rows to return
    :param ascending: Whether to sort the data in ascending order
    :param skip_data: Whether to include the data in the results
    :return: A list of rows
    """
    return client.get_items_between(component_configuration.name, start_date, end_date, ascending, limit, skip_data)


@_results_wrapper
def retrieve_latest_rows_before_datetime(
        component_configuration: ComponentConfiguration, date: datetime, limit: int, skip_data: bool = False
) -> List[Data]:
    """
    Get the latest rows before a certain date.
    :param component_configuration: The name of the collection
    :param date: The date to get rows before
    :param limit: The maximum number of rows to return
    :param skip_data: Whether to include the data in the results
    :return: A list of rows
    """
    return client.get_items_before(component_configuration.name, date, limit, skip_data)[::-1]
