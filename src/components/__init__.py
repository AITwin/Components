from typing import Union

from .collector import Collector, CollectorClass
from .handler import Handler, HandlerClass
from .harvester import Harvester, HarvesterClass

ComponentClass = Union[CollectorClass, HandlerClass, HarvesterClass]
