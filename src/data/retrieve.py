import json
from dataclasses import dataclass
from datetime import datetime
from typing import Union, List, Optional

from sqlalchemy import Table, select
from sqlalchemy.orm import aliased
from sqlalchemy.sql.functions import coalesce

from src.data.engine import engine
from src.data.storage import storage_manager


@dataclass
class Data:
    date: datetime
    _url: str
    _data_type: str = None

    @property
    def data(self) -> Union[str, bytes]:
        bytes_data = storage_manager.read(self._url)

        if self._data_type == "json":
            return json.loads(bytes_data)
        elif self._data_type == "text":
            return bytes_data.decode("utf-8")

        return bytes_data


def data_result(func) -> Optional[Union[Data, List[Data]]]:
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)

        if result is None:
            return None

        # If the result is a single row, return a single Data object
        if not isinstance(result, list):
            return Data(date=result.date, _url=result.data)

        return [
            Data(date=row.date, _url=row.data, _data_type=row.type) for row in result
        ]

    return wrapper


def _(statement):
    with engine.connect() as connection:
        return connection.execute(statement)


def base_query(table: Table, with_null: bool = False):
    """
    Returns a base query for a table. But replace the value of the date column
    when it is None with the value of the row with the id matching the copy_id.
    :param table: The table
    :param with_null: Whether to include rows with null data
    :return: The base query to use for all subsequent queries
    """

    t2 = aliased(table)

    query = select(
        table.c.id,
        table.c.date,
        coalesce(t2.c.data, table.c.data).label("data"),
        table.c.type,
    )

    if not with_null:
        query = query.where((table.c.copy_id.isnot(None)) | (table.c.hash.isnot(None)))

    query = query.select_from(table).outerjoin(t2, table.c.copy_id == t2.c.id)

    return query


@data_result
def retrieve_latest_row(table: Table, with_null: bool = False) -> Data:
    """
    Get the latest row from a table.
    :param table: The table
    :param with_null: Whether to include rows with null data
    :return: The latest row
    """

    return _(
        base_query(table, with_null=with_null).order_by(table.c.date.desc()).limit(1)
    ).fetchone()


@data_result
def retrieve_first_row(table: Table) -> Data:
    """
    Get the first row from a table.
    :param table: The table
    :return: The first row
    """
    return _(base_query(table).order_by(table.c.date.asc()).limit(1)).fetchone()


@data_result
def retrieve_after_datetime(table: Table, date: datetime, limit: int) -> List[Data]:
    return _(
        base_query(table)
        .where(table.c.date > date)
        .order_by(table.c.date.desc())
        .limit(limit)
    ).fetchall()


@data_result
def retrieve_before_datetime(table: Table, date: datetime, limit: int) -> List[Data]:
    return _(
        base_query(table)
        .where(table.c.date < date)
        .order_by(table.c.date.desc())
        .limit(limit)
    ).fetchall()


@data_result
def retrieve_between_datetime(
    table: Table, start_date: datetime, end_date: datetime, limit: int
) -> List[Data]:
    if start_date is None:
        return _(
            base_query(table)
            .where(table.c.date < end_date)
            .order_by(table.c.date.asc())
            .limit(limit)
        ).fetchall()
    elif end_date is None:
        return _(
            base_query(table)
            .where(table.c.date > start_date)
            .order_by(table.c.date.asc())
            .limit(limit)
        ).fetchall()
    else:
        return _(
            base_query(table)
            .where(table.c.date > start_date)
            .where(table.c.date < end_date)
            .order_by(table.c.date.asc())
            .limit(limit)
        ).fetchall()


@data_result
def retrieve_latest_rows_before_datetime(
    table: Table, date: datetime, limit: int
) -> List[Data]:
    return _(
        base_query(table)
        .where(table.c.date < date)
        .order_by(table.c.date.desc())
        .limit(limit)
    ).fetchall()
