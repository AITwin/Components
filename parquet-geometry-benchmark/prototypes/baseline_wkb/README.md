# Baseline — WKB-per-row (GeoParquet style)

The "current practice" comparison. One row per (entity, timestamp) with
the geometry serialized as little-endian WKB. No spatial sidecar.

## Polygon schema

```
entity_id   int64
t           timestamp[ms]
geom_wkb    binary
```

Sort: `(entity_id, t)`.

## Pointcloud schema

```
entity_id, t, intensity, classification, geom_wkb (POINT Z)
```

The pointcloud variant is deliberately silly — one WKB blob per point per
timestamp — to show what naive GeoParquet costs vs. the columnar designs.
