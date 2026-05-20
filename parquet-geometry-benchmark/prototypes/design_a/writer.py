"""Design A — Nested-MEOS-Arrow encoding.

Polygons are stored as List<Struct<ring_idx, vertex_id, traj: List<Struct<t,x,y>>>>.
Each per-vertex trajectory is a MEOS-shaped tgeompoint. Variable vertex
counts are handled by per-vertex trajectories ending or beginning at
different times — there is no positional ambiguity across frames.

Top-level flat columns (entity_id, subtype, interp, srid, flags, t_min,
t_max, bbox_*) are present for row-group pruning. The bbox sidecar can be
toggled off to measure the "pure" variant.
"""

from __future__ import annotations

import pyarrow as pa
import pyarrow.parquet as pq
import numpy as np


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

def _traj_type() -> pa.DataType:
    return pa.list_(pa.struct([
        pa.field("t", pa.timestamp("ms")),
        pa.field("x", pa.float64()),
        pa.field("y", pa.float64()),
    ]))


def polygon_schema(with_bbox: bool) -> pa.Schema:
    fields = [
        pa.field("entity_id", pa.int64()),
        pa.field("subtype", pa.int8()),
        pa.field("interp", pa.int8()),
        pa.field("srid", pa.int32()),
        pa.field("flags", pa.int32()),
        pa.field("t_min", pa.timestamp("ms")),
        pa.field("t_max", pa.timestamp("ms")),
    ]
    if with_bbox:
        fields += [
            pa.field("bbox_xmin", pa.float64()),
            pa.field("bbox_xmax", pa.float64()),
            pa.field("bbox_ymin", pa.float64()),
            pa.field("bbox_ymax", pa.float64()),
        ]
    fields += [
        pa.field("observations", pa.list_(pa.timestamp("ms"))),
        pa.field("vertices", pa.list_(pa.struct([
            pa.field("ring_idx", pa.int16()),
            pa.field("vertex_id", pa.int32()),
            pa.field("traj", _traj_type()),
        ]))),
    ]
    return pa.schema(fields)


def pointcloud_schema(with_bbox: bool) -> pa.Schema:
    fields = [
        pa.field("entity_id", pa.int64()),
        pa.field("subtype", pa.int8()),
        pa.field("interp", pa.int8()),
        pa.field("srid", pa.int32()),
        pa.field("flags", pa.int32()),
        pa.field("t_min", pa.timestamp("ms")),
        pa.field("t_max", pa.timestamp("ms")),
    ]
    if with_bbox:
        fields += [
            pa.field("bbox_xmin", pa.float64()),
            pa.field("bbox_xmax", pa.float64()),
            pa.field("bbox_ymin", pa.float64()),
            pa.field("bbox_ymax", pa.float64()),
        ]
    fields += [
        pa.field("frames", pa.list_(pa.struct([
            pa.field("t", pa.timestamp("ms")),
            pa.field("x", pa.list_(pa.float64())),
            pa.field("y", pa.list_(pa.float64())),
            pa.field("z", pa.list_(pa.float64())),
            pa.field("intensity", pa.list_(pa.float32())),
            pa.field("classification", pa.list_(pa.int8())),
        ]))),
    ]
    return pa.schema(fields)


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

def write_polygon_workload(workload, path: str, with_bbox: bool = True, row_group_size: int = 32) -> None:
    """Convert a polygon workload to Design A parquet."""
    rows = []
    is_static = workload.is_static
    for ent in workload.entities:
        # Collect all (t, x, y) per (ring_idx, vertex_id). For static
        # workload (W1) we keep one traj entry per vertex and store the
        # observation timestamps in a sibling column.
        per_vertex: dict[tuple[int, int], list[tuple[int, float, float]]] = {}
        all_t = []
        xs_all, ys_all = [], []
        for frame in ent.frames:
            all_t.append(frame.t)
            for ring_idx, ring in enumerate(frame.rings):
                for vid, (x, y) in enumerate(ring):
                    per_vertex.setdefault((ring_idx, vid), []).append((frame.t, x, y))
                    xs_all.append(x); ys_all.append(y)

        if is_static:
            # collapse traj to a single entry per vertex; observations sidelist
            vertices = []
            for (ring_idx, vid), pts in per_vertex.items():
                t0, x0, y0 = pts[0]
                vertices.append({
                    "ring_idx": ring_idx,
                    "vertex_id": vid,
                    "traj": [{"t": t0, "x": x0, "y": y0}],
                })
            observations = all_t
        else:
            vertices = []
            for (ring_idx, vid), pts in per_vertex.items():
                vertices.append({
                    "ring_idx": ring_idx,
                    "vertex_id": vid,
                    "traj": [{"t": t, "x": x, "y": y} for (t, x, y) in pts],
                })
            observations = []  # implicit from traj

        row = {
            "entity_id": ent.entity_id,
            "subtype": 2,
            "interp": workload.interp,
            "srid": ent.srid,
            "flags": 0,
            "t_min": min(all_t),
            "t_max": max(all_t),
            "observations": observations,
            "vertices": vertices,
        }
        if with_bbox:
            row.update({
                "bbox_xmin": float(min(xs_all)),
                "bbox_xmax": float(max(xs_all)),
                "bbox_ymin": float(min(ys_all)),
                "bbox_ymax": float(max(ys_all)),
            })
        rows.append(row)

    schema = polygon_schema(with_bbox)
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, path, compression="snappy", row_group_size=row_group_size)


def write_pointcloud_workload(workload, path: str, with_bbox: bool = True, row_group_size: int = 1) -> None:
    rows = []
    for ent in workload.entities:
        all_t, xmin, xmax, ymin, ymax = [], float("inf"), float("-inf"), float("inf"), float("-inf")
        frames = []
        for frame in ent.frames:
            all_t.append(frame.t)
            x = frame.xyz[:, 0]; y = frame.xyz[:, 1]; z = frame.xyz[:, 2]
            xmin = min(xmin, float(x.min())); xmax = max(xmax, float(x.max()))
            ymin = min(ymin, float(y.min())); ymax = max(ymax, float(y.max()))
            frames.append({
                "t": frame.t,
                "x": x.tolist(),
                "y": y.tolist(),
                "z": z.tolist(),
                "intensity": frame.intensity.tolist(),
                "classification": frame.classification.tolist(),
            })
        row = {
            "entity_id": ent.entity_id, "subtype": 4, "interp": workload.interp,
            "srid": ent.srid, "flags": 0,
            "t_min": min(all_t), "t_max": max(all_t), "frames": frames,
        }
        if with_bbox:
            row.update({"bbox_xmin": xmin, "bbox_xmax": xmax,
                        "bbox_ymin": ymin, "bbox_ymax": ymax})
        rows.append(row)
    schema = pointcloud_schema(with_bbox)
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, path, compression="snappy", row_group_size=row_group_size)
