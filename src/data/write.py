import json
from datetime import datetime

from sqlalchemy import Table

from src.data.engine import connection


def write_result(table: Table, data, date: datetime):
    """
    Write the result of a harvester to the database.
    If the data already exists, it will be overwritten.
    :param table:  The table to write to
    :param data:  The data to write
    :param date:  The date of the data
    """

    # Check if data is already in the database
    same_data_row = connection().execute(table.select().where(table.c.data == data)).fetchone()

    if same_data_row is not None:
        # Insert with copy_id
        connection().execute(table.insert().values(date=date, copy_id=same_data_row.id))
    else:
        # Insert without copy_id
        connection().execute(table.insert().values(date=date, data=data))

    connection().commit()
