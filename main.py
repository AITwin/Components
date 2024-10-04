import logging
from multiprocessing import Process

from dotenv import load_dotenv

from parser import parse_arguments

if load_dotenv():
    from src.configuration.load import (
        load_all_components,
    )
    from src.data.sync_db import sync_db_from_configuration
    from src.runners import (
        run_collector,
        run_collector_on_schedule,
        run_handlers,
        run_harvester,
        run_harvester_on_schedule,
        run_parquetize_on_schedule,
        run_parquetize,
    )


def launch_harvesters(args, config, processes, tables):
    """
    Launch harvester processes.

    Parameters:
        args (argparse.Namespace): Parsed command-line arguments.
        config: Configuration object.
        processes (list): List to append the created processes.
        tables (dict): Tables from the database synchronization.
    """
    harvester_names_to_run = (
        config.harvesters.keys() if "all" in args.harvesters else args.harvesters
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
    """
    Launch collector processes.

    Parameters:
        args (argparse.Namespace): Parsed command-line arguments.
        config: Configuration object.
        processes (list): List to append the created processes.
        tables (dict): Tables from the database synchronization.
    """
    collector_names_to_run = (
        config.collectors.keys() if "all" in args.collectors else args.collectors
    )

    for name, collector_config in config.collectors.items():
        if name in collector_names_to_run:
            process = Process(
                target=run_collector if args.now else run_collector_on_schedule,
                args=(collector_config, tables[name]),
                kwargs={"fail_on_error": False},
            )
            process.start()
            processes.append(process)


def launch_handlers(args, config, processes, tables):
    """
    Launch handlers server process.

    Parameters:
        args (argparse.Namespace): Parsed command-line arguments.
        config: Configuration object.
        processes (list): List to append the created processes.
        tables (dict): Tables from the database synchronization.
    """
    handlers_names_to_run = (
        config.handlers.keys() if "all" in args.handlers else args.handlers
    )

    handlers_to_run = {
        name: config.handlers[name]
        for name in handlers_names_to_run
        if name in config.handlers
    }

    if handlers_to_run:
        if args.now:
            raise ValueError("Cannot run handlers with --now flag.")
        handler_process = Process(
            target=run_handlers,
            args=(handlers_to_run, tables, args.host, args.port, args.allowed_hosts),
        )
        handler_process.start()
        processes.append(handler_process)


def launch_parquetize(args, config, processes, tables):
    """
    Launch parquetize processes.

    Parameters:
        args (argparse.Namespace): Parsed command-line arguments.
        config: Configuration object.
        processes (list): List to append the created processes.
        tables (dict): Tables from the database synchronization.
    """
    parquetize_names_to_run = (
        config.parquetize.keys() if "all" in args.parquetize else args.parquetize
    )

    for name, parquetize_config in config.parquetize.items():
        if name in parquetize_names_to_run:
            process = Process(
                target=run_parquetize if args.now else run_parquetize_on_schedule,
                args=(parquetize_config, tables),
            )
            process.start()
            processes.append(process)


def main():
    config = load_all_components()
    tables = sync_db_from_configuration(config)
    args = parse_arguments()

    processes = []

    # Launch handlers server
    launch_handlers(args, config, processes, tables)

    # Launch collectors
    launch_collectors(args, config, processes, tables)

    # Launch harvesters
    launch_harvesters(args, config, processes, tables)

    # Launch parquetize
    launch_parquetize(args, config, processes, tables)

    # If no processes were started, display a message
    if not processes:
        logging.warning("No handlers, collectors, or harvesters were specified to run.")
        return

    for process in processes:
        process.join()


if __name__ == "__main__":
    main()
