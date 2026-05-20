"""WKB-per-row baseline. One row per (entity, timestamp); geometry as WKB.

This is the GeoParquet-style "current practice" comparison. We implement
WKB serialization in pure Python so the prototype has no shapely
dependency."""

from __future__ import annotations

import struct

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq


# ---------------------------------------------------------------------------
# Minimal WKB encoder (little-endian, no Z/M, polygon and point only)
# ---------------------------------------------------------------------------

WKB_POINT = 1
WKB_POLYGON = 3


def encode_point_xy(x: float, y: float) -> bytes:
    return struct.pack("<BIdd", 1, WKB_POINT, x, y)


def encode_point_xyz(x: float, y: float, z: float) -> bytes:
    # WKB POINT Z, geometry type = 1001
    return struct.pack("<BIddd", 1, 1001, x, y, z)


def encode_polygon(rings: list[list[tuple[float, float]]]) -> bytes:
    parts = [struct.pack("<BII", 1, WKB_POLYGON, len(rings))]
    for ring in rings:
        # ensure ring closure
        closed = list(ring)
        if closed and closed[0] != closed[-1]:
            closed.append(closed[0])
        parts.append(struct.pack("<I", len(closed)))
        for x, y in closed:
            parts.append(struct.pack("<dd", x, y))
    return b"".join(parts)


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def polygon_schema() -> pa.Schema:
    return pa.schema([
        pa.field("entity_id", pa.int64()),
        pa.field("t", pa.timestamp("ms")),
        pa.field("geom_wkb", pa.binary()),
    ])


def pointcloud_schema() -> pa.Schema:
    return pa.schema([
        pa.field("entity_id", pa.int64()),
        pa.field("t", pa.timestamp("ms")),
        pa.field("intensity", pa.float32()),
        pa.field("classification", pa.int8()),
        pa.field("geom_wkb", pa.binary()),
    ])


def write_polygon_workload(workload, path: str, row_group_size: int = 50_000) -> None:
    eids, ts, wkbs = [], [], []
    for ent in workload.entities:
        for frame in ent.frames:
            eids.append(ent.entity_id)
            ts.append(frame.t)
            wkbs.append(encode_polygon(frame.rings))
    table = pa.table({
        "entity_id": pa.array(eids, pa.int64()),
        "t": pa.array(ts, pa.timestamp("ms")),
        "geom_wkb": pa.array(wkbs, pa.binary()),
    }, schema=polygon_schema())
    pq.write_table(table, path, compression="snappy", row_group_size=row_group_size)


def write_pointcloud_workload(workload, path: str, row_group_size: int = 200_000) -> None:
    eids, ts, intens, cls, wkbs = [], [], [], [], []
    for ent in workload.entities:
        for frame in ent.frames:
            n = frame.xyz.shape[0]
            x = frame.xyz[:, 0]; y = frame.xyz[:, 1]; z = frame.xyz[:, 2]
            for i in range(n):
                eids.append(ent.entity_id)
                ts.append(frame.t)
                intens.append(float(frame.intensity[i]))
                cls.append(int(frame.classification[i]))
                wkbs.append(encode_point_xyz(float(x[i]), float(y[i]), float(z[i])))
    table = pa.table({
        "entity_id": pa.array(eids, pa.int64()),
        "t": pa.array(ts, pa.timestamp("ms")),
        "intensity": pa.array(intens, pa.float32()),
        "classification": pa.array(cls, pa.int8()),
        "geom_wkb": pa.array(wkbs, pa.binary()),
    }, schema=pointcloud_schema())
    pq.write_table(table, path, compression="snappy", row_group_size=row_group_size)
