"""Design B reader: point-in-time, range, spatio-temporal filter, polygon recon."""

from __future__ import annotations

import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.compute as pc
import numpy as np


def _resolve_t_idx(timeline_path: str, entity_id: int, t_ms: int) -> int | None:
    tl = pq.read_table(timeline_path,
                       filters=[("entity_id", "=", entity_id),
                                ("t", "=", np.datetime64(t_ms, "ms"))])
    if tl.num_rows == 0:
        return None
    return int(tl["t_idx"][0].as_py())


def _resolve_t_idx_range(timeline_path: str, t1_ms: int, t2_ms: int) -> tuple[int, int] | None:
    tl = pq.read_table(timeline_path,
                       filters=[("t", ">=", np.datetime64(t1_ms, "ms")),
                                ("t", "<=", np.datetime64(t2_ms, "ms"))])
    if tl.num_rows == 0:
        return None
    arr = tl["t_idx"].to_numpy()
    return int(arr.min()), int(arr.max())


# ---------------------------------------------------------------------------
# Polygon reconstruction at time t
# ---------------------------------------------------------------------------

def materialize_polygon(main_path: str, timeline_path: str, entity_id: int,
                         t_ms: int, plus: bool = False) -> list[list[tuple[float, float]]]:
    t_idx = _resolve_t_idx(timeline_path, entity_id, t_ms)
    if t_idx is None:
        return []
    if plus:
        # Range-encoded: select rows where t_idx_start <= t_idx <= t_idx_end
        table = pq.read_table(main_path,
                              filters=[("entity_id", "=", entity_id),
                                       ("t_idx_start", "<=", t_idx),
                                       ("t_idx_end", ">=", t_idx)])
    else:
        table = pq.read_table(main_path,
                              filters=[("entity_id", "=", entity_id),
                                       ("t_idx", "=", t_idx)])
    if table.num_rows == 0:
        return []
    # Group by ring_idx, order by ring_pos
    ring_idx = table["ring_idx"].to_numpy()
    ring_pos = table["ring_pos"].to_numpy()
    x = table["x"].to_numpy(); y = table["y"].to_numpy()
    rings: dict[int, list[tuple[int, float, float]]] = {}
    for ri, rp, xv, yv in zip(ring_idx, ring_pos, x, y):
        rings.setdefault(int(ri), []).append((int(rp), float(xv), float(yv)))
    return [[(xv, yv) for _, xv, yv in sorted(r)] for _, r in sorted(rings.items())]


# ---------------------------------------------------------------------------
# Range read
# ---------------------------------------------------------------------------

def range_read(main_path: str, timeline_path: str, t1_ms: int, t2_ms: int,
                plus: bool = False) -> int:
    rng = _resolve_t_idx_range(timeline_path, t1_ms, t2_ms)
    if rng is None:
        return 0
    t1, t2 = rng
    if plus:
        table = pq.read_table(main_path,
                              filters=[("t_idx_start", "<=", t2),
                                       ("t_idx_end", ">=", t1)])
    else:
        table = pq.read_table(main_path,
                              filters=[("t_idx", ">=", t1), ("t_idx", "<=", t2)])
    return table.num_rows


# ---------------------------------------------------------------------------
# Spatio-temporal filter (with optional row-group bbox refinement)
# ---------------------------------------------------------------------------

def pointcloud_at_time(main_path: str, timeline_path: str, entity_id: int, t_ms: int) -> int:
    t_idx = _resolve_t_idx(timeline_path, entity_id, t_ms)
    if t_idx is None:
        return 0
    table = pq.read_table(main_path,
                          filters=[("entity_id", "=", entity_id),
                                   ("t_idx", "=", t_idx)],
                          columns=["x"])
    return table.num_rows


def pointcloud_range_read(main_path: str, timeline_path: str, t1_ms: int, t2_ms: int) -> int:
    rng = _resolve_t_idx_range(timeline_path, t1_ms, t2_ms)
    if rng is None:
        return 0
    t1, t2 = rng
    table = pq.read_table(main_path,
                          filters=[("t_idx", ">=", t1), ("t_idx", "<=", t2)],
                          columns=["entity_id"])
    return table.num_rows


def pointcloud_spatial_temporal(main_path: str, timeline_path: str, bbox, t_ms: int) -> tuple[int, int, int]:
    """Return (point_count_in_bbox, touched_rg, total_rg)."""
    xmin, ymin, xmax, ymax = bbox
    tl = pq.read_table(timeline_path, filters=[("t", "=", np.datetime64(t_ms, "ms"))])
    if tl.num_rows == 0:
        return 0, 0, pq.ParquetFile(main_path).metadata.num_row_groups
    t_idxs = set(tl["t_idx"].to_numpy().tolist())
    pf = pq.ParquetFile(main_path)
    total = pf.metadata.num_row_groups
    matches, touched = 0, 0
    for rg_idx in range(total):
        rgmd = pf.metadata.row_group(rg_idx)
        col_stats = {rgmd.column(i).path_in_schema: rgmd.column(i).statistics
                     for i in range(rgmd.num_columns)}
        sx = col_stats.get("x"); sy = col_stats.get("y")
        ti = col_stats.get("t_idx")
        spatial_match = (sx is None or sy is None or sx.min is None or
                         not (sx.max < xmin or sx.min > xmax or sy.max < ymin or sy.min > ymax))
        temporal_match = (ti is None or ti.min is None or
                          not (ti.max < min(t_idxs) or ti.min > max(t_idxs)))
        if spatial_match and temporal_match:
            touched += 1
            tbl = pf.read_row_group(rg_idx)
            import pyarrow.compute as pc
            mask = pc.is_in(tbl["t_idx"], value_set=pa.array(sorted(t_idxs)))
            mask = pc.and_(mask, pc.greater_equal(tbl["x"], xmin))
            mask = pc.and_(mask, pc.less_equal(tbl["x"], xmax))
            mask = pc.and_(mask, pc.greater_equal(tbl["y"], ymin))
            mask = pc.and_(mask, pc.less_equal(tbl["y"], ymax))
            matches += tbl.filter(mask).num_rows
    return matches, touched, total


def spatial_temporal_filter(main_path: str, timeline_path: str,
                              bbox: tuple[float, float, float, float],
                              t_ms: int, plus: bool = False) -> tuple[int, int, int]:
    """Find entities with a vertex in bbox at time t.
    Returns (matching_entities, row_groups_touched, total_row_groups).
    Row-group pruning is driven by min/max stats on x/y for each row group
    — this is the test of whether Design B's sort discipline gives spatial
    locality."""
    xmin, ymin, xmax, ymax = bbox
    # Look up t_idxs for the timestamp (point-in-time)
    tl = pq.read_table(timeline_path, filters=[("t", "=", np.datetime64(t_ms, "ms"))])
    if tl.num_rows == 0:
        return 0, 0, pq.ParquetFile(main_path).metadata.num_row_groups
    t_idxs = set(tl["t_idx"].to_numpy().tolist())

    pf = pq.ParquetFile(main_path)
    total_rg = pf.metadata.num_row_groups

    # Figure out which row groups can possibly contain matching rows.
    touched = 0
    matching_entities: set[int] = set()
    for rg_idx in range(total_rg):
        rgmd = pf.metadata.row_group(rg_idx)
        col_stats = {rgmd.column(i).path_in_schema: rgmd.column(i).statistics
                     for i in range(rgmd.num_columns)}
        # Spatial bbox stats
        sx = col_stats.get("x"); sy = col_stats.get("y")
        if sx is None or sx.min is None or sy is None or sy.min is None:
            spatial_match = True
        else:
            spatial_match = not (sx.max < xmin or sx.min > xmax or
                                 sy.max < ymin or sy.min > ymax)
        if plus:
            ts = col_stats.get("t_idx_start"); te = col_stats.get("t_idx_end")
            if ts is None or te is None or ts.min is None or te.max is None:
                temporal_match = True
            else:
                # Row group may contain a range covering some t_idx in t_idxs
                # if its [t_idx_start.min, t_idx_end.max] overlaps t_idxs
                t_lo = min(t_idxs); t_hi = max(t_idxs)
                temporal_match = not (te.max < t_lo or ts.min > t_hi)
        else:
            ti = col_stats.get("t_idx")
            if ti is None or ti.min is None:
                temporal_match = True
            else:
                t_lo = min(t_idxs); t_hi = max(t_idxs)
                temporal_match = not (ti.max < t_lo or ti.min > t_hi)
        if spatial_match and temporal_match:
            touched += 1
            tbl = pf.read_row_group(rg_idx)
            # Apply the predicate
            mask_t = pc.is_in(tbl["t_idx" if not plus else "t_idx_start"],
                              value_set=pa.array(sorted(t_idxs))) if not plus else None
            if plus:
                mask = pc.and_(
                    pc.less_equal(tbl["t_idx_start"], max(t_idxs)),
                    pc.greater_equal(tbl["t_idx_end"], min(t_idxs)),
                )
            else:
                mask = mask_t
            mask = pc.and_(mask, pc.greater_equal(tbl["x"], xmin))
            mask = pc.and_(mask, pc.less_equal(tbl["x"], xmax))
            mask = pc.and_(mask, pc.greater_equal(tbl["y"], ymin))
            mask = pc.and_(mask, pc.less_equal(tbl["y"], ymax))
            filtered = tbl.filter(mask)
            for eid in filtered["entity_id"].to_pylist():
                matching_entities.add(eid)
    return len(matching_entities), touched, total_rg
