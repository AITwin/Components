import argparse
import logging
from multiprocessing import Process

from dotenv import load_dotenv

from src.configuration.load import (
    load_all_components,
    get_optimal_dependencies_wise_order,
)
from src.data.sync_db import sync_db_from_configuration
from src.runners.run_collector import run_collector, run_collector_on_schedule
from src.runners.run_handler import run_handlers
from src.runners.run_harvester import run_harvester_on_schedule, run_harvester


def setup_logging(level):
    logging.basicConfig(level=level)
    logging.getLogger("Handler").setLevel(level)
    logging.getLogger("Collector").setLevel(level)
    logging.getLogger("Harvester").setLevel(level)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Run specific handlers, collectors, and harvesters."
    )
    parser.add_argument(
        "--init-dependencies",
        action="store_true",
        help="Runs all harvesters in the order that maximizes the number of dependencies that are satisfied",
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
        nargs="*",
        default=["localhost", "127.0.0.1"],
        help="Allowed hosts for the handlers server (default: *)",
    )
    return parser.parse_args()


def launch_harvesters(args, config, processes, tables):
    harvester_names_to_run = (
        args.harvesters if "all" not in args.harvesters else config.harvesters.keys()
    )
    for name, harvester_config in config.harvesters.items():
        if name in harvester_names_to_run:
            process = Process(
                target=run_harvester if args.now else run_harvester_on_schedule,
                args=(harvester_config, tables),
            )
            process.start()
            processes.append(process)


def launch_collectors(args, config, processes, tables):
    collector_names_to_run = (
        args.collectors if "all" not in args.collectors else config.collectors.keys()
    )

    for name, collector_config in config.collectors.items():
        if name in collector_names_to_run:
            process = Process(
                target=run_collector if args.now else run_collector_on_schedule,
                args=(collector_config, tables[name]),
                kwargs=dict(fail_on_error=False)
            )
            process.start()
            processes.append(process)


def launch_handlers(args, config, processes, tables):
    handlers_names_to_run = (
        args.handlers if "all" not in args.handlers else config.handlers.keys()
    )

    handlers_to_run = {
        name: config.handlers[name]
        for name in handlers_names_to_run
    }

    if args.handlers:
        if args.now:
            raise ValueError("Cannot run handlers with --now flag")
        handlers = Process(
            target=run_handlers,
            args=(handlers_to_run, tables, args.host, args.port, args.allowed_hosts),
        )
        handlers.start()
        processes.append(handlers)


def main():
    load_dotenv()
    config = load_all_components()
    tables = sync_db_from_configuration(config)
    args = parse_arguments()

    setup_logging(logging.INFO)

    # Run harvesters in optimal order which maximizes the number of dependencies that are satisfied.
    if args.init_dependencies:
        logging.info("Running harvesters in optimal order")
        harvesters = get_optimal_dependencies_wise_order(config.harvesters)
        for harvester in harvesters:
            run_harvester(harvester, tables)
        exit(0)

    processes = []

    # Launch handlers server
    launch_handlers(args, config, processes, tables)

    # Launch collectors
    launch_collectors(args, config, processes, tables)

    # Launch harvesters
    launch_harvesters(args, config, processes, tables)

    for process in processes:
        process.join()


if __name__ == "__main__":
    main()
