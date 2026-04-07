import logging
import multiprocessing
import os
import tempfile
import zipfile

from src.components import Harvester

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 1800


def _convert(gtfs_path, output_path):
    """Run conversion in a subprocess so it can be hard-killed on timeout."""
    from gtfs_parquet import parse_gtfs, write_parquet

    feed = parse_gtfs(gtfs_path)
    write_parquet(feed, output_path)


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
