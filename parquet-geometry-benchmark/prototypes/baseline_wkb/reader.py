"""WKB baseline reader."""

from __future__ import annotations

import struct

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq


def _decode_polygon(buf: bytes) -> list[list[tuple[float, float]]]:
    byte_order = buf[0]
    fmt_prefix = "<" if byte_order == 1 else ">"
    (_,) = struct.unpack_from(fmt_prefix + "I", buf, 1)  # type
    (nrings,) = struct.unpack_from(fmt_prefix + "I", buf, 5)
    rings = []
    off = 9
    for _ in range(nrings):
        (npts,) = struct.unpack_from(fmt_prefix + "I", buf, off); off += 4
        pts = []
        for _ in range(npts):
            x, y = struct.unpack_from(fmt_prefix + "dd", buf, off)
            pts.append((x, y))
            off += 16
        # drop closing repeat
        if len(pts) >= 2 and pts[0] == pts[-1]:
            pts = pts[:-1]
        rings.append(pts)
    return rings


def materialize_at_time(path: str, entity_id: int, t_ms: int) -> list[list[tuple[float, float]]]:
    target = np.datetime64(t_ms, "ms")
    table = pq.read_table(path,
                          filters=[("entity_id", "=", entity_id),
                                   ("t", "=", target)])
    if table.num_rows == 0:
        return []
    return _decode_polygon(table["geom_wkb"][0].as_py())


def range_read(path: str, t1_ms: int, t2_ms: int) -> int:
    table = pq.read_table(path,
                          filters=[("t", ">=", np.datetime64(t1_ms, "ms")),
                                   ("t", "<=", np.datetime64(t2_ms, "ms"))])
    return table.num_rows


def pointcloud_at_time(path: str, entity_id: int, t_ms: int) -> int:
    target = np.datetime64(t_ms, "ms")
    table = pq.read_table(path, filters=[("entity_id", "=", entity_id),
                                          ("t", "=", target)],
                          columns=["intensity"])
    return table.num_rows


def pointcloud_range_read(path: str, t1_ms: int, t2_ms: int) -> int:
    table = pq.read_table(path,
                          filters=[("t", ">=", np.datetime64(t1_ms, "ms")),
                                   ("t", "<=", np.datetime64(t2_ms, "ms"))],
                          columns=["entity_id"])
    return table.num_rows


def pointcloud_spatial_temporal(path: str, bbox, t_ms: int) -> tuple[int, int, int]:
    """No spatial pruning possible (WKB blobs have no stats). Filter by t,
    then decode every WKB point to check bbox membership."""
    xmin, ymin, xmax, ymax = bbox
    target = np.datetime64(t_ms, "ms")
    pf = pq.ParquetFile(path)
    total = pf.metadata.num_row_groups
    touched, matches = 0, 0
    for rg in range(total):
        rgmd = pf.metadata.row_group(rg)
        col_stats = {rgmd.column(i).path_in_schema: rgmd.column(i).statistics
                     for i in range(rgmd.num_columns)}
        ts = col_stats.get("t")
        if ts is None or ts.min is None or ts.min <= target <= ts.max:
            touched += 1
            tbl = pf.read_row_group(rg)
            mask = pa.compute.equal(tbl["t"], target)
            sub = tbl.filter(mask)
            for buf in sub["geom_wkb"].to_pylist():
                # WKB POINT Z layout: byte 0 = order; bytes 1-4 = type;
                # bytes 5-12 = x; 13-20 = y; 21-28 = z
                x, y = struct.unpack_from("<dd", buf, 5)
                if xmin <= x <= xmax and ymin <= y <= ymax:
                    matches += 1
    return matches, touched, total


def spatial_temporal_filter(path: str, bbox, t_ms: int) -> tuple[int, int, int]:
    """The honest 'current practice' filter. WKB blobs have no spatial
    stats — we just filter by t then scan WKBs to compute bbox membership.
    Reports (matches, touched_rg, total_rg) — touched is determined by
    the temporal filter only since spatial pruning isn't possible."""
    xmin, ymin, xmax, ymax = bbox
    target = np.datetime64(t_ms, "ms")
    pf = pq.ParquetFile(path)
    total = pf.metadata.num_row_groups
    # Determine which row groups have stats compatible with t
    touched = 0
    matching = set()
    for rg in range(total):
        rgmd = pf.metadata.row_group(rg)
        col_stats = {rgmd.column(i).path_in_schema: rgmd.column(i).statistics
                     for i in range(rgmd.num_columns)}
        ts = col_stats.get("t")
        if ts is None or ts.min is None:
            ok = True
        else:
            ok = ts.min <= target <= ts.max
        if not ok:
            continue
        touched += 1
        tbl = pf.read_row_group(rg)
        # Filter to target t
        mask = pa.compute.equal(tbl["t"], target)
        sub = tbl.filter(mask)
        for i, eid in enumerate(sub["entity_id"].to_pylist()):
            rings = _decode_polygon(sub["geom_wkb"][i].as_py())
            for ring in rings:
                if any(xmin <= x <= xmax and ymin <= y <= ymax for x, y in ring):
                    matching.add(eid)
                    break
    return len(matching), touched, total
