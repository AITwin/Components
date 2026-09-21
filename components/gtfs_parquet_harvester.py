import logging
import multiprocessing
import os
import tempfile
import zipfile

from src.components import Harvester

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 1800


def _convert(gtfs_path, output_path):
    """Run conversion in a subprocess so it can be hard-killed on timeout.

    One table at a time: parse it, write it into the archive, drop it. Parsing
    the whole feed first and writing it afterwards held every table in memory
    at once, and the De Lijn feed (stop_times alone is several GB as typed
    frames) got the process OOM-killed on the 8 GB harvester VM every night
    from 2026-08-29 on, leaving the endpoint frozen on the last good file.
    """
    from gtfs_parquet.parse import parse_gtfs_file
    from gtfs_parquet.schema import ALL_SCHEMAS
    from gtfs_parquet.write import _prepare_table

    with zipfile.ZipFile(gtfs_path) as source, zipfile.ZipFile(output_path, "w", zipfile.ZIP_STORED) as target:
        names = set(source.namelist())
        for table_name, schema in ALL_SCHEMAS.items():
            if schema.file_name not in names:
                continue
            with tempfile.TemporaryDirectory() as tmpdir:
                csv_path = source.extract(schema.file_name, tmpdir)
                df = parse_gtfs_file(csv_path, schema.file_name)
            target.writestr(f"{table_name}.parquet", _prepare_table(table_name, df, "zstd", 9))
            del df


class GTFSParquetHarvester(Harvester):
    """Generic harvester that converts a GTFS zip file to a Parquet zip archive.

    Uses the gtfs-parquet library for conversion, producing strongly-typed Parquet
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
