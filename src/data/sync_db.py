from itertools import chain
from typing import Dict

from sqlalchemy import MetaData
from sqlalchemy import Table

from src.configuration.model import ComponentsConfiguration
from src.data.engine import lazy_engine
from src.data.table import load_table_from_configuration


def sync_db_from_configuration(
    components_configuration: ComponentsConfiguration,
) -> Dict[str, Table]:
    """
    Sync the database from the components configuration.
    :param components_configuration: The components configuration
    """
    metadata_obj = MetaData()

    tables = {}

    for name, component_configuration in chain(
        components_configuration.harvesters.items(),
        components_configuration.collectors.items(),
    ):
        table = load_table_from_configuration(component_configuration, metadata_obj)
        tables[name] = table

    engine = lazy_engine.engine
    metadata_obj.create_all(engine)
    lazy_engine.reset()

    return tables
