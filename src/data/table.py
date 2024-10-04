from sqlalchemy import (
    Column,
    UniqueConstraint,
    TIMESTAMP,
    INTEGER,
    Table,
    MetaData,
    VARCHAR,
    Index,
    BOOLEAN,
)
from sqlalchemy.dialects.postgresql import JSONB


def load_simple_table_from_configuration(table_name: str, metadata_obj: MetaData):
    """
    Load/Create a simple table from a component configuration.

    A simple table is a table that contains an id, a date, a data column, a type column, a hash column, and a copy_id column.
    The copy_id column is used to prevent storing the same data multiple times, instead, it stores the id of the row that contains the same data,
    leveraging the unique constraint on the hash column.

    @param table_name: The table name
    @param metadata_obj: The metadata object
    @return: The table
    """
    return Table(
        table_name,
        metadata_obj,
        Column("id", INTEGER, primary_key=True, autoincrement=True),
        Column("date", TIMESTAMP, nullable=False),
        Column("data", VARCHAR(512), nullable=True),
        Column("type", VARCHAR(24), nullable=True),
        Column("hash", VARCHAR(32), nullable=True),
        Column("copy_id", INTEGER, nullable=True),
        UniqueConstraint("date"),
        UniqueConstraint("hash"),
        Index("date_index", "date"),
    )


def load_parquetize_table_from_configuration(table_name: str, metadata_obj: MetaData):
    """
    Load/Create a table for the parquetize process.

    A table for the parquetize process is a table that contains an id, a start_date, an end_date, a count,
    and a data column. The data column contains the parquet file.

    :param table_name: The table name
    :param metadata_obj: The metadata object
    :return: The table
    """

    return Table(
        table_name,
        metadata_obj,
        Column("id", INTEGER, primary_key=True, autoincrement=True),
        Column("start_date", TIMESTAMP, nullable=False),
        Column("end_date", TIMESTAMP, nullable=False),
        Column("count", INTEGER, nullable=False),
        Column("skipped", INTEGER, nullable=False),
        Column("original_size", INTEGER, nullable=False),
        Column("compressed_size", INTEGER, nullable=False),
        Column("schema", JSONB, nullable=False),
        Column(
            "data",
            VARCHAR(512),
            nullable=True,
        ),
        Column("batch", BOOLEAN, nullable=False),
        Index(f"{table_name}_start_date_index", "start_date"),
        Index(f"{table_name}_end_date_index", "end_date"),
        Index(f"{table_name}_start_end_date_index", "start_date", "end_date"),
    )
