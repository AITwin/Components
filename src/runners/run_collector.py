import logging
import time
from datetime import datetime, timedelta

import schedule
from sqlalchemy import Table

from src.configuration.model import ComponentConfiguration
from src.data.retrieve import retrieve_latest_row
from src.data.write import write_result
from src.runners._utils import schedule_string_to_function, schedule_string_to_time_delta

logger = logging.getLogger("Collector")


def _last_due(schedule_string: str, now: datetime) -> datetime:
    """The latest moment a time-of-day schedule ("04:20") was due, at or before `now`."""
    hour, minute = (int(x) for x in schedule_string.split(":")[:2])
    due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return due if due <= now else due - timedelta(days=1)


def _is_overdue(collector_config: ComponentConfiguration, table: Table, now: datetime = None) -> bool:
    """Whether the last run the schedule called for left no row.

    An interval schedule ("7d", "1h") first fires one full interval after the
    process starts, so a process that restarts more often than that never
    fires it: the weekly TMC event codes collector last ran in April 2026.
    A time-of-day schedule ("04:20") fires once a day, so one failed run (on
    2026-09-23 the database refused connections at 00:06) cost a whole day of
    STIB stops and SNCB timetable. Either way the process restarts hourly, so
    running once at startup when the due run left no row closes the hole.
    """
    now = now or datetime.now()
    latest = retrieve_latest_row(table)
    if latest is None:
        return True
    if ":" in collector_config.schedule:
        return latest.date < _last_due(collector_config.schedule, now)
    return now - latest.date > schedule_string_to_time_delta(collector_config.schedule)


# Schedules at least this far apart retry a failed run instead of waiting for
# the next one: every RETRY_EVERY, RETRY_TIMES times.
RETRY_FROM = timedelta(hours=1)
RETRY_EVERY_MINUTES = 15
RETRY_TIMES = 4


def _period(schedule_string: str) -> timedelta:
    return timedelta(days=1) if ":" in schedule_string else schedule_string_to_time_delta(schedule_string)


def _run_or_retry(collector_config: ComponentConfiguration, table: Table, fail_on_error: bool):
    if run_collector(collector_config, table, fail_on_error) is not _FAILED:
        return
    if _period(collector_config.schedule) < RETRY_FROM:
        return
    attempts = {"left": RETRY_TIMES}

    def retry():
        attempts["left"] -= 1
        failed = run_collector(collector_config, table, fail_on_error) is _FAILED
        if not failed or attempts["left"] <= 0:
            return schedule.CancelJob

    logger.info(f"Collector {collector_config.name} failed, retrying every {RETRY_EVERY_MINUTES} min")
    schedule.every(RETRY_EVERY_MINUTES).minutes.do(retry)


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

    job.do(_run_or_retry, collector_config, table, fail_on_error)

    if _is_overdue(collector_config, table):
        logger.info(f"Collector {collector_config.name} is overdue, running it now")
        _run_or_retry(collector_config, table, fail_on_error)

    while True:
        schedule.run_pending()
        time.sleep(1)


_FAILED = object()


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
        return _FAILED


