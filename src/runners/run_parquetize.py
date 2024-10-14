import logging
import time
from datetime import timedelta
from io import BytesIO
from typing import Dict

import pyarrow as pa
import pyarrow.parquet as pq
import requests
from jsonschema.exceptions import ValidationError
from jsonschema.validators import validate
from sqlalchemy import Table, select, column

from src.configuration.model import ComponentConfiguration
from src.data.engine import engine
from src.data.storage import storage_manager
from src.runners._utils import (
    schedule_string_to_time_delta,
    round_datetime_to_previous_delta,
)

logger = logging.getLogger("Parquetize")


def run_parquetize_on_schedule(
    component_config: ComponentConfiguration,
    tables: Dict[str, Table],
):
    logger.info("Running parquetize on schedule")

    while True:
        logger.debug(f"Running parquetize {component_config.name}")
        try:
            run_parquetize(component_config, tables)
        except Exception as e:
            logger.exception(f"Parquetize {component_config.name} failed: {e}")
            time.sleep(60)

        time.sleep(60)


def run_parquetize(
    component_config: ComponentConfiguration,
    tables: Dict[str, Table],
):
    """
    Run the "Parquetize" process. The idea is to convert the data from the source table to a parquet file, to
    group the data by a specific column and to save the schema of the data.

    :param component_config: The component configuration
    :param tables: The tables
    """

    parquetize_config = component_config.parquetize

    assert (
        parquetize_config is not None
    ), f"Parquetize configuration is missing in the component configuration {component_config.name}"

    parquet_table = tables[component_config.parquetize_name]
    source = tables[component_config.name]

    logger.info(f"Running parquetize {component_config.name}")

    with engine.connect() as connection:
        delta = schedule_string_to_time_delta(parquetize_config.batch)

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
            logger.info(f"Processing period {period_start} - {period_start + delta} for batching")
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

    with engine.connect() as connection:
        for previous_group, group in zip(
            [parquetize_config.batch] + parquetize_config.groups[:-1],
            parquetize_config.groups,
        ):
            logger.info(f"Processing group {group}")
            # Now we want to group the batch themselves
            first_unprocessed_batch = connection.execute(
                parquet_table.select()
                .where((column("aggregation") == previous_group))
                .limit(1)
            ).fetchone()

            last_unprocessed_batch = connection.execute(
                parquet_table.select()
                .where((column("aggregation") == previous_group))
                .order_by(parquet_table.c.end_date.desc())
                .limit(1)
            ).fetchone()

            if first_unprocessed_batch is None:
                logger.info(f"All batches are processed for this group {group}")
                continue

            group_time_delta = schedule_string_to_time_delta(group)
            start_date = round_datetime_to_previous_delta(
                first_unprocessed_batch[1], group_time_delta
            )
            end_date = last_unprocessed_batch[2]

            group_start = start_date

            while True:
                logger.info(f"Processing group {group} {group_start} - {group_start + group_time_delta}")
                group_end = group_start + group_time_delta
                if group_end > end_date:
                    logger.info(
                        f"End of data reached, last period: {start_date} - {end_date}, should re-run later"
                    )
                    break

                _generate_group(
                    component_config.name,
                    previous_group,
                    group,
                    parquetize_config.schema,
                    connection,
                    parquet_table,
                    group_start,
                    group_end,
                )

                group_start = group_end


def _generate_group(
    parquetize_table: str,
    previous_group: str,
    group: str,
    schema: dict,
    connection,
    parquet_table,
    group_start,
    group_end,
):
    # Fetch data from the database within the specified date range
    data_query = select(
        parquet_table.c.data,
        parquet_table.c.start_date,
        parquet_table.c.count,
        parquet_table.c.skipped,
        parquet_table.c.original_size,
    ).where(
        parquet_table.c.start_date.between(group_start, group_end)
        & (column("aggregation") == previous_group)
    ).order_by(parquet_table.c.start_date.asc())

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
        f"{parquetize_table}/{group_start.strftime('%Y-%m-%d_%H-%M-%S')}_to_{group_end.strftime('%Y-%m-%d_%H-%M-%S')}.parquet",
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
            schema=schema,
            aggregation=group,
            original_size=original_size,
            compressed_size=compressed_size,
        )
    )

    # Delete the processed data (period and batch)
    connection.execute(
        parquet_table.delete().where(
            parquet_table.c.start_date.between(group_start, group_end)
            & (column("aggregation") == previous_group)
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

    responses = [requests.get(row[0]) for row in data_rows]

    # Retrieve content from each data source
    datas = [(response.json(), row[1]) for response, row in zip(responses, data_rows)]

    validated_datas = []
    for data, date in datas:
        try:
            validate(data, component_config.parquetize.schema)
            new_data = []
            for item in data:
                new_item = item.copy()
                new_item["lineId"] = str(item["lineId"])
                new_data.append(new_item)
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
        f"{component_config.parquetize_name}/{period_start.strftime('%Y-%m-%d_%H-%M-%S')}_to_{period_end.strftime('%Y-%m-%d_%H-%M-%S')}.parquet",
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
            aggregation=component_config.parquetize.batch,
            original_size=original_size,
            compressed_size=compressed_size,
        )
    )
    connection.commit()
