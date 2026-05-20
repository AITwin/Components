# Design B — flat-primitive decomposition

Every row is a temporal point. Polygons are reconstructed by filtering on
(entity_id, t_idx) and ordering by (ring_idx, ring_pos). Per-entity
timeline lives in a sibling file mapping integer indices to timestamps.

## Main table (polygons)

```
entity_id  int64
t_idx      int32
ring_idx   int16    -- 0 = exterior, 1.. = holes
ring_pos   int32    -- vertex order within the ring
x, y       float64
```

Sort key: `(entity_id, t_idx, ring_idx, ring_pos)`. Ring transition
convention recorded in footer metadata.

## Main table (Design B+ static-collapse)

```
entity_id, ring_idx, ring_pos, x, y
t_idx_start, t_idx_end int32   -- inclusive run of t_idx where (x,y) holds
```

Identical (x, y) values for consecutive t_idx are run-length-encoded.
Identical to Design B for fully-deforming workloads, much smaller for
static workloads.

## Timeline sibling table

```
entity_id  int64
t_idx      int32
t          timestamp[ms]
```

## Pointcloud main table

```
entity_id, t_idx, x, y, z, intensity, classification
```

`ring_idx` / `ring_pos` omitted entirely — they are null for point clouds.

## Footer metadata

```
design           = "B"
ring_transition  = "explicit_ring_idx,monotonic_ring_pos,gaps_allowed"
sort             = "entity_id,t_idx,ring_idx,ring_pos"
```
