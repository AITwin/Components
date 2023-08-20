import os
from functools import lru_cache

from sqlalchemy import create_engine


class LazyEngineVariable:
    def __init__(self):
        self._engine = None

    def reset(self):
        self._engine = None
        self.connection.close()
        self.engine.dispose()
        self.connection.dispose()

    @property
    @lru_cache(maxsize=1)
    def engine(self):
        if self._engine is None:
            args = {}
            if "postgres" in os.environ.get("DATABASE_URL", ""):
                args["pool_pre_ping"] = True
                args["client_encoding"] = "utf8"

            self._engine = create_engine(os.environ.get("DATABASE_URL", ""), **args)
        return self._engine

    @property
    @lru_cache(maxsize=1)
    def connection(self):
        return self.engine.connect()

    def __del__(self):
        if self._engine is not None:
            self._engine.dispose()


lazy_engine = LazyEngineVariable()


def connection():
    return lazy_engine.connection
