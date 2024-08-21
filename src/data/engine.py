import os
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, Connection


class LazyEngine:
    def __init__(self):
        self._engine = None

    def reset(self):
        if self._engine is not None:
            self._engine.dispose()
            self._cached_engine.cache_clear()

    @property
    def engine(self) -> Engine:
        return self._cached_engine()

    @lru_cache(maxsize=1)
    def _cached_engine(self) -> Engine:
        if self._engine is None:
            args = {}
            if "postgres" in os.environ.get("DATABASE_URL", ""):
                args["pool_pre_ping"] = True
                args["client_encoding"] = "utf8"
                args["pool_size"] = 5
                args["max_overflow"] = 10
                args["pool_recycle"] = 1800

            self._engine = create_engine(os.environ.get("DATABASE_URL", ""), **args)
        return self._engine

    def get_connection(self) -> Connection:
        return self.engine.connect()

    def __del__(self):
        self.reset()

lazy_engine = LazyEngine()

def connection() -> Connection:
    return lazy_engine.get_connection()
