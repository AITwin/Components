import os

from sqlalchemy import (
    BINARY,
    Column,
    TEXT,
    UniqueConstraint,
    TIMESTAMP,
    INTEGER,
    Table,
    MetaData,
    JSON,
)
from sqlalchemy.dialects.postgresql import JSONB, BYTEA

from src.configuration.model import ComponentConfiguration


def get_data_type_from_configuration(component_configuration: ComponentConfiguration):
    is_postgres = "postgres" in os.environ.get("DATABASE_URL", "")

    if component_configuration.data_type == "binary":
        if is_postgres:
            return BYTEA
        else:
            return BINARY
    elif component_configuration.data_type == "json":
        if is_postgres:
            return JSONB
        else:
            return JSON
    elif component_configuration.data_type == "text":
        return TEXT

    raise ValueError(f"Unknown data type {component_configuration.data_type}")


def load_table_from_configuration(
    component_configuration: ComponentConfiguration, metadata_obj: MetaData
):
    return Table(
        component_configuration.name,
        metadata_obj,
        Column("id", INTEGER, primary_key=True, autoincrement=True),
        Column("date", TIMESTAMP),
        Column(
            "data",
            get_data_type_from_configuration(component_configuration),
            nullable=True,
        ),
        Column("copy_id", INTEGER),
        UniqueConstraint("date"),
        UniqueConstraint("data"),
    )
