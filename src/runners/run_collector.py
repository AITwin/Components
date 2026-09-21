import logging
import time
from datetime import datetime

import schedule
from sqlalchemy import Table

from src.configuration.model import ComponentConfiguration
from src.data.retrieve import retrieve_latest_row
from src.data.write import write_result
from src.runners._utils import schedule_string_to_function, schedule_string_to_time_delta

logger = logging.getLogger("Collector")


def _is_overdue(collector_config: ComponentConfiguration, table: Table) -> bool:
    """Whether the last collected row is older than the schedule interval.

    An interval schedule ("7d", "1h") first fires one full interval after the
    process starts, so a process that restarts more often than that never
    fires it: the weekly TMC event codes collector last ran in April 2026.
    Running once at startup when the table is already stale closes that hole.
    Time-of-day schedules ("04:00") are left alone.
    """
    if ":" in collector_config.schedule:
        return False
    latest = retrieve_latest_row(table)
    if latest is None:
        return True
    return datetime.now() - latest.date > schedule_string_to_time_delta(collector_config.schedule)


def run_collector_on_schedule(
    collector_config: ComponentConfiguration, table: Table, fail_on_error: bool = False
):
    """
    Run a collector on a schedule.
    :param collector_config: The collector configuration
    :param table: The table to insert the data into
    :param fail_on_error: Whether to fail on error
    """

    logger.info(
        f"Running collector {collector_config.name} on schedule: {collector_config.schedule}"
    )

    job = schedule_string_to_function(collector_config.schedule)

    job.do(run_collector, collector_config, table, fail_on_error)

    if _is_overdue(collector_config, table):
        logger.info(f"Collector {collector_config.name} is overdue, running it now")
        run_collector(collector_config, table, fail_on_error)

    while True:
        schedule.run_pending()
        time.sleep(1)


def run_collector(
    collector_config: ComponentConfiguration, table: Table, fail_on_error: bool = True
):
    """
    Run a collector.
    :param collector_config: The collector configuration
    :param table: The table to insert the data into
    :param fail_on_error: Whether to fail on error
    """
    logger.debug(f"Running collector {collector_config.name}")

    try:
        collector = collector_config.component()
        result = collector.run()

        if result is not None:
            write_result(collector_config, table, result, datetime.now())

        return result
    # catch traceback and log it
    except Exception as e:
        logger.exception(f"Error running collector {collector_config.name}, stopped with error: {e}")
        if fail_on_error:
            raise e


