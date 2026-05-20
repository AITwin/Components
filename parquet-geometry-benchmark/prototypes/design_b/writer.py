"""Design B — flat-primitive decomposition.

Every row is a temporal point. Polygons are reconstructed by filtering on
(entity_id, t_idx) and ordering by (ring_idx, ring_pos). Per-entity
timeline lives in a sibling table mapping integer indices to timestamps.

Variants:
  - `design_b`     : raw — one row per (vertex × timestamp)
  - `design_b_plus`: static-collapse — one row per vertex with
                     (t_idx_start, t_idx_end) range
"""

from __future__ import annotations

import json

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

def polygon_schema() -> pa.Schema:
    return pa.schema([
        pa.field("entity_id", pa.int64()),
        pa.field("t_idx", pa.int32()),
        pa.field("ring_idx", pa.int16()),
        pa.field("ring_pos", pa.int32()),
        pa.field("x", pa.float64()),
        pa.field("y", pa.float64()),
    ])


def polygon_schema_plus() -> pa.Schema:
    return pa.schema([
        pa.field("entity_id", pa.int64()),
        pa.field("t_idx_start", pa.int32()),
        pa.field("t_idx_end", pa.int32()),
        pa.field("ring_idx", pa.int16()),
        pa.field("ring_pos", pa.int32()),
        pa.field("x", pa.float64()),
        pa.field("y", pa.float64()),
    ])


def timeline_schema() -> pa.Schema:
    return pa.schema([
        pa.field("entity_id", pa.int64()),
        pa.field("t_idx", pa.int32()),
        pa.field("t", pa.timestamp("ms")),
    ])


def pointcloud_schema() -> pa.Schema:
    return pa.schema([
        pa.field("entity_id", pa.int64()),
        pa.field("t_idx", pa.int32()),
        pa.field("x", pa.float64()),
        pa.field("y", pa.float64()),
        pa.field("z", pa.float64()),
        pa.field("intensity", pa.float32()),
        pa.field("classification", pa.int8()),
    ])


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

FOOTER_META = {
    b"design": b"B",
    b"ring_transition": b"explicit_ring_idx,monotonic_ring_pos,gaps_allowed",
    b"sort": b"entity_id,t_idx,ring_idx,ring_pos",
}


def write_polygon_workload(workload, main_path: str, timeline_path: str, row_group_size: int = 200_000) -> None:
    """One row per (vertex, t_idx). Variable-vertex sparsity handled by
    omitting rows for absent (ring_idx, ring_pos) combinations."""
    entity_ids, t_idxs, ring_idxs, ring_poss, xs, ys = [], [], [], [], [], []
    tl_eids, tl_idxs, tl_ts = [], [], []
    for ent in workload.entities:
        for ti, frame in enumerate(ent.frames):
            tl_eids.append(ent.entity_id); tl_idxs.append(ti); tl_ts.append(frame.t)
            for ring_idx, ring in enumerate(frame.rings):
                for ring_pos, (x, y) in enumerate(ring):
                    entity_ids.append(ent.entity_id)
                    t_idxs.append(ti)
                    ring_idxs.append(ring_idx)
                    ring_poss.append(ring_pos)
                    xs.append(x); ys.append(y)

    table = pa.table({
        "entity_id": pa.array(entity_ids, pa.int64()),
        "t_idx": pa.array(t_idxs, pa.int32()),
        "ring_idx": pa.array(ring_idxs, pa.int16()),
        "ring_pos": pa.array(ring_poss, pa.int32()),
        "x": pa.array(xs, pa.float64()),
        "y": pa.array(ys, pa.float64()),
    }, schema=polygon_schema())

    # Already in sort order because we generated in (entity, t_idx, ring, pos) order
    pq.write_table(
        table, main_path, compression="snappy", row_group_size=row_group_size,
    )
    pq.write_table(_timeline_table(tl_eids, tl_idxs, tl_ts), timeline_path,
                   compression="snappy")
    _write_footer_meta(main_path)


def write_polygon_workload_plus(workload, main_path: str, timeline_path: str,
                                 row_group_size: int = 200_000) -> None:
    """Static-collapse variant: each (entity, ring_idx, vertex) recorded
    once with (t_idx_start, t_idx_end). Suitable when many vertices have
    long static runs."""
    entity_ids, t_starts, t_ends = [], [], []
    ring_idxs, ring_poss, xs, ys = [], [], [], []
    tl_eids, tl_idxs, tl_ts = [], [], []

    for ent in workload.entities:
        # Build timeline first
        for ti, frame in enumerate(ent.frames):
            tl_eids.append(ent.entity_id); tl_idxs.append(ti); tl_ts.append(frame.t)

        # Per (ring_idx, ring_pos) track runs of identical (x,y)
        # Map (ring_idx, ring_pos) -> list of (ti, x, y)
        per_vertex: dict[tuple[int, int], list[tuple[int, float, float]]] = {}
        for ti, frame in enumerate(ent.frames):
            for ring_idx, ring in enumerate(frame.rings):
                for ring_pos, (x, y) in enumerate(ring):
                    per_vertex.setdefault((ring_idx, ring_pos), []).append((ti, x, y))

        for (ring_idx, ring_pos), entries in per_vertex.items():
            # collapse runs of identical (x, y)
            run_start = entries[0][0]; run_x, run_y = entries[0][1], entries[0][2]
            prev_ti = entries[0][0]
            for (ti, x, y) in entries[1:]:
                if (x, y) == (run_x, run_y) and ti == prev_ti + 1:
                    prev_ti = ti
                    continue
                # emit run
                entity_ids.append(ent.entity_id)
                t_starts.append(run_start); t_ends.append(prev_ti)
                ring_idxs.append(ring_idx); ring_poss.append(ring_pos)
                xs.append(run_x); ys.append(run_y)
                run_start = ti; run_x, run_y = x, y; prev_ti = ti
            # emit trailing run
            entity_ids.append(ent.entity_id)
            t_starts.append(run_start); t_ends.append(prev_ti)
            ring_idxs.append(ring_idx); ring_poss.append(ring_pos)
            xs.append(run_x); ys.append(run_y)

    table = pa.table({
        "entity_id": pa.array(entity_ids, pa.int64()),
        "t_idx_start": pa.array(t_starts, pa.int32()),
        "t_idx_end": pa.array(t_ends, pa.int32()),
        "ring_idx": pa.array(ring_idxs, pa.int16()),
        "ring_pos": pa.array(ring_poss, pa.int32()),
        "x": pa.array(xs, pa.float64()),
        "y": pa.array(ys, pa.float64()),
    }, schema=polygon_schema_plus())
    pq.write_table(table, main_path, compression="snappy", row_group_size=row_group_size)
    pq.write_table(_timeline_table(tl_eids, tl_idxs, tl_ts), timeline_path,
                   compression="snappy")
    _write_footer_meta(main_path)


def write_pointcloud_workload(workload, main_path: str, timeline_path: str,
                               row_group_size: int = 200_000) -> None:
    eids, tidx, x, y, z, inten, cls = [], [], [], [], [], [], []
    tl_eids, tl_idxs, tl_ts = [], [], []
    for ent in workload.entities:
        for ti, frame in enumerate(ent.frames):
            tl_eids.append(ent.entity_id); tl_idxs.append(ti); tl_ts.append(frame.t)
            n = frame.xyz.shape[0]
            eids.extend([ent.entity_id] * n)
            tidx.extend([ti] * n)
            x.extend(frame.xyz[:, 0].tolist())
            y.extend(frame.xyz[:, 1].tolist())
            z.extend(frame.xyz[:, 2].tolist())
            inten.extend(frame.intensity.tolist())
            cls.extend(frame.classification.tolist())

    table = pa.table({
        "entity_id": pa.array(eids, pa.int64()),
        "t_idx": pa.array(tidx, pa.int32()),
        "x": pa.array(x, pa.float64()),
        "y": pa.array(y, pa.float64()),
        "z": pa.array(z, pa.float64()),
        "intensity": pa.array(inten, pa.float32()),
        "classification": pa.array(cls, pa.int8()),
    }, schema=pointcloud_schema())
    pq.write_table(table, main_path, compression="snappy", row_group_size=row_group_size)
    pq.write_table(_timeline_table(tl_eids, tl_idxs, tl_ts), timeline_path,
                   compression="snappy")
    _write_footer_meta(main_path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _timeline_table(eids, idxs, ts):
    return pa.table({
        "entity_id": pa.array(eids, pa.int64()),
        "t_idx": pa.array(idxs, pa.int32()),
        "t": pa.array(ts, pa.timestamp("ms")),
    }, schema=timeline_schema())


def _write_footer_meta(path: str) -> None:
    # Re-write the file with footer metadata. Cheaper than re-encoding: we
    # accept the cost since this is a prototype, and metadata is small.
    table = pq.read_table(path)
    md = {**(table.schema.metadata or {}), **FOOTER_META}
    table = table.replace_schema_metadata(md)
    pq.write_table(table, path, compression="snappy")
