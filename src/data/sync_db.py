from itertools import chain
from typing import Dict

from sqlalchemy import MetaData, Table

from src.configuration.model import ComponentsConfiguration
from src.data.engine import engine
from src.data.table import (
    load_simple_table_from_configuration,
    load_parquetize_table_from_configuration,
)


def sync_db_from_configuration(
    configuration: ComponentsConfiguration,
) -> Dict[str, Table]:
    """
    Sync the database from the components' configuration.
    :param configuration: The components configuration
    :return: The tables
    """

    metadata_obj = MetaData()

    tables = {}

    for name, component in chain(
        configuration.harvesters.items(),
        configuration.collectors.items(),
    ):
        tables[name] = load_simple_table_from_configuration(
            component.name, metadata_obj
        )

        if component.parquetize:
            tables[component.parquetize_name] = load_parquetize_table_from_configuration(
                component.parquetize_name, metadata_obj
            )

    metadata_obj.create_all(engine)

    return tables
