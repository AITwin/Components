from dataclasses import dataclass
from functools import lru_cache
from typing import List, Optional, Dict, Self

from src.components import ComponentClass


@dataclass
class ComponentConfiguration:
    name: str
    data_type: str
    data_format: str

    dependencies: List[Self]
    dependencies_limit: Optional[List[int]]
    component: ComponentClass
    schedule: Optional[str]
    source: Optional[Self]
    source_range: Optional[str]
    source_range_strict: bool = True
    multiple_results: bool = False
    query_parameters: Optional[Dict[str, str]] = None

    def __hash__(self):
        return hash(self.name)


class ComponentsConfiguration:
    handlers: Dict[str, ComponentConfiguration]
    harvesters: Dict[str, ComponentConfiguration]
    collectors: Dict[str, ComponentConfiguration]

    def __init__(self,collectors: Dict[str, ComponentConfiguration], harvesters: Dict[str, ComponentConfiguration], handlers: Dict[str, ComponentConfiguration]):
        self.collectors = collectors
        self.harvesters = harvesters
        self.handlers = handlers

        self.components = {
            **collectors,
            **harvesters,
            **handlers
        }
