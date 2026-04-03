import io
import logging
import tempfile
import os
import zipfile

from gtfs_parquet import parse_gtfs, write_parquet

from src.components import Harvester

logger = logging.getLogger(__name__)


class GTFSParquetHarvester(Harvester):
    """Generic harvester that converts a GTFS zip file to a Parquet zip archive.

    Uses the gtfs-parquet library for conversion, producing strongly-typed Parquet
    files with zstd compression. This yields significant size reductions (40-75%)
    and enables efficient columnar reads with near-zero RAM overhead via Polars.
    """

    def run(self, source):
        gtfs_bytes = source.data

        with tempfile.TemporaryDirectory() as tmpdir:
            # Write source GTFS zip to a temp file so gtfs-parquet can read it
            gtfs_path = os.path.join(tmpdir, "gtfs.zip")
            with open(gtfs_path, "wb") as f:
                f.write(gtfs_bytes)

            try:
                feed = parse_gtfs(gtfs_path)
            except zipfile.BadZipFile:
                logger.warning("Source data is not a valid zip file, skipping")
                return None

            output_path = os.path.join(tmpdir, "gtfs.parquet.zip")
            write_parquet(feed, output_path)

            with open(output_path, "rb") as f:
                return f.read()