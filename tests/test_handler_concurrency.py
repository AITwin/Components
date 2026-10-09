"""At most MAX_CONCURRENT_HANDLERS handlers run at once; the other requests wait."""
import os
import sys
import threading
import time
import unittest
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FILE_STORAGE_DIRECTORY", "/tmp/storage")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import importlib  # noqa: E402

run_handler = importlib.import_module("src.runners.run_handler")


class HandlerConcurrency(unittest.TestCase):
    def test_parallel_requests_are_queued(self):
        lock, state = threading.Lock(), {"now": 0, "max": 0}

        class Slow:
            def __init__(self, tables):
                pass

            def run(self):
                with lock:
                    state["now"] += 1
                    state["max"] = max(state["max"], state["now"])
                time.sleep(0.2)
                with lock:
                    state["now"] -= 1
                return {"ok": True}

        config = SimpleNamespace(component=Slow, query_parameters={}, data_type="json")
        server = run_handler.ThreadedHTTPServer(
            ("127.0.0.1", 0),
            lambda *a, **k: run_handler.HttpRequestHandler(
                *a, allowed_hosts=["127.0.0.1"], handlers={"slow": config}, tables={}, **k),
        )
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_address[1]}/slow"
        try:
            with ThreadPoolExecutor(6) as pool:
                codes = list(pool.map(lambda _: urllib.request.urlopen(url).status, range(6)))
        finally:
            server.shutdown()
        self.assertEqual(codes, [200] * 6)
        self.assertEqual(state["max"], run_handler.MAX_CONCURRENT_HANDLERS)


if __name__ == "__main__":
    unittest.main()
