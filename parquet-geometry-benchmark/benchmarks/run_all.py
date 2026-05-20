"""Run the full matrix and save results.json."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Allow running as script
sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmarks.harness import benchmark_one


def main(sizes=("small",), workloads=("w1", "w2", "w3", "w4"), append=False):
    out = Path(__file__).parent / "results.json"
    if append and out.exists():
        all_results = json.loads(out.read_text())
        # drop any prior entries for the same (workload-base, size) combos
        keep = []
        new_combos = {(w, s) for w in workloads for s in sizes}
        for r in all_results:
            wb = r.get("workload", "").rsplit("_", 1)[0] if "_" in r.get("workload", "") else r.get("workload", "")
            short = wb.split("_")[0]  # e.g. w1_static -> w1
            if (short, r.get("size_preset")) in new_combos:
                continue
            keep.append(r)
        all_results = keep
    else:
        all_results = []
    for w in workloads:
        for s in sizes:
            t0 = time.perf_counter()
            print(f"[{w}/{s}] starting...", flush=True)
            try:
                r = benchmark_one(w, s)
                all_results.extend(r)
                # Persist incrementally so a crash later doesn't lose work
                out.write_text(json.dumps(all_results, indent=2, default=str))
                print(f"[{w}/{s}] done in {time.perf_counter()-t0:.1f}s, {len(r)} measurements (saved)", flush=True)
            except Exception as exc:
                import traceback; traceback.print_exc()
                all_results.append({
                    "workload": f"{w}_{s}", "size_preset": s, "design": None,
                    "metric": "error", "value": str(exc),
                })
                print(f"[{w}/{s}] FAILED: {exc}", flush=True)
    out.write_text(json.dumps(all_results, indent=2, default=str))
    print(f"wrote {out} ({len(all_results)} entries)")


if __name__ == "__main__":
    args = sys.argv[1:]
    sizes = tuple(a for a in args if a in ("small", "medium", "large")) or ("small",)
    workloads = tuple(a for a in args if a in ("w1", "w2", "w3", "w4")) or ("w1", "w2", "w3", "w4")
    append = "--append" in args
    main(sizes=sizes, workloads=workloads, append=append)
