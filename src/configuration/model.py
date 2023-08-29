from dataclasses import dataclass
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
    storage_date: Optional[bool] = False

    def __hash__(self):
        return hash(self.name)


@dataclass
class ComponentsConfiguration:
    handlers: Dict[str, ComponentConfiguration]
    harvesters: Dict[str, ComponentConfiguration]
    collectors: Dict[str, ComponentConfiguration]
