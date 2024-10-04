from dataclasses import dataclass
from typing import List, Optional, Dict, Self, Any

from src.components import ComponentClass


@dataclass
class ComponentParquetizeConfig:
    batch: str
    group: str
    schema: Dict[str, Any]


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
    parquetize: Optional[ComponentParquetizeConfig] =None
    source_range_strict: bool = True
    multiple_results: bool = False
    query_parameters: Optional[Dict[str, str]] = None

    def __hash__(self):
        return hash(self.name)

    @property
    def parquetize_name(self):
        return f"{self.name}_parquetize"

@dataclass
class ComponentsConfiguration:
    handlers: Dict[str, ComponentConfiguration]
    harvesters: Dict[str, ComponentConfiguration]
    collectors: Dict[str, ComponentConfiguration]
    parquetize: Dict[str, ComponentConfiguration]
