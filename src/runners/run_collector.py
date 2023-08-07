import logging
import time
from datetime import datetime

import schedule
from sqlalchemy import Table

from src.configuration.model import ComponentConfiguration
from src.data.write import write_result
from src.runners._utils import schedule_string_to_function

logger = logging.getLogger("Collector")


def run_collector_on_schedule(collector_config: ComponentConfiguration, table: Table):
    """
    Run a collector on a schedule.
    :param collector_config: The collector configuration
    :param table: The table to insert the data into
    """

    logger.info(
        f"Running collector {collector_config.name} on schedule: {collector_config.schedule}"
    )

    job = schedule_string_to_function(collector_config.schedule)

    job.do(run_collector, collector_config, table)

    while True:
        schedule.run_pending()
        time.sleep(1)


def run_collector(collector_config: ComponentConfiguration, table: Table):
    """
    Run a collector.
    :param collector_config: The collector configuration
    """
    logger.debug(f"Running collector {collector_config.name}")

    collector = collector_config.component()
    result = collector.run()

    if result is not None:
        write_result(table, result, datetime.now())

    return result
