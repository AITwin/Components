"""Run W1 large without A2 (which OOMs at this scale due to Python-list
materialization in the snapshot writer). Appends results to results.json."""

from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from synthetic.workloads import GENERATORS
from prototypes.design_a import writer as a_writer
from prototypes.design_a import reader as a_reader
from prototypes.design_b import writer as b_writer
from prototypes.design_b import reader as b_reader
from prototypes.baseline_wkb import writer as wkb_writer
from prototypes.baseline_wkb import reader as wkb_reader

DATA = Path(__file__).parent.parent / "data"
DATA.mkdir(exist_ok=True)

workload = GENERATORS["w1"](seed=42, size="large")
size = "large"
base = DATA / workload.name
results = []

paths = {
    "baseline_wkb": [f"{base}.wkb.parquet"],
    "design_a1": [f"{base}.a1.parquet"],
    "design_a1_nobbox": [f"{base}.a1_nobbox.parquet"],
    "design_b": [f"{base}.b.main.parquet", f"{base}.b.timeline.parquet"],
    "design_b_plus": [f"{base}.bplus.main.parquet", f"{base}.bplus.timeline.parquet"],
}

n_rows_total = sum(len(e.frames) for e in workload.entities)

# write
runs = {
    "baseline_wkb": lambda p: wkb_writer.write_polygon_workload(workload, p[0]),
    "design_a1": lambda p: a_writer.write_polygon_workload(workload, p[0], with_bbox=True),
    "design_a1_nobbox": lambda p: a_writer.write_polygon_workload(workload, p[0], with_bbox=False),
    "design_b": lambda p: b_writer.write_polygon_workload(workload, p[0], p[1]),
    "design_b_plus": lambda p: b_writer.write_polygon_workload_plus(workload, p[0], p[1]),
}
sizes_by_design = {}
for d, fn in runs.items():
    ps = paths[d]
    for p in ps:
        if os.path.exists(p):
            os.remove(p)
    t0 = time.perf_counter(); fn(ps); dt = time.perf_counter() - t0
    sz = sum(os.path.getsize(p) for p in ps if os.path.exists(p))
    sizes_by_design[d] = sz
    print(f"[{d}] {dt:.1f}s  {sz/1024/1024:.2f}MB")
    results.append({"workload": workload.name, "size_preset": size, "design": d, "metric": "storage_bytes", "value": sz})
    results.append({"workload": workload.name, "size_preset": size, "design": d, "metric": "write_time_s", "value": dt})
    results.append({"workload": workload.name, "size_preset": size, "design": d, "metric": "write_rows_per_s", "value": n_rows_total / dt if dt > 0 else None})

# compression ratio
wkb_sz = sizes_by_design["baseline_wkb"]
for d, sz in sizes_by_design.items():
    if d == "baseline_wkb": continue
    results.append({"workload": workload.name, "size_preset": size, "design": d, "metric": "compression_ratio_vs_wkb", "value": wkb_sz / sz if sz else None})

# queries
rng = random.Random(123)
ents = [e.entity_id for e in rng.sample(workload.entities, 30)]
times = [rng.choice(workload.entities[0].frames).t for _ in range(30)]

# point-in-time
for dname, fn in [
    ("design_a1", lambda eid, t: a_reader.materialize_at_time(paths["design_a1"][0], eid, t, is_static=True)),
    ("design_a1_nobbox", lambda eid, t: a_reader.materialize_at_time(paths["design_a1_nobbox"][0], eid, t, is_static=True)),
    ("design_b", lambda eid, t: b_reader.materialize_polygon(paths["design_b"][0], paths["design_b"][1], eid, t, plus=False)),
    ("design_b_plus", lambda eid, t: b_reader.materialize_polygon(paths["design_b_plus"][0], paths["design_b_plus"][1], eid, t, plus=True)),
    ("baseline_wkb", lambda eid, t: wkb_reader.materialize_at_time(paths["baseline_wkb"][0], eid, t)),
]:
    t0 = time.perf_counter()
    for eid, t in zip(ents, times):
        fn(eid, t)
    dt = (time.perf_counter() - t0) / 30
    results.append({"workload": workload.name, "size_preset": size, "design": dname, "metric": "point_in_time_ms", "value": dt * 1000})
    print(f"  pit {dname} {dt*1000:.2f}ms")

# range
all_t = sorted(set(f.t for e in workload.entities for f in e.frames))
t1 = all_t[len(all_t)//2 - len(all_t)//20]
t2 = all_t[len(all_t)//2 + len(all_t)//20]
for dname, fn in [
    ("design_a1", lambda: a_reader.range_read(paths["design_a1"][0], t1, t2)),
    ("design_a1_nobbox", lambda: a_reader.range_read(paths["design_a1_nobbox"][0], t1, t2)),
    ("design_b", lambda: b_reader.range_read(paths["design_b"][0], paths["design_b"][1], t1, t2, plus=False)),
    ("design_b_plus", lambda: b_reader.range_read(paths["design_b_plus"][0], paths["design_b_plus"][1], t1, t2, plus=True)),
    ("baseline_wkb", lambda: wkb_reader.range_read(paths["baseline_wkb"][0], t1, t2)),
]:
    t0 = time.perf_counter(); fn(); dt = time.perf_counter() - t0
    results.append({"workload": workload.name, "size_preset": size, "design": dname, "metric": "range_read_ms", "value": dt * 1000})

# spatial
ent0 = workload.entities[len(workload.entities)//2]; f0 = ent0.frames[len(ent0.frames)//2]
cx = sum(p[0] for r in f0.rings for p in r)/sum(len(r) for r in f0.rings)
cy = sum(p[1] for r in f0.rings for p in r)/sum(len(r) for r in f0.rings)
bbox = (cx-50, cy-50, cx+50, cy+50); tq = f0.t
for dname, fn in [
    ("design_a1", lambda: a_reader.spatial_temporal_filter(paths["design_a1"][0], bbox, tq, with_bbox=True, is_static=True)),
    ("design_a1_nobbox", lambda: a_reader.spatial_temporal_filter(paths["design_a1_nobbox"][0], bbox, tq, with_bbox=False, is_static=True)),
    ("design_b", lambda: b_reader.spatial_temporal_filter(paths["design_b"][0], paths["design_b"][1], bbox, tq, plus=False)),
    ("baseline_wkb", lambda: wkb_reader.spatial_temporal_filter(paths["baseline_wkb"][0], bbox, tq)),
]:
    t0 = time.perf_counter(); matches, touched, total = fn(); dt = time.perf_counter() - t0
    results.append({"workload": workload.name, "size_preset": size, "design": dname, "metric": "spatial_temporal_ms", "value": dt * 1000})
    results.append({"workload": workload.name, "size_preset": size, "design": dname, "metric": "spatial_temporal_matches", "value": int(matches)})
    results.append({"workload": workload.name, "size_preset": size, "design": dname, "metric": "row_groups_touched", "value": int(touched)})
    results.append({"workload": workload.name, "size_preset": size, "design": dname, "metric": "row_groups_total", "value": int(total)})
    print(f"  sf {dname} {dt*1000:.2f}ms  match={matches} rg={touched}/{total}")

# append to results.json
out = Path(__file__).parent / "results.json"
prior = json.loads(out.read_text())
# drop any prior W1 large entries
prior = [r for r in prior if not (r.get("workload") == workload.name and r.get("size_preset") == "large")]
prior.extend(results)
out.write_text(json.dumps(prior, indent=2, default=str))
print(f"appended {len(results)} entries; total now {len(prior)}")
