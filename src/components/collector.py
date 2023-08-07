import abc
from typing import Type


class Collector(abc.ABC):
    def __init__(self, **kwargs):
        self.settings = kwargs

    @abc.abstractmethod
    def run(self):
        pass


CollectorClass = Type[Collector]
