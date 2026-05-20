# Design A — Nested-MEOS-Arrow

Polygons are encoded as per-vertex trajectories — each vertex has a stable
`vertex_id` within its ring, and its own trajectory `List<Struct<t, x, y>>`.
This mirrors MEOS's tgeompoint structure. Variable vertex counts are
handled naturally: vertices that disappear just end their trajectory,
vertices that appear are new entries.

## Polygon row layout

```
entity_id     int64
subtype       int8
interp        int8
srid          int32
flags         int32
t_min/t_max   timestamp[ms]
bbox_*        float64           -- optional sidecar (with_bbox=True)
observations  List<timestamp>   -- populated only for static workload
vertices      List<Struct<
                ring_idx  : int16,
                vertex_id : int32,
                traj      : List<Struct<t, x, y>>
              >>
```

## Pointcloud row layout

```
entity_id, subtype, interp, srid, flags, t_min, t_max, bbox_*
frames : List<Struct<
            t              : timestamp[ms],
            x, y, z        : List<float64>     -- parallel arrays
            intensity      : List<float32>,
            classification : List<int8>
         >>
```

## Variants benchmarked

- `design_a` — with `bbox_*` sidecar columns
- `design_a_nobbox` — pure form without sidecar
