import logging
import multiprocessing
import os
import shutil
import tempfile
import zipfile

from src.components import Harvester

logger = logging.getLogger(__name__)

# The De Lijn feed takes 10 to 20 minutes on the harvester VM's two cores and
# went past 30 minutes on 2026-09-22 while a backfill shared the CPU.
TIMEOUT_SECONDS = 7200

# Above this CSV size a table is converted with the bounded-memory path.
LARGE_TABLE_BYTES = 200 * 1024 * 1024
BATCH_ROWS = 250_000
BUCKETS = 32


def _convert(gtfs_path, output_path):
    """Run conversion in a subprocess so it can be hard-killed on timeout.

    Small tables go through the gtfs-parquet library as before. A large one
    (De Lijn's stop_times.txt is 1.8 GB of CSV) is converted with
    `_write_large_table`, which never holds the table whole: parsing the feed
    eagerly, even one table at a time, got the process OOM-killed on the 8 GB
    harvester VM every night from 2026-08-29 on, freezing the endpoint on the
    last good file. Polars' lazy sort was tried first and still peaked above
    6 GB on that table.
    """
    from gtfs_parquet.parse import parse_gtfs_file
    from gtfs_parquet.schema import ALL_SCHEMAS
    from gtfs_parquet.write import _prepare_table

    with zipfile.ZipFile(gtfs_path) as source, tempfile.TemporaryDirectory() as tmpdir, \
            zipfile.ZipFile(output_path, "w", zipfile.ZIP_STORED) as target:
        infos = {info.filename: info for info in source.infolist()}
        for table_name, schema in ALL_SCHEMAS.items():
            info = infos.get(schema.file_name)
            if info is None:
                continue
            csv_path = source.extract(info, tmpdir)
            if info.file_size <= LARGE_TABLE_BYTES:
                df = parse_gtfs_file(csv_path, schema.file_name)
                target.writestr(f"{table_name}.parquet", _prepare_table(table_name, df, "zstd", 9))
                del df
            else:
                parquet_path = os.path.join(tmpdir, f"{table_name}.parquet")
                _write_large_table(csv_path, schema, parquet_path, os.path.join(tmpdir, "buckets"))
                target.write(parquet_path, f"{table_name}.parquet")
                os.remove(parquet_path)
            os.remove(csv_path)


def _write_large_table(csv_path, schema, parquet_path, work_dir):
    """Type, sort and write a table too large to hold in memory.

    An external sort. A first pass reads only the first sort key and picks
    quantile boundaries that split it into `BUCKETS` ranges. The CSV is then
    read in batches; each batch is typed with the library's own expressions
    and its rows are written to the bucket their key falls in. Each bucket is
    sorted on the full sort keys, written with polars, and the sorted buckets
    are streamed into the final file in range order, which yields the same
    globally sorted parquet as sorting the whole table (the order matters:
    hashing keys into buckets instead gave a file 2.4 times larger, since
    neighbouring trips share most of their values). The final file is
    written by polars, not pyarrow: pyarrow's writer caps dictionary pages at
    1 MB and fell back to plain encoding on the big string columns. Peak
    memory is the key column, then one batch plus one bucket.
    """
    import polars as pl
    from gtfs_parquet.parse import _apply_schema

    os.makedirs(work_dir, exist_ok=True)
    lazy = pl.scan_csv(csv_path, infer_schema=False, truncate_ragged_lines=True)
    columns = [c.strip() for c in lazy.collect_schema().names()]
    lazy = lazy.rename(dict(zip(lazy.collect_schema().names(), columns)))
    keys = [k for k in schema.sort_keys if k in columns]

    bounds = []
    if keys:
        key_values = _collect_streaming(lazy.select(keys[0])).get_column(keys[0]).sort()
        bounds = [key_values[i * key_values.len() // BUCKETS] for i in range(1, BUCKETS)]
        del key_values
    bucket_of = pl.sum_horizontal([(pl.col(keys[0]) >= pl.lit(b)).cast(pl.UInt8) for b in bounds]) if bounds else pl.lit(0)

    reader = pl.read_csv_batched(csv_path, infer_schema_length=0, truncate_ragged_lines=True,
                                 batch_size=BATCH_ROWS, low_memory=True)
    part = 0
    while True:
        batches = reader.next_batches(1)
        if not batches:
            break
        raw = batches[0].rename({c: c.strip() for c in batches[0].columns})
        df = _apply_schema(raw.with_columns(bucket_of.alias("__bucket")), schema)
        for (bucket,), rows in df.partition_by("__bucket", as_dict=True).items():
            rows.drop("__bucket").write_parquet(os.path.join(work_dir, f"{bucket}_{part}.parquet"))
        part += 1
        del df, raw, batches

    try:
        sorted_files = []
        for bucket in range(BUCKETS):
            files = sorted(f for f in os.listdir(work_dir) if f.startswith(f"{bucket}_"))
            if not files:
                continue
            df = pl.concat([pl.read_parquet(os.path.join(work_dir, f)) for f in files])
            if keys:
                df = df.sort(keys)
            sorted_path = os.path.join(work_dir, f"sorted_{bucket:03d}.parquet")
            df.write_parquet(sorted_path, compression="zstd", compression_level=9)
            sorted_files.append(sorted_path)
            del df
            for f in files:
                os.remove(os.path.join(work_dir, f))
        pl.scan_parquet(sorted_files).sink_parquet(parquet_path, compression="zstd", compression_level=9)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _collect_streaming(lazy):
    """Collect with the streaming engine on both the polars the VM runs (1.13) and current ones."""
    try:
        return lazy.collect(engine="streaming")
    except (TypeError, ValueError):  # 1.13 rejects the engine name with ValueError
        return lazy.collect(streaming=True)


class GTFSParquetHarvester(Harvester):
    """Generic harvester that converts a GTFS zip file to a Parquet zip archive.

    Uses the gtfs-parquet library's schemas, producing strongly-typed Parquet
    files with zstd compression. This yields significant size reductions (40-75%)
    and enables efficient columnar reads with near-zero RAM overhead via Polars.
    """

    def run(self, source):
        gtfs_bytes = source.data

        with tempfile.TemporaryDirectory() as tmpdir:
            gtfs_path = os.path.join(tmpdir, "gtfs.zip")
            with open(gtfs_path, "wb") as f:
                f.write(gtfs_bytes)
            del gtfs_bytes

            try:
                zipfile.ZipFile(gtfs_path).close()
            except zipfile.BadZipFile:
                logger.warning("Source data is not a valid zip file, skipping")
                return None

            output_path = os.path.join(tmpdir, "gtfs.parquet.zip")

            proc = multiprocessing.Process(target=_convert, args=(gtfs_path, output_path))
            proc.start()
            proc.join(timeout=TIMEOUT_SECONDS)

            if proc.is_alive():
                proc.kill()
                proc.join()
                logger.warning("GTFS to Parquet conversion timed out after %ds, skipping", TIMEOUT_SECONDS)
                return None

            if proc.exitcode != 0:
                logger.warning("GTFS to Parquet conversion failed (exit code %d), skipping", proc.exitcode)
                return None

            with open(output_path, "rb") as f:
                return f.read()
