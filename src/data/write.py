import hashlib
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

    if data is str:
        data_bytes = data.encode("utf-8")
    elif isinstance(data, dict) or isinstance(data, list):
        data_bytes = json.dumps(data).encode("utf-8")
    else:
        data_bytes = data

    md5_digest = hashlib.md5(data_bytes).hexdigest()

    # Check if data is already in the database
    same_data_row = (
        connection().execute(table.select().where(table.c.hash == md5_digest)).fetchone()
    )

    if same_data_row is not None:
        # Insert with copy_id
        connection().execute(table.insert().values(date=date, copy_id=same_data_row.id))
    else:
        # Insert without copy_id
        connection().execute(table.insert().values(date=date, data=data, hash=md5_digest))

    connection().commit()
