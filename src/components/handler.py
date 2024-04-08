import abc
from typing import Type, Dict



class Handler(abc.ABC):
    def __init__(self, tables: Dict[str, "ComponentConfiguration"]):
        self._tables = tables

    def get_table_by_name(self, name: str) -> "ComponentConfiguration":
        return self._tables[name]

    @abc.abstractmethod
    def run(self, **kwargs):
        pass


HandlerClass = Type[Handler]
