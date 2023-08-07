import argparse

# Set logging level to INFO
import logging
from multiprocessing import Process

from dotenv import load_dotenv

from src.configuration.load import load_all_components
from src.data.sync_db import sync_db_from_configuration
from src.runners.run_collector import run_collector, run_collector_on_schedule
from src.runners.run_handler import run_handlers
from src.runners.run_harvester import run_harvester_on_schedule, run_harvester

logging.basicConfig(level=logging.INFO)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Run specific handlers, collectors, and harvesters."
    )
    parser.add_argument(
        "--handlers", nargs="*", default=[], help="List of handler names to run"
    )
    parser.add_argument(
        "--collectors", nargs="*", default=[], help="List of collector names to run"
    )
    parser.add_argument(
        "--harvesters", nargs="*", default=[], help="List of harvester names to run"
    )
    parser.add_argument(
        "--now", action="store_true", help="Run harvesters or collectors once and exit"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8888,
        help="Port to run the handlers server on (default: 8888)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="localhost",
        help="Host to run the handlers server on (default: localhost)",
    )

    parser.add_argument(
        "--allowed-hosts",
        type=list,
        default=["localhost"],
        help="Allowed hosts for the handlers server (default: *)",
    )

    return parser.parse_args()


def _set_logging_levels_for_all_loggers(level):
    # Set for Handler, Collector, and Harvester
    logging.getLogger("Handler").setLevel(level)
    logging.getLogger("Collector").setLevel(level)
    logging.getLogger("Harvester").setLevel(level)


if __name__ == "__main__":
    load_dotenv()

    config = load_all_components()
    tables = sync_db_from_configuration(config)

    args = parse_arguments()

    processes = []

    # Run handlers
    handler_names_to_run = (
        args.handlers if "*" not in args.handlers else list(config.handlers.keys())
    )

    if handler_names_to_run:
        if args.now:
            raise ValueError("Cannot run handlers with --now flag")
        handlers = Process(
            target=run_handlers,
            args=(config.handlers, tables, args.host, args.port, args.allowed_hosts),
        )
        handlers.start()
        processes.append(handlers)

    # Run collectors
    collector_names_to_run = (
        args.collectors
        if "*" not in args.collectors
        else list(config.collectors.keys())
    )

    for name, collector_config in config.collectors.items():
        if name in collector_names_to_run:
            process = Process(
                target=run_collector if args.now else run_collector_on_schedule,
                args=(collector_config, tables[name]),
            )
            process.start()
            processes.append(process)

    # Run harvesters
    harvester_names_to_run = (
        args.harvesters
        if "*" not in args.harvesters
        else list(config.harvesters.keys())
    )

    for name, harvester_config in config.harvesters.items():
        if name in harvester_names_to_run:
            process = Process(
                target=run_harvester if args.now else run_harvester_on_schedule,
                args=(harvester_config, tables),
            )
            process.start()
            processes.append(process)

    for process in processes:
        process.join()
