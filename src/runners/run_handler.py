import http.server
import json
import logging
from socketserver import ThreadingMixIn
from typing import Dict, List

from sqlalchemy import Table

from src.configuration.model import ComponentConfiguration

logger = logging.getLogger("Handler")


def _treat_query_parameters(
    query_parameters: Dict[str, str], component: ComponentConfiguration
):
    result = {}

    for key, value in component.query_parameters.items():
        if key not in query_parameters:
            return False, None

        # Parse query parameter
        try:
            # noinspection PyUnresolvedReferences
            value = __builtins__[value](query_parameters[key])
        except ValueError:
            return False, None

        result[key] = value

    return True, result


class ThreadedHTTPServer(ThreadingMixIn, http.server.HTTPServer):
    pass


class HttpRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(
        self,
        *args,
        allowed_hosts: List[str],
        handlers: Dict[str, ComponentConfiguration],
        tables: Dict[str, Table],
        **kwargs,
    ):
        self.allowed_hosts = allowed_hosts
        self.tables = tables
        self.handlers = handlers

        super().__init__(*args, **kwargs)

    def check_client_address(self):
        host = self.client_address[0]
        if host not in self.allowed_hosts:
            self.log_error(f"FORBIDDEN: {host} not in {self.allowed_hosts}")
            self.send_error(403, "Forbidden")
            return False
        return True

    def do_GET(self):
        if not self.check_client_address():
            return

        # Extract handler name from path (split at query parameters)
        handler_name = self.path[1:]
        query_parameters_string = None

        if "?" in handler_name:
            handler_name, query_parameters_string = handler_name.split("?")

        handler_config = self.handlers.get(handler_name, None)

        if handler_config is None:
            self.send_error(404, "Not Found")
            return

        # Extract query parameters from path
        success, query_parameters = _treat_query_parameters(
            dict(
                parameter.split("=") for parameter in query_parameters_string.split("&")
            )
            if query_parameters_string
            else {},
            handler_config,
        )

        if not success:
            self.send_error(400, "Bad Request")
            return

        self.send_response(200)

        logger.debug(
            f"Executing handler {handler_name} with parameters {query_parameters}"
        )

        # Execute handler
        result = handler_config.component(self.tables).run(**query_parameters)

        if result is None:
            self.send_error(404, "No data found for this specific query")
            return

        if handler_config.data_type == "json":
            self.send_header("Content-type", "text/json")
            self.end_headers()
            self.wfile.write(bytes(json.dumps(result), "utf8"))
        elif handler_config.data_type == "binary":
            self.send_header("Content-type", "application/octet-stream")
            self.end_headers()
            self.wfile.write(result)
        else:
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(bytes(result, "utf8"))

        return True


def run_handlers(
    handler_configurations: Dict[str, ComponentConfiguration],
    tables: Dict[str, Table],
    ip: str = "localhost",
    port: int = 8888,
    allowed_hosts: List[str] = None,
):
    if allowed_hosts is None:
        allowed_hosts = ["localhost", "127.0.0.1"]

    server_address = (ip, port)

    httpd = ThreadedHTTPServer(
        server_address,
        lambda *args, **kwargs: HttpRequestHandler(
            *args,
            allowed_hosts=allowed_hosts,
            handlers=handler_configurations,
            tables=tables,
            **kwargs,
        ),
    )

    logger.info(f"Running handlers on {ip}:{port}")

    httpd.serve_forever()
