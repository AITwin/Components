import abc
from typing import Type, Dict

from sqlalchemy import Table


class Handler(abc.ABC):
    def __init__(self, tables: Dict[str, Table]):
        self._tables = tables

    def get_table_by_name(self, name: str) -> Table:
        return self._tables[name]

    @abc.abstractmethod
    def run(self, **kwargs):
        pass


HandlerClass = Type[Handler]
