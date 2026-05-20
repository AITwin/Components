"""Design A reader: point-in-time, range, and spatio-temporal queries."""

from __future__ import annotations

import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.compute as pc
import numpy as np
from bisect import bisect_left


def _load_with_filter(path: str, filt) -> pa.Table:
    return pq.read_table(path, filters=filt)


def row_group_stats(path: str) -> dict:
    """Return per-row-group statistics. Useful for the pruning honesty check."""
    pf = pq.ParquetFile(path)
    md = pf.metadata
    info = {"num_row_groups": md.num_row_groups, "row_groups": []}
    for rg in range(md.num_row_groups):
        rgmd = md.row_group(rg)
        cols = {}
        for c in range(rgmd.num_columns):
            cm = rgmd.column(c)
            s = cm.statistics
            if s is None:
                continue
            cols[cm.path_in_schema] = {
                "min": s.min, "max": s.max, "null_count": s.null_count,
            }
        info["row_groups"].append({"num_rows": rgmd.num_rows, "columns": cols})
    return info


def count_row_groups_touched(path: str, filt) -> tuple[int, int]:
    """Returns (read, total) — how many row groups matched the predicate."""
    pf = pq.ParquetFile(path)
    total = pf.metadata.num_row_groups
    table = pq.read_table(path, filters=filt, columns=["entity_id"])
    # Reverse-engineer: how many distinct row groups would have been touched?
    # PyArrow doesn't expose this directly, so we walk row groups and
    # apply the predicate to each one's statistics manually.
    touched = 0
    for rg in range(total):
        rgmd = pf.metadata.row_group(rg)
        if _rg_could_match(rgmd, filt):
            touched += 1
    return touched, total


def _rg_could_match(rgmd, filt) -> bool:
    """Conservative: returns True if a row group's stats cannot rule out filt."""
    # filt is a list of (col, op, val) tuples in pyarrow filter syntax.
    cols_by_path = {rgmd.column(i).path_in_schema: rgmd.column(i) for i in range(rgmd.num_columns)}
    for col, op, val in filt:
        if col not in cols_by_path:
            return True  # no stats -> cannot prune
        s = cols_by_path[col].statistics
        if s is None or s.min is None or s.max is None:
            return True
        mn, mx = s.min, s.max
        if op == "=" or op == "==":
            if not (mn <= val <= mx):
                return False
        elif op == "<":
            if not (mn < val):
                return False
        elif op == "<=":
            if not (mn <= val):
                return False
        elif op == ">":
            if not (mx > val):
                return False
        elif op == ">=":
            if not (mx >= val):
                return False
    return True


# ---------------------------------------------------------------------------
# Geometry materialization
# ---------------------------------------------------------------------------

def materialize_at_time(path: str, entity_id: int, t_ms: int, is_static: bool = False) -> list[list[tuple[float, float]]]:
    """Return the polygon rings for an entity at time t_ms."""
    table = pq.read_table(path, filters=[("entity_id", "=", entity_id)])
    if table.num_rows == 0:
        return []
    row = table.to_pylist()[0]
    if is_static:
        # Single-entry per-vertex traj — same polygon at all observation times
        rings: dict[int, list[tuple[int, float, float]]] = {}
        for v in row["vertices"]:
            rings.setdefault(v["ring_idx"], []).append((v["vertex_id"], v["traj"][0]["x"], v["traj"][0]["y"]))
        # Verify t_ms is within observations (we materialize anyway)
        return [[(x, y) for _, x, y in sorted(r)] for _, r in sorted(rings.items())]

    # Variable / fixed case: find the per-vertex trajectory entry whose t
    # exactly matches t_ms (or nearest for interp=linear, but we keep it
    # simple — the workloads put observations on a regular grid).
    rings: dict[int, list[tuple[int, float, float]]] = {}
    target = np.datetime64(t_ms, "ms")
    for v in row["vertices"]:
        traj = v["traj"]
        # Find the entry at this t
        ts = [s["t"] for s in traj]
        # binary search
        idx = bisect_left(ts, target)
        if idx >= len(traj):
            continue
        s = traj[idx]
        if s["t"] != target:
            continue
        rings.setdefault(v["ring_idx"], []).append((v["vertex_id"], s["x"], s["y"]))
    return [[(x, y) for _, x, y in sorted(r)] for _, r in sorted(rings.items())]


def range_read(path: str, t1_ms: int, t2_ms: int) -> int:
    """Count entities whose [t_min, t_max] overlaps [t1, t2]. Returns rows read."""
    filt = [("t_max", ">=", np.datetime64(t1_ms, "ms")),
            ("t_min", "<=", np.datetime64(t2_ms, "ms"))]
    table = pq.read_table(path, filters=filt)
    return table.num_rows


def spatial_temporal_filter(path: str, bbox: tuple[float, float, float, float],
                             t_ms: int, with_bbox: bool = True,
                             is_static: bool = False) -> tuple[int, int, int]:
    """Find entities with any vertex in bbox at time t.

    Returns (matches, touched_rg, total_rg). With bbox sidecar: row-group
    pruning happens on flat columns and we still scan candidates to drop
    false positives. Without bbox: PyArrow cannot prune on nested leaves
    via the current implementation, so we read everything and do the
    spatial test in Python — which is the honest cost of the pure form.
    """
    xmin, ymin, xmax, ymax = bbox
    target = np.datetime64(t_ms, "ms")
    base_filter = [
        ("t_min", "<=", target),
        ("t_max", ">=", target),
    ]
    if with_bbox:
        spatial = [
            ("bbox_xmax", ">=", xmin),
            ("bbox_xmin", "<=", xmax),
            ("bbox_ymax", ">=", ymin),
            ("bbox_ymin", "<=", ymax),
        ]
        full_filter = base_filter + spatial
    else:
        full_filter = base_filter

    touched, total = count_row_groups_touched(path, full_filter)
    table = pq.read_table(path, filters=full_filter)

    # Always do a true vertex-level check (bbox prefilter is conservative).
    matches = 0
    for row in table.to_pylist():
        if _vertex_in_bbox(row, target, xmin, ymin, xmax, ymax, is_static):
            matches += 1
    return matches, touched, total


def materialize_at_time_snapshot(path: str, entity_id: int, t_ms: int) -> list[list[tuple[float, float]]]:
    """A2 reader: look up the snapshot frame at time t_ms."""
    table = pq.read_table(path, filters=[("entity_id", "=", entity_id)])
    if table.num_rows == 0:
        return []
    row = table.to_pylist()[0]
    target = np.datetime64(t_ms, "ms")
    for f in row["frames"]:
        if f["t"] == target:
            return [[(p["x"], p["y"]) for p in ring] for ring in f["rings"]]
    return []


def spatial_temporal_filter_snapshot(path: str, bbox, t_ms: int, with_bbox: bool = True):
    """A2 spatial-temporal filter with the same honest semantics as A1:
    bbox sidecar prunes row groups; without it we still scan all frames
    in Python to find true matches."""
    xmin, ymin, xmax, ymax = bbox
    target = np.datetime64(t_ms, "ms")
    base_filter = [("t_min", "<=", target), ("t_max", ">=", target)]
    if with_bbox:
        spatial = [
            ("bbox_xmax", ">=", xmin), ("bbox_xmin", "<=", xmax),
            ("bbox_ymax", ">=", ymin), ("bbox_ymin", "<=", ymax),
        ]
        full = base_filter + spatial
    else:
        full = base_filter
    touched, total = count_row_groups_touched(path, full)
    table = pq.read_table(path, filters=full)
    matches = 0
    for row in table.to_pylist():
        for f in row["frames"]:
            if f["t"] != target:
                continue
            hit = False
            for ring in f["rings"]:
                for p in ring:
                    if xmin <= p["x"] <= xmax and ymin <= p["y"] <= ymax:
                        hit = True; break
                if hit: break
            if hit:
                matches += 1
            break
    return matches, touched, total


def materialize_points_at_time(path: str, entity_id: int, t_ms: int) -> int:
    """Pointcloud: return count of points at time t (we return count to keep
    benchmark output small)."""
    target = np.datetime64(t_ms, "ms")
    table = pq.read_table(path, filters=[("entity_id", "=", entity_id)])
    if table.num_rows == 0:
        return 0
    row = table.to_pylist()[0]
    for f in row["frames"]:
        if f["t"] == target:
            return len(f["x"])
    return 0


def pointcloud_range_read(path: str, t1_ms: int, t2_ms: int) -> int:
    table = pq.read_table(path,
                          filters=[("t_max", ">=", np.datetime64(t1_ms, "ms")),
                                   ("t_min", "<=", np.datetime64(t2_ms, "ms"))])
    return table.num_rows


def _vertex_in_bbox(row, target, xmin, ymin, xmax, ymax, is_static) -> bool:
    if is_static:
        for v in row["vertices"]:
            s = v["traj"][0]
            if xmin <= s["x"] <= xmax and ymin <= s["y"] <= ymax:
                return True
        return False
    for v in row["vertices"]:
        traj = v["traj"]
        # binary search for target
        ts = [s["t"] for s in traj]
        from bisect import bisect_left as _bl
        idx = _bl(ts, target)
        if idx >= len(traj) or traj[idx]["t"] != target:
            continue
        s = traj[idx]
        if xmin <= s["x"] <= xmax and ymin <= s["y"] <= ymax:
            return True
    return False
