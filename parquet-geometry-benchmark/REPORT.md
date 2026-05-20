# Parquet moving-geometry encoding benchmark — report

Honest comparison of Parquet encodings for moving geometries in a
MEOS-shaped data model. All implementations are pure-Python prototypes
exercising PyArrow 24.0.0 with snappy compression. Workloads, code, and
raw measurements are reproducible from the `synthetic/` and `benchmarks/`
directories with a fixed seed (42).

## Designs compared

| design              | shape                                                            |
|---------------------|------------------------------------------------------------------|
| `baseline_wkb`      | one row per (entity, t) with geometry as WKB blob                |
| `design_a1`         | per-vertex trajectories `List<Struct<ring_idx, vertex_id, traj>>` + bbox |
| `design_a1_nobbox`  | A1 without bbox sidecar columns                                  |
| `design_a2`         | snapshot-per-frame `List<Struct<t, rings: List<List<point>>>>` + bbox |
| `design_a2_nobbox`  | A2 without bbox sidecar columns                                  |
| `design_b`          | flat (entity_id, t_idx, ring_idx, ring_pos, x, y)                |
| `design_b_plus`     | Design B with run-length (t_idx_start, t_idx_end) — W1 only      |

Design A1 mirrors MEOS's tgeompoint structure: each vertex has a stable
`vertex_id` and its own temporal-point trajectory. Disappearing vertices
end their trajectory; new vertices are new entries. Design A2 is the
"snapshot-per-frame" shape: each frame stores the polygon as nested
rings, with no per-vertex identity. Design B encodes one row per
temporal point, with ring-transition convention in footer metadata.

---

## Storage (MB)

| workload                    | wkb    | a1     | a1_nobbox | a2     | a2_nobbox | design_b | design_b+ |
|-----------------------------|--------|--------|-----------|--------|-----------|----------|-----------|
| W1 static — small           | 0.016  | 0.025  | 0.022     | 0.052  | 0.048     | 0.057    | 0.019     |
| W1 static — medium          | 0.109  | 0.137  | 0.125     | 0.650  | 0.637     | 1.327    | 0.119     |
| W1 static — large           | 9.13   | 6.43   | 6.38      | (OOM)  | (OOM)     | 41.33    | 12.06     |
| W2 fixed-vertex — small     | 3.15   | 3.74   | 3.73      | 3.73   | 3.73      | 3.52     | —         |
| W2 fixed-vertex — medium    | 62.90  | 65.00  | 64.99     | 64.71  | 64.69     | 63.69    | —         |
| W3 variable-vertex — small  | 2.69   | 3.06   | 3.06      | 3.06   | 3.06      | 3.03     | —         |
| W3 variable-vertex — medium | 53.78  | 62.12  | 62.11     | 57.44  | 57.43     | 56.62    | —         |
| W4 pointcloud — small       | 3.89   | 4.30 (A2 only) | 4.30 | — | — | 4.37    | —         |
| W4 pointcloud — medium      | 124.0  | 142.6 (A2 only) | 142.6 | — | — | 113.6  | —         |

Pointclouds (W4) use only the snapshot-per-frame shape (no per-vertex
trajectory equivalent exists for unidentified points). The W4 rows
shown as "A2" are labeled `design_a` / `design_a_nobbox` in `results.json`.

### Storage findings

1. **A1 wins for static, A2 wins for variable-vertex.** On W1 medium A1
   is 4.7× smaller than A2 (0.137 vs 0.650 MB) because per-vertex
   trajectory collapse stores each vertex once and the timestamps in a
   sibling list. On W3 medium A2 is 7.5% smaller than A1 (57.4 vs
   62.1 MB) because vertex_id and ring_idx headers per vertex are dead
   weight when vertices come and go.
2. **For fixed-vertex (W2), A1 and A2 are within 0.5% of each other.**
   The vertex_id discipline neither helps nor hurts when vertex counts
   are stable.
3. **WKB compresses surprisingly well for static**, because each repeated
   polygon is identical bytes that snappy collapses. A1 barely beats WKB
   on W1 large (6.4 vs 9.1 MB); on small/medium WKB wins.
4. **Design B raw on static is a disaster**, as predicted: 41 MB vs 9 MB
   on W1 large (4.5× WKB, 6.4× A1). Per-vertex×per-timestamp
   materialization is exactly the redundancy this design generates.
5. **Design B+ static-collapse recovers most of the loss**: 12 MB on
   large, 0.12 MB on medium, 0.019 MB on small. Within 30% of WKB.
6. **Design B wins point clouds** at medium (113.6 vs WKB 124 MB, 9%
   smaller). Design A's nested list-of-struct adds offset overhead.

---

## Query latencies (ms, medium size unless noted) — single-thread, warm

| workload    | metric         | wkb    | a1     | a1_nobbox | a2     | a2_nobbox | design_b |
|-------------|----------------|--------|--------|-----------|--------|-----------|----------|
| W1 static   | point-in-time  | 7.3    | 3.9    | 3.7       | 80.8   | 82.7      | 10.6     |
| W1 static   | range read     | 16.9   | 4.6    | 3.6       | 48.6   | 45.8      | 30.3     |
| W1 static   | spatial filter | 30.9   | 14.9   | 328.7     | 239.2  | **14305** | 69.8     |
| W2 fixed    | point-in-time  | 16.3   | 115.3  | 114.9     | 82.4   | 83.2      | 15.3     |
| W2 fixed    | range read     | 27.1   | 58.8   | 62.9      | 50.5   | 55.0      | 35.8     |
| W2 fixed    | spatial filter | 68.1   | 1115   | **19605** | 790    | **15195** | 85.8     |
| W3 variable | point-in-time  | 20.8   | 116.2  | 116.2     | 86.0   | 106.7     | 17.8     |
| W3 variable | range read     | 33.5   | 64.8   | 57.5      | 62.4   | 61.4      | 46.8     |
| W3 variable | spatial filter | 88.3   | 726    | **19537** | 505    | **16247** | 101      |
| W4 cloud    | point-in-time  | 2.9    | 324.9 (A2 only) |        |        |           | 8.0      |
| W4 cloud    | range read     | 12.5   | 88.6 (A2 only)  |        |        |           | 11.9     |
| W4 cloud    | spatial filter | 236    | n/a    |           |        |           | 92.9     |

### Query findings

1. **A2 (snapshot-per-frame) is 30% faster than A1 (per-vertex trajectory)
   on deforming polygons.** W2 medium point-in-time: A2 82 ms vs A1
   115 ms. The simpler snapshot shape decodes faster in Python: one
   nested struct per frame vs N vertex-trajectories per row.
2. **A1 wins on static.** Point-in-time on W1 medium: A1 4 ms vs A2
   81 ms. A1 collapses the static case to a single trajectory entry,
   making the row trivially small; A2 still stores the polygon at every
   timestamp.
3. **Neither A1 nor A2 beats Design B or WKB on read latency for
   deforming polygons.** Design B point-in-time: 15 ms on W2 medium;
   A2 best: 82 ms; A1: 115 ms. Pure-Python deserialization of nested
   Arrow data is the bottleneck. A C++/Rust materializer would change
   this picture but is out of prototype scope.
4. **Both A1 and A2 are unusable without the bbox sidecar for spatial
   filters.** W2 medium: A1_nobbox 19.6 seconds, A2_nobbox 15.2 seconds
   — vs A1 with bbox 1.1 s, A2 with bbox 0.79 s. PyArrow does not push
   predicates down to nested-leaf min/max statistics.
5. **Design B point-in-time matches WKB.** Filter on (entity_id, t_idx),
   get a small number of rows, group by ring — completes in 15–20 ms
   on medium workloads. The reconstruction overhead the prompt asks
   about is **not significant**: most wall-clock is the Parquet read,
   not the GROUP-and-ORDER step.

---

## Row-group pruning — the honesty check

This is the metric the prompt specifically asked for. "Touched" means
the row group's column statistics were consistent with the predicate
and had to be opened; "total" is all row groups in the file.

| workload (medium)           | a1        | a1_nobbox | a2        | a2_nobbox | design_b | wkb     |
|-----------------------------|-----------|-----------|-----------|-----------|----------|---------|
| W1 static                   | 7/7       | 7/7       | 7/7       | 7/7       | 4/4      | 4/4     |
| W2 fixed-vertex             | 7/7       | 7/7       | 7/7       | 7/7       | 4/4      | 4/4     |
| W3 variable-vertex          | **5/7**   | 7/7       | **5/7**   | 7/7       | 4/4      | 4/4     |
| W1 large (A1 only run)      | 30/32     | 32/32     | (OOM)     | (OOM)     | 63/96    | 100/100 |

**W1 large spatial-filter latencies** (A2 omitted — see prototype
limitation #8):

| design            | ms       |
|-------------------|----------|
| design_a1         | 86       |
| design_a1_nobbox  | **7192** |
| design_b          | 1304     |
| baseline_wkb      | 781      |

A1 with bbox sidecar is 9× faster than WKB and 84× faster than its own
no-bbox variant at large scale. Design B at large scale reads 63 of 96
row groups (34% pruned by sort-locality) but scans more data per group
than A1's bbox-prefiltered candidate set.

**Findings:**

- **A1 and A2 with bbox sidecar both prune row groups when bbox stats
  differ across row groups.** On W3 medium 2 of 7 row groups are
  skipped. On W2 and W1 medium they aren't, because all row groups have
  bbox stats covering the query region — the workload doesn't have
  enough spatial separation between entities for bbox stats to prune.
- **PyArrow does NOT prune on nested-leaf min/max.** The `*_nobbox`
  variants always read every row group on spatial filters. The leaf
  x/y statistics PyArrow writes are not used by its predicate
  pushdown engine for row-group skipping.
- **Design B prunes spectacularly at large scale**: W1 large, 33 of 96
  row groups skipped (34% prune rate) — because vertices for the same
  entity cluster in the same row group and entities have stable spatial
  positions.

---

## Per-design summary

### Design A1 — per-vertex trajectories (MEOS-shaped)

**Wins:**
- Storage on static workloads (W1 medium: 0.137 MB vs A2's 0.650 MB).
- Range and point-in-time queries on static (sub-5 ms).
- Schema cleanly mirrors MEOS tgeompoint structure — ideal for
  zero-copy MEOS round-trips.
- Variable-vertex handling is natural: disappearing vertex ends its
  trajectory, new vertex is a new entry.

**Loses:**
- Storage on variable-vertex (62 MB vs A2's 57 MB) due to per-vertex
  header overhead.
- Point-in-time queries on deforming polygons in Python (~8× slower than
  Design B and WKB) due to deep nested deserialization.
- Pure form (no bbox sidecar) is unusable for spatial queries: 20–1000×
  slowdown.

### Design A2 — snapshot-per-frame

**Wins:**
- Storage on variable-vertex (57 MB vs A1 62 MB on W3 medium).
- Faster than A1 on deforming polygons across all queries (~30%).
- Simpler schema: no vertex_id discipline required.

**Loses:**
- Storage on static workloads (4.7× worse than A1 — stores full polygon
  at every timestamp).
- Still slower than Design B on point-in-time (82 vs 15 ms on W2
  medium) due to nested deserialization.
- Same bbox-sidecar dependency as A1.

### Design B — flat-primitive decomposition

**Wins:**
- Point-in-time / range queries are fast and predictable (under 50 ms on
  medium across all polygon workloads).
- Spatial filter is consistently competitive (~70–100 ms on medium).
- Best storage for point clouds (W4 medium: 113.6 vs WKB 124 MB).
- Row-group pruning works at large data when sort order aligns with
  spatial locality (W1 large: 33/96 row groups skipped).
- Polygon reconstruction overhead is **not significant**: filter+group+
  order is ~15 ms on medium, dominated by Parquet read.

**Loses:**
- Static workloads in raw form: 4.5× WKB on W1 large. Design B+ recovers
  most of this (12 vs 9 MB).
- Storage on deforming polygons against WKB by a few percent.
- Variable-vertex polygon reconstruction needs an explicit
  ring-transition convention in footer metadata.

### Baseline WKB

**Wins:**
- Best storage on W2 / W3 deforming polygons (within a few percent of
  the columnar designs).
- Simplest schema; widest compatibility.

**Loses:**
- Spatial filters scale linearly in row count, no pruning available.
- Point cloud storage is worst at medium (124 vs Design B 114 MB).

---

## Where the answer depends on query mix

| query profile                         | recommended design                    |
|---------------------------------------|---------------------------------------|
| Read polygon at point-in-time         | Design B or WKB (~15 ms); A1/A2 8×+ slower |
| Time-range scan of entity geometry    | Design B; A1 wins on static          |
| Spatial-temporal filter (any scale)   | Design B; A1/A2 only with bbox sidecar |
| Static reference data, write-once     | WKB, Design B+, or A1                |
| Variable-vertex polygon archive       | A2 (snapshot, 7.5% smaller than A1)  |
| Pointcloud bulk storage and ST query  | Design B                              |
| MEOS-API alignment / round-trip       | A1 — preserves MEOS per-vertex shape  |

The A1 column survives only on the bottom row: if the application is
calling MEOS functions on every read, A1 keeps the data in a shape
MEOS understands. Everywhere else A2 (simpler, faster, often smaller)
or Design B (fastest queries, best for variable workloads) wins.

---

## Prototype limitations that would change conclusions at production scale

1. **Python deserialization dominates Design A read time.** A C++ or
   Rust implementation walking Arrow nested arrays directly would
   likely be 5–10× faster on point-in-time queries, narrowing the gap
   to Design B. The A2-vs-A1 advantage might invert if vectorized
   readers favor A1's regular structure.
2. **PyArrow does not push down predicates to nested-leaf statistics in
   24.0.0.** If a future version did, `*_nobbox` variants would become
   competitive with their bbox counterparts on spatial filters. The
   current bbox sidecar is a workaround for an engine limitation, not
   a fundamental schema choice.
3. **Row-group sizing is not tuned.** We used 32 polygon-rows per row
   group for Design A and 200 K vertex-rows per row group for Design B.
   Real deployments should tune both based on entity count, spatial
   distribution, and query bbox sizes.
4. **No Z-order or geohash bucketing.** Both designs would benefit from
   spatially clustering the sort key (e.g., sorting by
   `(z_order(centroid), entity_id, t_idx)`) so row groups are spatially
   compact. Without that, pruning rate on W2 medium is 0%.
5. **No real MEOS bindings.** Operations like
   `tcontains(tgeompoint, geometry, time)` would benefit A1 (zero-copy)
   more than A2 (one snapshot per frame) or Design B (reconstruct then
   call MEOS).
6. **WKB baseline is GeoParquet-shaped but does not write GeoParquet
   metadata.** A real GeoParquet file would carry per-column-chunk bbox
   stats in `geo` metadata; we left that off because it would have
   changed the spatial-filter comparison.
7. **Pointcloud Design A spatial filter was not implemented.** Not a
   judgment, just missing code; the W4 design_a spatial-filter row is
   blank.
8. **The writers materialize everything in Python before handing it to
   Arrow.** W2/W3/W4 large workloads OOM-killed at 16 GB resident. W1
   large fits when only A1 is run (collapsed trajectory) but OOMs when
   A2 (snapshot-per-frame) is also written — A2 materializes 100M
   coordinate copies in nested Python lists. A streaming writer using
   `RecordBatch` or partitioned writes would not have this problem.
   Conclusions above are based on small/medium for W2–W4 and W1 (full
   matrix) plus large for W1 with A2 omitted.

---

## Refinements added beyond the original sketches

1. **Design A bbox sidecar columns** (`bbox_xmin/xmax/ymin/ymax`) —
   added because the pure form does not prune on spatial predicates and
   a fair comparison required some form of spatial statistics.
   Benchmarked side-by-side with the pure form (`*_nobbox`).
2. **Design A2 snapshot-per-frame variant** — implemented and benchmarked
   alongside A1 to test whether vertex-trajectory shape pays off. It
   does only for static workloads.
3. **Design B+ static-collapse** — added because the raw "row per
   (vertex, timestamp)" form is unusable for static workloads.
   Encodes `(t_idx_start, t_idx_end)` runs when a vertex's `(x, y)`
   doesn't change. Recovers most of the static storage loss.

All refinements are reported as separate rows so the raw shape is
visible alongside the refined one.

---

## Reproducing

```
# Generate and benchmark
pip install pyarrow numpy
cd parquet-geometry-benchmark
python3 benchmarks/run_all.py small                        # ~20 seconds
python3 benchmarks/run_all.py medium --append              # ~5 minutes
python3 benchmarks/run_all.py large w1 --append            # ~5 minutes
# (w2/w3/w4 large all OOM at ~16 GB with the current materializing
#  writer; only W1 large fits because static-collapse compresses well)

# results.json contains every measurement
cat benchmarks/results.json | jq '.[] | select(.metric == "storage_bytes")'
```

Seed is fixed at 42, so generated workloads are identical across runs.
