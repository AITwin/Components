import logging
import time
from datetime import datetime, timedelta
from typing import Dict

from sqlalchemy import Table

from src.configuration.model import ComponentConfiguration
from src.data.retrieve import (
    retrieve_latest_row,
    retrieve_after_datetime,
    retrieve_between_datetime,
    retrieve_latest_rows_before_datetime,
    retrieve_first_row,
)
from src.data.write import write_result

ZERO_DATE = datetime(1970, 1, 1)


logger = logging.getLogger("Harvester")


def run_harvester_on_schedule(
    harvester_config: ComponentConfiguration, tables: Dict[str, Table]
):
    logger.info(f"Running harvester {harvester_config.name} on schedule")
    while True:
        logger.debug(f"Running harvester {harvester_config.name}")
        if not run_harvester(harvester_config, tables):
            time.sleep(5)


def source_range_to_period_and_limit(
    latest_date: datetime, source_range: str | int
) -> (datetime, datetime, int):
    """
    Convert a source range to a period and limit.

    This function takes the latest date and a source range, which can be either a time period or a limit (count).
    If the source range represents a time period, the function calculates the start and end dates of the period,
    rounded to the previous period based on the given time unit. If the source range represents a limit, it returns
    the latest date and the specified limit.

    :param latest_date: The latest date harvested.
    :param source_range: The source range, which can be expressed as a time period or a limit (count).
        Time period examples: "3d" (3 days), "6h" (6 hours), "30m" (30 minutes), "120s" (120 seconds).
        Limit example: "100" (100 records).
    :return: A tuple containing the calculated start date, end date (for time periods), and limit (for counts).
    """

    if source_range is None:
        return latest_date, None, 1

    if type(source_range) == int or source_range.isdigit():
        return latest_date, None, int(source_range)

    if "d" in source_range:
        days = int(source_range.replace("d", ""))
        # Round latest date to the previous period
        latest_date = latest_date - timedelta(days=latest_date.day % days)
        return latest_date, latest_date + timedelta(days=days), None

    elif "h" in source_range:
        hours = int(source_range.replace("h", ""))
        # Round latest date to the previous period
        latest_date = latest_date - timedelta(hours=latest_date.hour % hours)
        return latest_date, latest_date + timedelta(hours=hours), None

    elif "m" in source_range:
        minutes = int(source_range.replace("m", ""))
        # Round latest date to the previous period
        latest_date = latest_date - timedelta(minutes=latest_date.minute % minutes)
        return latest_date, latest_date + timedelta(minutes=minutes), None

    elif "s" in source_range:
        seconds = int(source_range.replace("s", ""))
        # Round latest date to the previous period
        latest_date = latest_date - timedelta(seconds=latest_date.second % seconds)
        return latest_date, latest_date + timedelta(seconds=seconds), None


def run_harvester(harvester_config: ComponentConfiguration, tables: Dict[str, Table]) -> bool:
    """
    Run a harvester.
    :param harvester_config: The harvester configuration
    :param tables: The tables to use for the harvester (table name to table object (SQLAlchemy))
    :return: Whether the harvester ran successfully
    """
    table = tables[harvester_config.name]
    source_table = tables[harvester_config.source.name]

    # Get latest date harvested
    latest_row = retrieve_latest_row(table, with_null=True)

    if latest_row is None:
        # In case the harvester has never been run, get the first row from the source table
        row = retrieve_first_row(source_table)
        # Minus one second to make sure we include the first row
        latest_date = (row and (row.date - timedelta(seconds=1))) or ZERO_DATE
    else:
        latest_date = latest_row.date

    # Get source range
    start_date, end_date, limit = source_range_to_period_and_limit(
        latest_date, harvester_config.source_range
    )

    source_data = retrieve_between_datetime(source_table, start_date, end_date, limit)
    if not source_data:
        return False  # No new data to harvest

    if limit and harvester_config.source_range_strict and len(source_data) < limit:
        return False  # No new data to harvest, still building the amount of data specified by the limit

    if end_date and not retrieve_after_datetime(table, latest_date, 1):
        return False  # No new data to harvest, still building the same period

    storage_date = end_date or source_data[-1].date

    if limit == 1 and not end_date:
        source_data = source_data[0]

    dependencies = harvester_config.dependencies

    dependencies_data = {}

    for dependency, dependency_limit in zip(
        dependencies, harvester_config.dependencies_limit
    ):
        dependency_table = tables[dependency.name]
        dependency_data = retrieve_latest_rows_before_datetime(
            dependency_table, storage_date, dependency_limit
        )

        if dependency_limit == 1:
            if not dependency_data:
                raise ValueError(f"Dependency {dependency.name} not found")

            dependency_data = dependency_data[0]
        dependencies_data[dependency.name] = dependency_data

    # Harvest data
    harvester = harvester_config.component()

    result = harvester.run(source_data, **dependencies_data)

    if harvester_config.multiple_results:
        for item, source in zip(result, source_data):
            write_result(table, item, source.date)
    elif result is not None:
        write_result(table, result, storage_date)
    else:
        logger.debug(
            f"Harvester {harvester_config.name} returned None, writing empty result to database since "
            "harvester should always yield consistent results on the same input."
        )
        write_result(table, None, storage_date)

    return True
