import logging
from datetime import timedelta
from io import BytesIO
from typing import Dict

import pyarrow as pa
import pyarrow.parquet as pq
import requests
from jsonschema.exceptions import ValidationError
from jsonschema.validators import validate
from sqlalchemy import Table, select

from src.configuration.model import ComponentConfiguration
from src.data.engine import engine
from src.data.storage import storage_manager
from src.runners._utils import schedule_string_to_time_delta

logger = logging.getLogger("Parquetize")


def run_parquetize(
    component_config: ComponentConfiguration,
    tables: Dict[str, Table],
):
    """
    Run the "Parquetize" process. The idea is to convert the data from the source table to a parquet file, to
    group the data by a specific column and to save the schema of the data.

    :param component_config: The component configuration
    :param tables: The tables
    :param fail_on_error: Whether to fail on error
    """
    assert (
        component_config.parquetize is not None
    ), f"Parquetize configuration is missing in the component configuration {component_config.name}"

    parquet_table = tables[component_config.parquetize_name]
    source = tables[component_config.name]

    delta = schedule_string_to_time_delta(component_config.parquetize.batch)

    with engine.connect() as connection:
        latest_parquet = connection.execute(
            parquet_table.select().order_by(parquet_table.c.end_date.desc()).limit(1)
        ).fetchone()

        latest_date = latest_parquet and latest_parquet[2]

        if latest_date is None:
            result = connection.execute(
                source.select().order_by(source.c.date.asc()).limit(1)
            ).fetchone()

            if not result:
                raise ValueError(f"No data found in the source table {source.name}")

            latest_date = result[1] - timedelta(seconds=1)

        end_date = connection.execute(
            source.select().order_by(source.c.date.desc()).limit(1)
        ).fetchone()[1]

        period_start = latest_date

        while True:
            period_end = period_start + delta

            if period_end > end_date:
                logger.info(
                    f"End of data reached, last period: {period_start} - {end_date}, should re-run later"
                )
                break

            _generate_batch(
                component_config,
                connection,
                parquet_table,
                period_end,
                period_start,
                source,
            )

            period_start = period_end

    # Now we want to group the batch themselves
    with engine.connect() as connection:
        first_unprocessed_batch = connection.execute(
            parquet_table.select().where(parquet_table.c.batch.is_(True)).limit(1)
        ).fetchone()

        last_unprocessed_batch = connection.execute(
            parquet_table.select()
            .where(parquet_table.c.batch.is_(True))
            .order_by(parquet_table.c.end_date.desc())
            .limit(1)
        ).fetchone()

        group_period = schedule_string_to_time_delta(component_config.parquetize.group)

        if first_unprocessed_batch is None:
            logger.info("All batches are processed")
            return

        start_date = first_unprocessed_batch[1]
        end_date = last_unprocessed_batch[2]

        group_start = start_date

        while True:
            group_end = group_start + group_period
            if group_end > end_date:
                logger.info(
                    f"End of data reached, last period: {start_date} - {end_date}, should re-run later"
                )
                break

            _generate_group(
                component_config,
                connection,
                parquet_table,
                group_start,
                group_end,
            )

            group_start = group_end


def _generate_group(
    component_config, connection, parquet_table, group_start, group_end
):
    # Fetch data from the database within the specified date range
    data_query = select(
        parquet_table.c.data,
        parquet_table.c.start_date,
        parquet_table.c.count,
        parquet_table.c.skipped,
        parquet_table.c.original_size,
    ).where(parquet_table.c.start_date.between(group_start, group_end))

    data_rows = connection.execute(data_query).fetchall()

    urls = [row[0] for row in data_rows]
    # Retrieve content from each data source
    datas = [BytesIO(requests.get(url).content) for url in urls]


    table = None

    for data in datas:
        if table is None:
            table = pq.read_table(data)
        else:
            table = pa.concat_tables(
                [table, pq.read_table(data)], promote=True, safe=False
            )

    output = BytesIO()
    pq.write_table(
        table,
        output,
        compression="gzip",
        use_dictionary=True,
        compression_level=9,
    )

    url = storage_manager.write(
        f"{component_config.parquetize_name}/{group_start.strftime('%Y-%m-%d_%H-%M-%S')}_to_{group_end.strftime('%Y-%m-%d_%H-%M-%S')}",
        output.getvalue(),
    )

    original_size = sum([row[4] for row in data_rows])
    compressed_size = output.getbuffer().nbytes

    connection.execute(
        parquet_table.insert().values(
            start_date=group_start,
            end_date=group_end,
            data=url,
            count=sum([row[2] for row in data_rows]),
            skipped=sum([row[3] for row in data_rows]),
            schema=component_config.parquetize.schema,
            batch=False,
            original_size=original_size,
            compressed_size=compressed_size
        )
    )

    # Delete the processed data (period and batch)
    connection.execute(
        parquet_table.delete().where(
            parquet_table.c.start_date.between(group_start, group_end)
            & parquet_table.c.batch.is_(True)
        )
    )
    connection.commit()

    # Delete files
    for url in urls:
        storage_manager.delete(url)


def _generate_batch(
    component_config, connection, parquet_table, period_end, period_start, source
):
    # Fetch data from the database within the specified date range
    data_query = select(source.c.data, source.c.date).where(
        source.c.date.between(period_start, period_end)
    )
    data_rows = connection.execute(data_query).fetchall()


    responses =[requests.get(row[0]) for row in data_rows]

    # Retrieve content from each data source
    datas = [(response.json(), row[1]) for response, row in zip(responses, data_rows)]

    validated_datas = []
    for data, date in datas:
        try:
            validate(data, component_config.parquetize.schema)
            validated_datas.append({"data": data, "date": date})
        except ValidationError as val:
            logger.warning(f"Error validating data: {val}")

    # Save the data to the parquet table
    table = pa.Table.from_pylist(validated_datas)
    output = BytesIO()
    pq.write_table(
        table,
        output,
        compression="snappy",
        use_dictionary=True,
    )

    url = storage_manager.write(
        f"{component_config.parquetize_name}/{period_start.strftime('%Y-%m-%d_%H-%M-%S')}_to_{period_end.strftime('%Y-%m-%d_%H-%M-%S')}",
        output.getvalue(),
    )

    original_size = sum([len(response.content) for response in responses])
    compressed_size = output.getbuffer().nbytes

    connection.execute(
        parquet_table.insert().values(
            start_date=period_start,
            end_date=period_end,
            data=url,
            count=len(validated_datas),
            skipped=len(data_rows) - len(validated_datas),
            schema=component_config.parquetize.schema,
            batch=True,
            original_size=original_size,
            compressed_size=compressed_size
        )
    )
    connection.commit()
