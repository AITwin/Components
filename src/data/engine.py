import os
from functools import lru_cache

from sqlalchemy import create_engine


class LazyEngineVariable:
    def __init__(self):
        self._engine = None

    @property
    @lru_cache(maxsize=1)
    def engine(self):
        if self._engine is None:
            self._engine = create_engine(os.environ.get("DATABASE_URL", ""), echo=True)
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
