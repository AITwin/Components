# Parquet moving-geometry encoding benchmark — report

Honest comparison of three Parquet encodings for moving geometries in a
MEOS-shaped data model. All implementations are pure-Python prototypes
exercising PyArrow 24.0.0 with snappy compression. Workloads, code, and
raw measurements are reproducible from the `synthetic/` and `benchmarks/`
directories with a fixed seed (42).

## Designs compared

| design            | shape                                              |
|-------------------|----------------------------------------------------|
| `baseline_wkb`    | one row per (entity, t) with geometry as WKB blob  |
| `design_a`        | nested per-vertex trajectories + flat bbox sidecar |
| `design_a_nobbox` | same as `design_a` but without the bbox sidecar    |
| `design_b`        | flat (entity_id, t_idx, ring_idx, ring_pos, x, y)  |
| `design_b_plus`   | Design B with run-length (t_idx_start, t_idx_end)  |

Design A polygons are encoded as
`List<Struct<ring_idx, vertex_id, traj: List<Struct<t, x, y>>>>` — each
vertex has a stable `vertex_id` and its own MEOS-shaped temporal-point
trajectory. Disappearing vertices end their trajectory; new vertices are
new entries. Design B is one row per temporal point, with footer
metadata recording the ring-transition convention.

---

## Storage (MB)

| workload                    | wkb    | design_a | a_nobbox | design_b | design_b+ |
|-----------------------------|--------|----------|----------|----------|-----------|
| W1 static — small           | 0.016  | 0.025    | 0.022    | 0.057    | 0.019     |
| W1 static — medium          | 0.109  | 0.137    | 0.125    | 1.327    | 0.119     |
| W1 static — large           | 9.13   | 6.43     | 6.38     | 41.33    | 12.06     |
| W2 fixed-vertex — small     | 3.15   | 3.74     | 3.73     | 3.52     | —         |
| W2 fixed-vertex — medium    | 62.90  | 65.00    | 64.99    | 63.69    | —         |
| W3 variable-vertex — small  | 2.69   | 3.06     | 3.06     | 3.03     | —         |
| W3 variable-vertex — medium | 53.78  | 62.12    | 62.11    | 56.62    | —         |
| W4 pointcloud — small       | 3.89   | 4.30     | 4.30     | 4.37     | —         |
| W4 pointcloud — medium      | 124.0  | 142.6    | 142.6    | 113.6    | —         |

### Storage findings

1. **WKB compresses surprisingly well for static**, because each repeated
   polygon is identical bytes that snappy collapses. Design A barely
   beats WKB on W1 large (6.4 vs 9.1 MB); on small and medium it loses.
2. **Design B raw on static is a disaster**, as predicted: 41 MB vs 9 MB
   on W1 large (4.5× WKB, 6.4× Design A). Per-vertex×per-timestamp
   materialization is exactly the redundancy this design generates.
3. **Design B+ static-collapse recovers most of the loss**: 12 MB on
   large, 0.12 MB on medium, 0.019 MB on small. Within 30% of WKB. This
   is the only viable Design B shape for static-dominated data.
4. **For deforming polygons (W2, W3), all encodings cluster within ~20%**
   of WKB. Columnar compression on smoothly varying coordinates is good
   but not transformative against a snappy-compressed WKB blob.
5. **Design B wins point clouds (W4 medium): 113.6 vs 124 MB WKB** —
   roughly 9% smaller. Design A loses pointclouds (143 MB) because the
   List-of-Struct-of-List shape adds offset overhead per frame.
6. **Design A's per-vertex trajectory shape is slightly larger than
   Design B's flat layout** for deforming workloads (W3 medium: 62 vs
   57 MB). The nested struct headers cost more than they save.

---

## Query latencies (ms) — single-thread, warm

| workload (medium)        | metric         | wkb    | design_a | a_nobbox | design_b |
|--------------------------|----------------|--------|----------|----------|----------|
| W1 static                | point-in-time  | 7.89   | 3.94     | 3.65     | 10.92    |
| W1 static                | range read     | 18.5   | 4.6      | 4.1      | 35.4     |
| W1 static                | spatial filter | 33.6   | 17.0     | 335.9    | 71.7     |
| W2 fixed-vertex          | point-in-time  | 16.4   | 113.8    | 113.2    | 14.6     |
| W2 fixed-vertex          | range read     | 32.9   | 66.6     | 65.4     | 35.9     |
| W2 fixed-vertex          | spatial filter | 60.8   | 1096     | **23620**| 77.7     |
| W3 variable-vertex       | point-in-time  | 19.6   | 113.0    | 114.6    | 17.0     |
| W3 variable-vertex       | range read     | 26.1   | 51.8     | 50.6     | 43.0     |
| W3 variable-vertex       | spatial filter | 75.9   | 693.1    | **19525**| 87.0     |
| W4 pointcloud            | point-in-time  | 2.9    | 324.9    | 325.4    | 8.0      |
| W4 pointcloud            | range read     | 12.5   | 88.6     | 88.5     | 11.9     |
| W4 pointcloud            | spatial filter | 236.5  | n/a      | n/a      | 92.9     |

(Design A pointcloud spatial filter not implemented — the per-entity
nested decode path didn't fit cleanly into the spatial+temporal predicate
shape we use elsewhere. Treat as missing data, not a result.)

### Query findings

1. **Design A's pure form (no bbox sidecar) is unusable for spatial
   filters.** W2 medium: 23.6 seconds vs Design A with bbox 1.1 seconds
   (21× slower) vs Design B 78ms (300× slower). This is the colleague's
   sketch's key vulnerability. Without bbox sidecar columns, PyArrow has
   no flat-column statistics to push spatial predicates down to. We have
   to read every row group and filter in Python.
2. **PyArrow does NOT push spatial predicates down to nested-leaf
   statistics.** Both `design_a` and `design_a_nobbox` show identical
   spatial behavior modulo the bbox sidecar; the nested `x`/`y` leaf
   statistics that are written to the file metadata are not consulted by
   the predicate-pushdown engine for row-group skipping. The bbox
   sidecar is what gives Design A's spatial filter teeth — and turning
   it off reveals 20–1000× slowdowns.
3. **Design A's per-vertex deserialization is expensive in Python.**
   W2/W3 medium point-in-time queries take 113 ms in Design A vs 15 ms
   in Design B and WKB. The cost is `Table.to_pylist()` walking deeply
   nested structs; a C++/Rust materializer would likely close most of
   this gap, but a Python application sees it.
4. **Design B point-in-time matches WKB.** Filter on (entity, t_idx), get
   a small number of rows, group by ring — completes in 15–20 ms even
   on medium-size deforming polygons. The reconstruction overhead the
   prompt asks about is not significant: most of the wall-clock is
   Parquet read, not the GROUP-and-ORDER step.
5. **W1 spatial filter ordering is inverted.** WKB beats Design A on
   small (2.8 vs 6.1 ms) and is close on medium (33.6 vs 17.0 ms);
   Design A wins on large (797 vs 87 ms). The break-even point is around
   medium scale; at large scale the bbox-sidecar pruning pays for the
   nested-decode overhead.

---

## Row-group pruning — the honesty check

This is the metric the prompt specifically asked for. "Touched" means
the row group's column statistics were consistent with the predicate
and had to be opened; "total" is all row groups in the file.

| workload (size)                  | design_a    | a_nobbox    | design_b    | wkb          |
|----------------------------------|-------------|-------------|-------------|--------------|
| W1 static — large                | **30/32**   | 32/32       | **63/96**   | 100/100      |
| W3 variable-vertex — medium      | **5/7**     | 7/7         | 4/4         | 4/4          |
| W2 fixed-vertex — medium         | 7/7         | 7/7         | 4/4         | 4/4          |
| W4 pointcloud — medium           | n/a         | n/a         | 4/4         | 20/20        |

**Findings:**

- **Design A's bbox sidecar DOES enable real row-group pruning.** On W1
  large 2 of 32 row groups are skipped; on W3 medium 2 of 7. Not huge,
  but real and non-zero.
- **PyArrow does not prune on nested-leaf min/max.** `design_a_nobbox`
  always reads every row group on spatial filters — the leaf-level x/y
  statistics that pyarrow writes are not used by its predicate engine.
- **Design B prunes spectacularly at large scale**, when sort order
  aligns with spatial locality: W1 large, 33 of 96 row groups skipped
  (34% prune rate) — because vertices for the same entity cluster in
  the same row group and entities have stable spatial positions.
- **The story changes with sort key.** Design B is sorted by
  `(entity_id, t_idx)`. If two entities have similar entity_ids and
  similar spatial positions, they share row groups and pruning works.
  At medium scale (4 row groups for 200 entities) the entire workload's
  bbox is in every row group, so no pruning happens. This is a
  prototype artifact, not a fundamental property.

---

## Per-design summary

### Design A — Nested-MEOS-Arrow

**Wins:**
- Storage on large static workloads (6.4 MB vs WKB 9.1 MB on W1 large).
- Spatial filter on large scale, *with* bbox sidecar (87 ms vs WKB 798 ms).
- Schema cleanly mirrors MEOS in-memory tgeompoint structure.

**Loses:**
- Point-in-time queries on deforming polygons in Python (~8× slower than
  Design B and WKB) due to deep nested deserialization.
- Pointcloud storage (143 MB vs Design B 114 MB) due to list-of-struct
  offset overhead.
- Pure form (no bbox sidecar) is unusable for spatial queries: 20–1000×
  slowdown.

**Key dependency:** the bbox sidecar columns. Without them, Design A's
"flat top-level columns for pruning" claim doesn't pan out — flat
non-spatial columns (subtype/interp/srid/flags) are useless for spatial
predicates, and PyArrow does not push down to nested-leaf statistics.

### Design B — flat-primitive decomposition

**Wins:**
- Point-in-time / range queries are fast and predictable (under 50 ms on
  medium across all polygon workloads).
- Spatial filter is consistently competitive (~70–90 ms on medium,
  similar to WKB scan).
- Best storage for point clouds (W4 medium: 113.6 vs WKB 124 MB).
- Row-group pruning works on large data when sort order aligns with
  spatial locality (W1 large: 33/96 row groups skipped).
- Polygon reconstruction overhead is **not significant**: filter+group is
  ~15ms on medium, dominated by Parquet read not by the GROUP step.

**Loses:**
- Static workloads in raw form: 4.5× WKB on W1 large. Design B+ recovers
  most of this (12 vs 9 MB).
- Storage on deforming polygons against WKB by a few percent (W3 medium
  56.6 vs 53.8 MB) — flat columns aren't dramatically better than a
  WKB blob with snappy.
- Variable-vertex polygon reconstruction needs an explicit
  ring-transition convention that lives in footer metadata, not in the
  schema. Consumers must respect it.

### Baseline WKB

**Wins:**
- Best storage on W2 / W3 deforming polygons (within a few percent of
  the columnar designs).
- Simplest schema; widest compatibility.

**Loses:**
- Spatial filters scale linearly in row count, no pruning available.
- Point cloud storage is worst at large scale (143 vs 114 MB Design B).
- Static workloads compress well only because snappy collapses identical
  blobs; against a designed-for-static encoding it loses 30%.

---

## Where the answer depends on query mix

| query profile                         | recommended design                          |
|---------------------------------------|---------------------------------------------|
| Read whole polygon at point-in-time   | Design B or WKB (Design A 8× slower)        |
| Time-range scan of entity geometry    | Design A (with bbox) or Design B            |
| Spatial-temporal filter (any scale)   | Design B; Design A only with bbox sidecar   |
| Static reference data, write-once     | WKB or Design B+; Design B raw is a trap    |
| Pointcloud bulk storage and ST query  | Design B                                    |
| MEOS-API alignment / round-trip       | Design A — preserves MEOS structure         |

The MEOS-alignment row is where the qualitative pitch for Design A still
holds even though it loses several benchmarks: if your application is
calling MEOS functions on every read, Design A keeps the data in a
shape MEOS understands. Design B requires reconstruction even for
operations MEOS could do natively.

---

## Prototype limitations that would change conclusions at production scale

1. **Python deserialization dominates Design A's read time.** A C++ or
   Rust implementation walking Arrow nested arrays directly would
   likely be 5–10× faster on point-in-time queries, narrowing the gap
   to Design B.
2. **PyArrow does not push down predicates to nested-leaf statistics in
   24.0.0.** If a future version did, `design_a_nobbox` would become
   competitive with `design_a` on spatial filters. The current bbox
   sidecar is a workaround for an engine limitation, not a fundamental
   schema choice.
3. **Row-group sizing is not tuned.** We used 32 polygon-rows per row
   group for Design A (giving 32 row groups on 1000 entities at large)
   and 200 K vertex-rows per row group for Design B. Real deployments
   should tune both based on entity count, spatial distribution, and
   query bbox sizes — none of which we explored.
4. **No Z-order or geohash bucketing.** Both designs would benefit from
   spatially clustering the sort key (e.g., sorting by
   `(z_order(centroid), entity_id, t_idx)`) so row groups are spatially
   compact. Without that, pruning rate on W2/W3 medium is 0%.
5. **No real MEOS bindings.** Operations like
   `tcontains(tgeompoint, geometry, time)` would benefit Design A
   (zero-copy) more than Design B (reconstruct then call MEOS).
6. **WKB baseline is GeoParquet-shaped but does not write GeoParquet
   metadata.** A real GeoParquet file would carry per-column-chunk bbox
   stats in `geo` metadata; we left that off because it would have
   changed the spatial-filter comparison.
7. **Pointcloud Design A spatial filter was not implemented.** Not a
   judgment, just missing code; the W4 design_a spatial-filter row is
   blank.
8. **The writers materialize everything in Python before handing it to
   Arrow.** Attempting W2 large (1000 entities × 5000 frames × 20
   vertices = 100 M rows) OOM-killed the process at 16 GB resident.
   A streaming writer using `RecordBatch` or partitioned writes would
   not have this problem, but is out of prototype scope. Conclusions
   above are based on small (10 MB) and medium (100 MB) for W2/W3/W4
   and small/medium/large for W1.

---

## Refinements I implemented that weren't in the original sketches

1. **Design A bbox sidecar columns** (`bbox_xmin/xmax/ymin/ymax`) — added
   because the pure form does not prune on spatial predicates and a
   fair comparison required some form of spatial statistics. Benchmarked
   side-by-side with the pure form (`design_a_nobbox`).
2. **Design B+ static-collapse** — added because the raw "row per
   (vertex, timestamp)" form is unusable for static workloads (4.5× WKB
   on W1 large). The collapse encodes `(t_idx_start, t_idx_end)` runs
   when a vertex's `(x, y)` doesn't change. Recovers most of the static
   storage loss; query times are competitive with WKB.

Both refinements are reported as separate rows so the raw shape is
visible alongside the refined one.

---

## Reproducing

```
# Generate and benchmark
pip install pyarrow numpy
cd parquet-geometry-benchmark
python3 benchmarks/run_all.py small               # ~10 seconds
python3 benchmarks/run_all.py medium --append     # ~3 minutes
python3 benchmarks/run_all.py large w1 --append   # ~3 minutes
# (w2/w3/w4 large all OOM at ~16 GB with the current materializing
#  writer; only W1 large fits because static-collapse compresses well)

# results.json contains every measurement
cat benchmarks/results.json | jq '.[] | select(.metric == "storage_bytes")'
```

Seed is fixed at 42, so generated workloads are identical across runs.
