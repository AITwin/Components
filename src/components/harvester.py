import abc
from typing import Type


class Harvester(abc.ABC):
    @abc.abstractmethod
    def run(self, *args, **kwargs):
        pass


HarvesterClass = Type[Harvester]
