# Parquet moving-geometry encoding benchmark

Prototype comparison of three Parquet encodings for MEOS-shaped moving
geometries:

- **Design A** (`prototypes/design_a/`) — Nested-MEOS-Arrow, per-vertex
  trajectories with optional bbox sidecar.
- **Design B** (`prototypes/design_b/`) — Flat-primitive decomposition,
  one row per temporal point. Includes a `Design B+` static-collapse
  variant.
- **Baseline WKB** (`prototypes/baseline_wkb/`) — GeoParquet-style
  one-row-per-(entity,timestamp) with geometry as WKB.

## Layout

```
parquet-geometry-benchmark/
├── DESIGN_NOTE.md       initial schemas + resolved sanity-check decisions
├── REPORT.md            full results, findings, and limitations
├── prototypes/
│   ├── design_a/        nested-MEOS-Arrow writer + reader
│   ├── design_b/        flat-primitive writer + reader
│   └── baseline_wkb/    WKB baseline writer + reader
├── synthetic/           four parameterized workload generators (seed=42)
├── benchmarks/          harness + run_all.py; writes results.json
└── data/                generated parquet files (gitignored)
```

## Running

```bash
pip install pyarrow numpy
python3 benchmarks/run_all.py small               # ~10s
python3 benchmarks/run_all.py medium --append     # ~3min
python3 benchmarks/run_all.py large w1 --append   # ~3min (only w1 fits in RAM)
```

Results land in `benchmarks/results.json`. See `REPORT.md` for the
synthesized comparison and findings.
