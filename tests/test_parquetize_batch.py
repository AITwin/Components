"""A batch over snapshots where the harvester produced nothing (an empty blob)."""
import json
import os
import sys
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

from sqlalchemy import JSON, Column, DateTime, Integer, MetaData, String, Table

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FILE_STORAGE_DIRECTORY", "/tmp/storage")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import importlib  # noqa: E402

run_parquetize = importlib.import_module("src.runners.run_parquetize")

COLLECTION = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"uuid": "u", "lineId": 7, "tripId": None},
     "geometry": {"type": "Point", "coordinates": [4.35, 50.85]}}]}


class EmptySnapshots(unittest.TestCase):
    def test_empty_blobs_are_skipped_not_fatal(self):
        blobs = {"a": json.dumps(COLLECTION).encode(), "b": b""}
        rows = [("a", datetime(2026, 9, 30, 0, 1)), ("b", datetime(2026, 9, 30, 0, 2))]
        connection = mock.MagicMock()
        connection.execute.return_value.fetchall.return_value = rows
        config = SimpleNamespace(
            name="stib_vehicle_trip", parquetize_name="stib_vehicle_trip_parquetize",
            parquetize=SimpleNamespace(schema={"type": "array"}, batch="1h"))
        written = {}
        with mock.patch.object(run_parquetize, "fetch_data", lambda row: (blobs[row[0]], row[1])), \
                mock.patch.object(run_parquetize.storage_manager, "write",
                                  lambda name, data: written.setdefault(name, data) and name):
            meta = MetaData()
            source = Table("stib_vehicle_trip", meta, Column("date", DateTime), Column("data", String))
            parquet = Table("stib_vehicle_trip_parquetize", meta, *(Column(c, t) for c, t in (
                ("start_date", DateTime), ("end_date", DateTime), ("data", String), ("count", Integer),
                ("skipped", Integer), ("schema", JSON), ("aggregation", String),
                ("original_size", Integer), ("compressed_size", Integer))))
            run_parquetize._generate_batch(config, connection, parquet,
                                           datetime(2026, 9, 30, 1), datetime(2026, 9, 30), source)
        self.assertEqual(len(written), 1)
        values = connection.execute.call_args_list[-1].args[0].compile().params
        self.assertEqual((values["count"], values["skipped"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
