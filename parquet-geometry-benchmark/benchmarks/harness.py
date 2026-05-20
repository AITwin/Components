"""Benchmark harness — drives writers and readers across designs.

Outputs results.json with one entry per (design, workload, size, metric).
"""

from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from synthetic.workloads import (
    GENERATORS, SIZE_PRESETS, Workload, PolygonEntity, PointCloudEntity,
)
from prototypes.design_a import writer as a_writer
from prototypes.design_a import reader as a_reader
from prototypes.design_b import writer as b_writer
from prototypes.design_b import reader as b_reader
from prototypes.baseline_wkb import writer as wkb_writer
from prototypes.baseline_wkb import reader as wkb_reader


DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)


def _is_polygon(workload: Workload) -> bool:
    return isinstance(workload.entities[0], PolygonEntity)


def _file_size(*paths: str) -> int:
    return sum(os.path.getsize(p) for p in paths if os.path.exists(p))


# ---------------------------------------------------------------------------
# Single benchmark run
# ---------------------------------------------------------------------------

def benchmark_one(workload_key: str, size: str, n_queries: int = 30) -> list[dict]:
    gen = GENERATORS[workload_key]
    workload = gen(seed=42, size=size)
    n_entities = len(workload.entities)
    n_rows_total = sum(
        len(e.frames) if isinstance(e, PolygonEntity) or isinstance(e, PointCloudEntity) else 0
        for e in workload.entities
    )

    results: list[dict] = []
    base = DATA_DIR / f"{workload.name}"

    is_poly = _is_polygon(workload)

    # ---- Write phase ----
    runs = {}
    if is_poly:
        runs["baseline_wkb"] = lambda p: wkb_writer.write_polygon_workload(workload, p[0])
        runs["design_a"] = lambda p: a_writer.write_polygon_workload(workload, p[0], with_bbox=True)
        runs["design_a_nobbox"] = lambda p: a_writer.write_polygon_workload(workload, p[0], with_bbox=False)
        runs["design_b"] = lambda p: b_writer.write_polygon_workload(workload, p[0], p[1])
        if workload.is_static:
            runs["design_b_plus"] = lambda p: b_writer.write_polygon_workload_plus(workload, p[0], p[1])
    else:
        runs["baseline_wkb"] = lambda p: wkb_writer.write_pointcloud_workload(workload, p[0])
        runs["design_a"] = lambda p: a_writer.write_pointcloud_workload(workload, p[0], with_bbox=True)
        runs["design_a_nobbox"] = lambda p: a_writer.write_pointcloud_workload(workload, p[0], with_bbox=False)
        runs["design_b"] = lambda p: b_writer.write_pointcloud_workload(workload, p[0], p[1])

    # Paths
    paths = {
        "baseline_wkb": [f"{base}.wkb.parquet"],
        "design_a": [f"{base}.a.parquet"],
        "design_a_nobbox": [f"{base}.a_nobbox.parquet"],
        "design_b": [f"{base}.b.main.parquet", f"{base}.b.timeline.parquet"],
        "design_b_plus": [f"{base}.bplus.main.parquet", f"{base}.bplus.timeline.parquet"],
    }

    sizes_by_design: dict[str, int] = {}
    write_times_by_design: dict[str, float] = {}
    for design, runner in runs.items():
        ps = paths[design]
        for p in ps:
            if os.path.exists(p):
                os.remove(p)
        t0 = time.perf_counter()
        runner(ps)
        dt = time.perf_counter() - t0
        write_times_by_design[design] = dt
        sizes_by_design[design] = _file_size(*ps)
        results.append({
            "workload": workload.name, "size_preset": size, "design": design,
            "metric": "storage_bytes", "value": sizes_by_design[design],
        })
        results.append({
            "workload": workload.name, "size_preset": size, "design": design,
            "metric": "write_time_s", "value": dt,
        })
        results.append({
            "workload": workload.name, "size_preset": size, "design": design,
            "metric": "write_rows_per_s", "value": n_rows_total / dt if dt > 0 else None,
        })

    # ---- Compression ratio vs WKB ----
    wkb_sz = sizes_by_design["baseline_wkb"]
    for design, sz in sizes_by_design.items():
        if design == "baseline_wkb":
            continue
        results.append({
            "workload": workload.name, "size_preset": size, "design": design,
            "metric": "compression_ratio_vs_wkb", "value": wkb_sz / sz if sz else None,
        })

    # ---- Query workload setup ----
    rng = random.Random(123)
    sample_entities = [e.entity_id for e in rng.sample(workload.entities, min(n_queries, n_entities))]
    sample_times = [
        rng.choice(workload.entities[0].frames).t for _ in range(n_queries)
    ]

    # ---- Point-in-time queries ----
    if is_poly:
        # design_a
        t0 = time.perf_counter()
        for eid, t in zip(sample_entities, sample_times):
            a_reader.materialize_at_time(paths["design_a"][0], eid, t, is_static=workload.is_static)
        dt = (time.perf_counter() - t0) / n_queries
        results.append({"workload": workload.name, "size_preset": size,
                        "design": "design_a", "metric": "point_in_time_ms", "value": dt * 1000})

        t0 = time.perf_counter()
        for eid, t in zip(sample_entities, sample_times):
            a_reader.materialize_at_time(paths["design_a_nobbox"][0], eid, t, is_static=workload.is_static)
        dt = (time.perf_counter() - t0) / n_queries
        results.append({"workload": workload.name, "size_preset": size,
                        "design": "design_a_nobbox", "metric": "point_in_time_ms", "value": dt * 1000})

        t0 = time.perf_counter()
        for eid, t in zip(sample_entities, sample_times):
            b_reader.materialize_polygon(paths["design_b"][0], paths["design_b"][1], eid, t, plus=False)
        dt = (time.perf_counter() - t0) / n_queries
        results.append({"workload": workload.name, "size_preset": size,
                        "design": "design_b", "metric": "point_in_time_ms", "value": dt * 1000})

        if workload.is_static:
            t0 = time.perf_counter()
            for eid, t in zip(sample_entities, sample_times):
                b_reader.materialize_polygon(paths["design_b_plus"][0], paths["design_b_plus"][1], eid, t, plus=True)
            dt = (time.perf_counter() - t0) / n_queries
            results.append({"workload": workload.name, "size_preset": size,
                            "design": "design_b_plus", "metric": "point_in_time_ms", "value": dt * 1000})

        t0 = time.perf_counter()
        for eid, t in zip(sample_entities, sample_times):
            wkb_reader.materialize_at_time(paths["baseline_wkb"][0], eid, t)
        dt = (time.perf_counter() - t0) / n_queries
        results.append({"workload": workload.name, "size_preset": size,
                        "design": "baseline_wkb", "metric": "point_in_time_ms", "value": dt * 1000})

    # ---- Range read ----
    # pick a 10%-of-span range from the middle
    all_t = sorted(set(f.t for e in workload.entities for f in e.frames))
    span = all_t[-1] - all_t[0]
    t1 = all_t[len(all_t) // 2 - len(all_t) // 20]
    t2 = all_t[len(all_t) // 2 + len(all_t) // 20]

    if is_poly:
        for dname, fn in [
            ("design_a", lambda: a_reader.range_read(paths["design_a"][0], t1, t2)),
            ("design_a_nobbox", lambda: a_reader.range_read(paths["design_a_nobbox"][0], t1, t2)),
            ("design_b", lambda: b_reader.range_read(paths["design_b"][0], paths["design_b"][1], t1, t2, plus=False)),
            ("baseline_wkb", lambda: wkb_reader.range_read(paths["baseline_wkb"][0], t1, t2)),
        ]:
            t0 = time.perf_counter()
            n = fn()
            dt = time.perf_counter() - t0
            results.append({"workload": workload.name, "size_preset": size,
                            "design": dname, "metric": "range_read_ms", "value": dt * 1000})
            results.append({"workload": workload.name, "size_preset": size,
                            "design": dname, "metric": "range_read_rows", "value": int(n)})
        if workload.is_static:
            t0 = time.perf_counter()
            n = b_reader.range_read(paths["design_b_plus"][0], paths["design_b_plus"][1], t1, t2, plus=True)
            dt = time.perf_counter() - t0
            results.append({"workload": workload.name, "size_preset": size,
                            "design": "design_b_plus", "metric": "range_read_ms", "value": dt * 1000})

    # ---- Spatio-temporal filter ----
    if is_poly:
        # bbox: a 100x100 box around the median centroid at the median time
        ent0 = workload.entities[len(workload.entities) // 2]
        f0 = ent0.frames[len(ent0.frames) // 2]
        cx = sum(p[0] for r in f0.rings for p in r) / sum(len(r) for r in f0.rings)
        cy = sum(p[1] for r in f0.rings for p in r) / sum(len(r) for r in f0.rings)
        bbox = (cx - 50, cy - 50, cx + 50, cy + 50)
        t_query = f0.t

        for dname, fn in [
            ("design_a", lambda: a_reader.spatial_temporal_filter(paths["design_a"][0], bbox, t_query, with_bbox=True, is_static=workload.is_static)),
            ("design_a_nobbox", lambda: a_reader.spatial_temporal_filter(paths["design_a_nobbox"][0], bbox, t_query, with_bbox=False, is_static=workload.is_static)),
            ("design_b", lambda: b_reader.spatial_temporal_filter(paths["design_b"][0], paths["design_b"][1], bbox, t_query, plus=False)),
            ("baseline_wkb", lambda: wkb_reader.spatial_temporal_filter(paths["baseline_wkb"][0], bbox, t_query)),
        ]:
            t0 = time.perf_counter()
            matches, touched, total = fn()
            dt = time.perf_counter() - t0
            results.append({"workload": workload.name, "size_preset": size,
                            "design": dname, "metric": "spatial_temporal_ms", "value": dt * 1000})
            results.append({"workload": workload.name, "size_preset": size,
                            "design": dname, "metric": "spatial_temporal_matches", "value": int(matches)})
            results.append({"workload": workload.name, "size_preset": size,
                            "design": dname, "metric": "row_groups_touched", "value": int(touched)})
            results.append({"workload": workload.name, "size_preset": size,
                            "design": dname, "metric": "row_groups_total", "value": int(total)})

    # ---- Pointcloud queries ----
    if not is_poly:
        ent0 = workload.entities[0]
        f0 = ent0.frames[len(ent0.frames) // 2]
        cx = float(np.median(f0.xyz[:, 0])); cy = float(np.median(f0.xyz[:, 1]))
        bbox = (cx - 25, cy - 25, cx + 25, cy + 25)
        t_query = f0.t

        # point-in-time
        sample_pc = [(e.entity_id, rng.choice(e.frames).t) for e in rng.sample(workload.entities, min(n_queries, n_entities))]
        for dname, fn in [
            ("design_a", lambda eid, t: a_reader.materialize_points_at_time(paths["design_a"][0], eid, t)),
            ("design_a_nobbox", lambda eid, t: a_reader.materialize_points_at_time(paths["design_a_nobbox"][0], eid, t)),
            ("design_b", lambda eid, t: b_reader.pointcloud_at_time(paths["design_b"][0], paths["design_b"][1], eid, t)),
            ("baseline_wkb", lambda eid, t: wkb_reader.pointcloud_at_time(paths["baseline_wkb"][0], eid, t)),
        ]:
            t0 = time.perf_counter()
            for eid, t in sample_pc:
                fn(eid, t)
            dt = (time.perf_counter() - t0) / len(sample_pc)
            results.append({"workload": workload.name, "size_preset": size,
                            "design": dname, "metric": "point_in_time_ms", "value": dt * 1000})

        # range read
        t1pc = ent0.frames[max(0, len(ent0.frames)//2 - 3)].t
        t2pc = ent0.frames[min(len(ent0.frames)-1, len(ent0.frames)//2 + 3)].t
        for dname, fn in [
            ("design_a", lambda: a_reader.pointcloud_range_read(paths["design_a"][0], t1pc, t2pc)),
            ("design_a_nobbox", lambda: a_reader.pointcloud_range_read(paths["design_a_nobbox"][0], t1pc, t2pc)),
            ("design_b", lambda: b_reader.pointcloud_range_read(paths["design_b"][0], paths["design_b"][1], t1pc, t2pc)),
            ("baseline_wkb", lambda: wkb_reader.pointcloud_range_read(paths["baseline_wkb"][0], t1pc, t2pc)),
        ]:
            t0 = time.perf_counter()
            fn()
            dt = time.perf_counter() - t0
            results.append({"workload": workload.name, "size_preset": size,
                            "design": dname, "metric": "range_read_ms", "value": dt * 1000})

        # spatial-temporal — Design A pointcloud spatial: we don't have a
        # version, so reuse the per-entity loader with manual bbox scan.
        for dname, fn in [
            ("design_b", lambda: b_reader.pointcloud_spatial_temporal(paths["design_b"][0], paths["design_b"][1], bbox, t_query)),
            ("baseline_wkb", lambda: wkb_reader.pointcloud_spatial_temporal(paths["baseline_wkb"][0], bbox, t_query)),
        ]:
            t0 = time.perf_counter()
            matches, touched, total = fn()
            dt = time.perf_counter() - t0
            results.append({"workload": workload.name, "size_preset": size,
                            "design": dname, "metric": "spatial_temporal_ms", "value": dt * 1000})
            results.append({"workload": workload.name, "size_preset": size,
                            "design": dname, "metric": "spatial_temporal_matches", "value": int(matches)})
            results.append({"workload": workload.name, "size_preset": size,
                            "design": dname, "metric": "row_groups_touched", "value": int(touched)})
            results.append({"workload": workload.name, "size_preset": size,
                            "design": dname, "metric": "row_groups_total", "value": int(total)})

    return results
