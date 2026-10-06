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


class DayGroupBoundary(unittest.TestCase):
    def test_batch_starting_at_midnight_stays_out_of_the_previous_day(self):
        import io

        import pyarrow as pa
        import pyarrow.parquet as pq
        from sqlalchemy import create_engine, select

        meta = MetaData()
        parquet = Table("stib_vehicle_trip_parquetize", meta, Column("id", Integer, primary_key=True),
                        *(Column(c, t) for c, t in (
                            ("start_date", DateTime), ("end_date", DateTime), ("data", String),
                            ("count", Integer), ("skipped", Integer), ("schema", JSON),
                            ("aggregation", String), ("original_size", Integer),
                            ("compressed_size", Integer))))
        engine = create_engine("sqlite://")
        meta.create_all(engine)
        starts = {"23": datetime(2026, 10, 5, 23), "00": datetime(2026, 10, 6)}
        blobs, written = {}, {}
        for name, start in starts.items():
            out = io.BytesIO()
            pq.write_table(pa.Table.from_pylist([{"lineId": "7", "date": start}]), out)
            blobs[name] = out.getvalue()
        with engine.connect() as connection:
            for name, start in starts.items():
                connection.execute(parquet.insert().values(
                    start_date=start, end_date=start.replace(hour=(start.hour + 1) % 24), data=name,
                    count=1, skipped=0, aggregation="1h", original_size=1, compressed_size=1))
            with mock.patch.object(run_parquetize.storage_manager, "read", lambda url: blobs[url]), \
                    mock.patch.object(run_parquetize.storage_manager, "write",
                                      lambda name, data: written.setdefault(name, data) and name), \
                    mock.patch.object(run_parquetize.storage_manager, "delete", lambda url: None):
                run_parquetize._generate_group(
                    "stib_vehicle_trip_parquetize", SimpleNamespace(group="1h"),
                    SimpleNamespace(group="1d", keys=None), {}, connection, parquet,
                    datetime(2026, 10, 5), datetime(2026, 10, 6))
            left = connection.execute(select(parquet.c.aggregation, parquet.c.data)).fetchall()
        day = pq.read_table(io.BytesIO(next(iter(written.values())))).to_pylist()
        self.assertEqual([r["date"] for r in day], [datetime(2026, 10, 5, 23)])
        self.assertIn(("1h", "00"), left)


if __name__ == "__main__":
    unittest.main()
