# Design note — schemas before implementation

This is the sanity-check artifact requested by the prompt. Two encodings
(Design A: Nested-MEOS-Arrow; Design B: Flat-primitive decomposition) plus
a WKB baseline, applied to four synthetic workloads. Implementation has
not started yet.

Throughout, `point2d` is shorthand for `Struct<x: float64, y: float64>` and
`point3d` adds `z: float64`. Timestamps are `timestamp[ms]`. Entity IDs
are `int64`.

---

## Common top-level pruning columns (Design A)

To give Parquet's row-group statistics something flat to filter on, every
Design A file carries these as plain top-level columns even when the
information is also recoverable from the nested payload:

| column        | type    | purpose                                  |
|---------------|---------|------------------------------------------|
| `entity_id`   | int64   | per-entity selection                     |
| `subtype`     | int8    | 1=instant, 2=sequence, 3=sequenceset     |
| `interp`      | int8    | 0=step, 1=linear, 2=discrete             |
| `srid`        | int32   | spatial reference id                     |
| `flags`       | int32   | MEOS-style bitfield (z, T, geodetic, …)  |
| `t_min`       | ts[ms]  | min observation timestamp for this row   |
| `t_max`       | ts[ms]  | max observation timestamp for this row   |
| `bbox_xmin/xmax/ymin/ymax` | float64 | per-row aggregate bbox       |

The bbox columns are the "refinement" the prompt mentions for Design A: a
sidecar that lets row-group min/max stats actually express a spatial
filter, since stats on nested leaves are unlikely to be used for pushdown
by current PyArrow. We will benchmark Design A both **with** and
**without** the bbox sidecar so the difference is visible.

---

## Workload 1 — `tgeometry` static

Fixed polygon per entity, observed at many timestamps. No vertex motion.

### Design A schema

```
entity_id        : int64
subtype, interp, srid, flags, t_min, t_max, bbox_*  (as above)
static_geometry  : Struct<
                     rings: List<List<point2d>>      -- the polygon, stored once
                   >
observations     : List<timestamp[ms]>               -- when it was seen
```

One row per entity. The static geometry is materialized once per entity;
observations are a flat list of timestamps. This is the encoding's best
case for redundancy savings vs. WKB-per-row.

### Design B schema

```
-- main table, one row per (vertex × observation timestamp)
entity_id    : int64
t_idx        : int32        -- index into per-entity timeline
ring_idx     : int16        -- 0 = exterior ring, 1.. = holes
ring_pos     : int32        -- vertex order within the ring
x, y         : float64

-- sibling timeline table
entity_id    : int64
t_idx        : int32
t            : timestamp[ms]
```

Sort key: `(entity_id, t_idx, ring_idx, ring_pos)`. Static polygons are
the worst case for Design B by construction: every (vertex, timestamp)
pair is materialized. We will report this honestly rather than special-
casing it. A flagged variant ("Design B+ static-collapse") that records
each vertex once with `(t_idx_start, t_idx_end)` is *not* part of the
core benchmark but I will sketch it in the report if results warrant.

### Baseline (WKB)

```
entity_id    : int64
t            : timestamp[ms]
geom_wkb     : binary       -- the full polygon, serialized per row
```

---

## Workload 2 — Fixed-vertex deforming geometry

Polygons with a constant vertex count whose vertex positions move smoothly
over time.

### Design A schema

```
entity_id, subtype, interp, srid, flags, t_min, t_max, bbox_*
vertex_count : int32                                 -- constant per entity
frames       : List<Struct<
                  t      : timestamp[ms],
                  rings  : List<List<point2d>>       -- the polygon at time t
               >>
```

One row per entity, one inner list element per keyframe. This is the
"List<Struct<t, value>>" shape from the prompt with `value` materialized
as the nested ring/point structure.

### Design B schema — same as Workload 1

```
entity_id, t_idx, ring_idx, ring_pos, x, y
```

Vertex identity is encoded by `(ring_idx, ring_pos)`: the vertex at
position 5 of ring 0 at t_idx=10 is the "same" vertex as position 5 of
ring 0 at t_idx=11 — that's how trajectories are recovered. Fixed vertex
count means `ring_pos` ranges are stable across frames.

### Baseline (WKB) — same as Workload 1

One row per (entity, timestamp) with the polygon serialized as WKB.

---

## Workload 3 — Variable-vertex deforming geometry

Polygons that gain and lose vertices at keyframes. This is the workload
Design B was motivated by.

### Design A schema — same shape as Workload 2

```
frames : List<Struct<t, rings: List<List<point2d>>>>
```

The inner `rings` simply has a different length per frame. Nothing in the
schema forces vertex count to be constant.

### Design B schema

Same flat schema as Workload 2. When a vertex disappears at frame k, no
row exists for that `(entity_id, t_idx=k, ring_idx, ring_pos)`. When a
new vertex appears, a new `ring_pos` is introduced. Reconstruction at
time t filters to the timestamps surrounding t, groups by ring, orders by
`ring_pos`.

**Honest caveat I want to surface up front:** Design B's reconstruction
needs a ring-transition convention so it can tell "this is ring 0 of the
polygon at t" from "this is a different ring of the polygon at t". I'll
record this in Parquet footer metadata as the prompt says, with the
convention being: `ring_idx` is explicit, `ring_pos` is monotone within
`(entity_id, t_idx, ring_idx)`, and gaps in `ring_pos` are tolerated
(vertex deletions). The first benchmark will use that.

### Baseline (WKB) — same as Workload 1

---

## Workload 4 — Point cloud

Many points per timestamp, no vertex identity, optional intensity and
classification attributes.

### Design A schema

```
entity_id, subtype, interp, srid, flags, t_min, t_max, bbox_*
frames : List<Struct<
            t              : timestamp[ms],
            points         : List<point3d>,
            intensity      : List<float32>,    -- parallel to points
            classification : List<int8>        -- parallel to points
         >>
```

The parallel lists keep per-point attributes co-located with coordinates
within a frame. No vertex identity across frames is implied.

### Design B schema

```
entity_id      : int64        -- "frame id" or sensor id
t_idx          : int32
x, y, z        : float64
ring_idx       : null
ring_pos       : null
intensity      : float32
classification : int8
```

ring_idx and ring_pos are null for the entire point-cloud table — that
column is the convention the prompt names for distinguishing trajectory
points from polygon vertices.

### Baseline (WKB)

```
entity_id, t, intensity, classification, geom_wkb (POINT)
```

One row per point per timestamp, with each point's coordinates serialized
as a small WKB POINT. This is genuinely silly for point clouds but it's
what "current practice" via GeoParquet looks like, so it stays.

---

## Generator parameter table

Each workload is parameterized identically so size targets are
predictable. Defaults:

| param                | small (~10 MB) | medium (~100 MB) | large (~1 GB) |
|----------------------|----------------|------------------|---------------|
| entities             | 50             | 200              | 1000          |
| timestamps / entity  | 200            | 1000             | 5000          |
| vertices / polygon   | 20             | 20               | 20            |
| change rate (W3)     | 0.05           | 0.05             | 0.05          |
| points / frame (W4)  | 500            | 2000             | 10000         |
| random seed          | 42             | 42               | 42            |

Sizes are approximate (post-WKB-baseline) and will be tuned once the
first round of writers exists. The seed is fixed so the same workload
is reproducible across designs.

---

## Benchmarks I will run

Per (design × workload × size):

1. **Storage**: file size + per-column-chunk size (via `ParquetFile.metadata`).
2. **Write throughput**: rows-per-second, single thread, warm cache.
3. **Point-in-time read**: materialize one entity's geometry at a given t,
   averaged over many random (entity, t) draws.
4. **Range read**: all entities, time range [t1, t2].
5. **Spatio-temporal filter**: entities whose bbox intersects B at time t.
   - Reported alongside **row groups read vs. skipped**, taken from
     `ParquetFile.metadata.row_group(i).column(j).statistics`. This is
     the honesty check the prompt calls out.
6. **Polygon reconstruction**: materialize the polygon at a given t for
   Design B (Design A gets it for free; for the comparison I'll still
   wall-clock both).

For Design A I will run benchmark 5 **twice** — once relying only on
nested leaf stats, once with the flat bbox sidecar columns — so we can
see whether PyArrow actually prunes on nested leaves or only on flat
columns. That's the empirical question that decides whether Design A's
"flat top-level columns for pruning" claim survives.

---

## What I am NOT building

- A real MEOS binding. The prototypes simulate temporal-geometry semantics
  in pure Python. The schemas above are MEOS-shaped but the implementation
  doesn't link MEOS.
- WKB-plus-sidecar hybrids. The prompt says to isolate the Arrow tier.
- Production-grade ring topology. Holes are allowed (`ring_idx >= 1`) but
  self-intersecting / multi-polygon cases are out of scope.
- Multi-threaded write or async readers. Single-thread numbers only.

---

## Resolved sanity-check decisions

1. **Design A polygon shape: per-vertex trajectories.** Each polygon
   entity is `List<Struct<ring_idx, vertex_id, traj: List<Struct<t, x, y>>>>`.
   `vertex_id` is stable across frames. Variable-vertex is handled
   naturally: vertices that disappear just end their trajectory, vertices
   that appear are new entries. This mirrors MEOS's tgeompoint structure.
   For static (Workload 1) each vertex has a single-entry trajectory and
   the observation timeline lives in a sibling `observations` column.

2. **Design A bbox sidecar: benchmark both.** Pure form vs. with per-row
   `bbox_*` columns will both be measured. The pure form is the honest
   "preserves MEOS structure" version; the sidecar form is the refined
   variant.

3. **Design B+ static-collapse: implemented and labeled.** Workload 1 gets
   both the raw Design B (one row per vertex×timestamp) and Design B+
   (one row per vertex with `t_idx_start..t_idx_end`). They appear as
   separate rows in the results table.
