import hashlib
import json
from datetime import datetime

from sqlalchemy import Table

from src.configuration.model import ComponentConfiguration
from src.data.engine import engine
from src.data.storage import storage_manager


def write_result(
    configuration: ComponentConfiguration, table: Table, data, date: datetime
):
    """
    Write the result of a harvester to the database.
    If the data already exists, it will be overwritten.
    :param configuration: The configuration of the component
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

    if data_bytes is None:
        md5_digest = None
    else:
        md5_digest = hashlib.md5(data_bytes).hexdigest()

    with engine.connect() as connection:
        # Upload data to storage
        url = storage_manager.write(
            f"{configuration.name}/{date.strftime('%Y-%m-%d_%H-%M-%S')}",
            data_bytes,
        )
        # Insert data to database
        connection.execute(
            table.insert().values(
                date=date, data=url, hash=md5_digest, type=configuration.data_type
            )
        )

    connection.commit()
