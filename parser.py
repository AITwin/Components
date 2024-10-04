import argparse
import logging


def setup_logging(level):
    """
    Set up logging configuration.

    Parameters:
        level (int): Logging level.
    """
    logging.basicConfig(level=level)
    logging.getLogger("Handler").setLevel(level)
    logging.getLogger("Collector").setLevel(level)
    logging.getLogger("Harvester").setLevel(level)


def parse_arguments():
    """
    Parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Run specific handlers, collectors, and harvesters."
    )
    parser.add_argument(
        "--init-dependencies",
        action="store_true",
        help=(
            "Runs all harvesters in the order that maximizes the number of dependencies "
            "that are satisfied."
        ),
    )
    parser.add_argument(
        "--handlers",
        nargs="*",
        default=[],
        help="List of handler names to run.",
    )
    parser.add_argument(
        "--collectors",
        nargs="*",
        default=[],
        help="List of collector names to run.",
    )
    parser.add_argument(
        "--harvesters",
        nargs="*",
        default=[],
        help="List of harvester names to run.",
    )
    parser.add_argument(
        "--now",
        action="store_true",
        help="Run harvesters or collectors once and exit.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8888,
        help="Port to run the handlers server on (default: 8888).",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="localhost",
        help="Host to run the handlers server on (default: localhost).",
    )
    parser.add_argument(
        "--allowed-hosts",
        nargs="*",
        default=["localhost", "127.0.0.1"],
        help="Allowed hosts for the handlers server (default: localhost, 127.0.0.1).",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="WARNING",
        help="Set the logging level (default: WARNING).",
    )
    parser.add_argument(
        "--parquetize",
        nargs="*",
        default=[],
        help="List of harvester names to run.",
    )

    return parser.parse_args()
