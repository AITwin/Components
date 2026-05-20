"""Synthetic workload generators for the four moving-geometry workloads.

Returns workload data in a neutral in-memory representation that each
writer turns into Parquet on its own terms. Fixed random seed by default.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterator

import numpy as np


# ---------------------------------------------------------------------------
# Neutral in-memory representation
# ---------------------------------------------------------------------------

@dataclass
class PolygonFrame:
    t: int                                # ms epoch
    rings: list[list[tuple[float, float]]]


@dataclass
class PolygonEntity:
    entity_id: int
    srid: int
    frames: list[PolygonFrame]            # one polygon per observation time


@dataclass
class PointCloudFrame:
    t: int
    xyz: np.ndarray                       # (N, 3) float64
    intensity: np.ndarray                 # (N,) float32
    classification: np.ndarray            # (N,) int8


@dataclass
class PointCloudEntity:
    entity_id: int
    srid: int
    frames: list[PointCloudFrame]


@dataclass
class Workload:
    name: str
    entities: list                        # PolygonEntity or PointCloudEntity
    interp: int                           # 0 step, 1 linear, 2 discrete
    is_static: bool = False               # tgeometry static


# ---------------------------------------------------------------------------
# Size presets
# ---------------------------------------------------------------------------

SIZE_PRESETS = {
    "small":  dict(entities=50,   timestamps=200,  vertices=20, change_rate=0.05, ppf=500),
    "medium": dict(entities=200,  timestamps=1000, vertices=20, change_rate=0.05, ppf=2000),
    "large":  dict(entities=1000, timestamps=5000, vertices=20, change_rate=0.05, ppf=10000),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ring_around(cx: float, cy: float, r: float, n: int, phase: float = 0.0) -> list[tuple[float, float]]:
    return [
        (cx + r * math.cos(phase + 2 * math.pi * k / n),
         cy + r * math.sin(phase + 2 * math.pi * k / n))
        for k in range(n)
    ]


def _timestamps(n: int, start_ms: int = 1_700_000_000_000, step_ms: int = 1000) -> list[int]:
    return [start_ms + i * step_ms for i in range(n)]


# ---------------------------------------------------------------------------
# Workload 1 — static tgeometry
# ---------------------------------------------------------------------------

def gen_workload1(seed: int = 42, size: str = "small") -> Workload:
    p = SIZE_PRESETS[size]
    rng = np.random.default_rng(seed)
    ts = _timestamps(p["timestamps"])
    entities = []
    for eid in range(p["entities"]):
        cx, cy = float(rng.uniform(-1000, 1000)), float(rng.uniform(-1000, 1000))
        r = float(rng.uniform(5, 50))
        polygon = [_ring_around(cx, cy, r, p["vertices"])]
        frames = [PolygonFrame(t=t, rings=polygon) for t in ts]
        entities.append(PolygonEntity(entity_id=eid, srid=4326, frames=frames))
    return Workload(name=f"w1_static_{size}", entities=entities, interp=0, is_static=True)


# ---------------------------------------------------------------------------
# Workload 2 — fixed-vertex deforming polygon
# ---------------------------------------------------------------------------

def gen_workload2(seed: int = 42, size: str = "small") -> Workload:
    p = SIZE_PRESETS[size]
    rng = np.random.default_rng(seed + 1)
    ts = _timestamps(p["timestamps"])
    entities = []
    for eid in range(p["entities"]):
        cx0, cy0 = float(rng.uniform(-1000, 1000)), float(rng.uniform(-1000, 1000))
        r0 = float(rng.uniform(10, 30))
        vel = rng.normal(0, 0.5, size=2)
        # smooth per-vertex offsets via low-frequency sin/cos
        omega = rng.uniform(0.001, 0.01, size=p["vertices"])
        phase_off = rng.uniform(0, 2 * math.pi, size=p["vertices"])
        amp = rng.uniform(0.5, 3.0, size=p["vertices"])
        frames = []
        for i, t in enumerate(ts):
            cx = cx0 + vel[0] * i
            cy = cy0 + vel[1] * i
            ring = []
            for k in range(p["vertices"]):
                theta = 2 * math.pi * k / p["vertices"]
                r = r0 + amp[k] * math.sin(omega[k] * i + phase_off[k])
                ring.append((cx + r * math.cos(theta), cy + r * math.sin(theta)))
            frames.append(PolygonFrame(t=t, rings=[ring]))
        entities.append(PolygonEntity(entity_id=eid, srid=4326, frames=frames))
    return Workload(name=f"w2_fixed_{size}", entities=entities, interp=1)


# ---------------------------------------------------------------------------
# Workload 3 — variable-vertex deforming polygon
# ---------------------------------------------------------------------------

def gen_workload3(seed: int = 42, size: str = "small") -> Workload:
    p = SIZE_PRESETS[size]
    rng = np.random.default_rng(seed + 2)
    ts = _timestamps(p["timestamps"])
    entities = []
    for eid in range(p["entities"]):
        cx0, cy0 = float(rng.uniform(-1000, 1000)), float(rng.uniform(-1000, 1000))
        r0 = float(rng.uniform(10, 30))
        vel = rng.normal(0, 0.5, size=2)
        base_n = p["vertices"]
        frames = []
        for i, t in enumerate(ts):
            cx = cx0 + vel[0] * i
            cy = cy0 + vel[1] * i
            # vertex count jitters by +/- a few each frame
            jitter = int(rng.integers(-3, 4))
            n = max(6, base_n + jitter)
            # change_rate of vertices get perturbed in radius
            r_arr = np.full(n, r0)
            mask = rng.random(n) < p["change_rate"]
            r_arr = r_arr + mask * rng.normal(0, 2.0, size=n)
            ring = [
                (cx + r_arr[k] * math.cos(2 * math.pi * k / n),
                 cy + r_arr[k] * math.sin(2 * math.pi * k / n))
                for k in range(n)
            ]
            frames.append(PolygonFrame(t=t, rings=[ring]))
        entities.append(PolygonEntity(entity_id=eid, srid=4326, frames=frames))
    return Workload(name=f"w3_variable_{size}", entities=entities, interp=1)


# ---------------------------------------------------------------------------
# Workload 4 — point cloud
# ---------------------------------------------------------------------------

def gen_workload4(seed: int = 42, size: str = "small") -> Workload:
    p = SIZE_PRESETS[size]
    rng = np.random.default_rng(seed + 3)
    # Cap timestamps for point clouds — entity*timestamp*ppf gets huge fast.
    n_ts = min(p["timestamps"], 50 if size == "small" else 100 if size == "medium" else 200)
    ts = _timestamps(n_ts)
    ppf = p["ppf"]
    # Use fewer "entities" (sensors) — each contributes ppf points per frame
    n_entities = max(1, p["entities"] // 10)
    entities = []
    for eid in range(n_entities):
        cx, cy = float(rng.uniform(-1000, 1000)), float(rng.uniform(-1000, 1000))
        frames = []
        for t in ts:
            xyz = rng.normal(0, 50, size=(ppf, 3)).astype(np.float64)
            xyz[:, 0] += cx
            xyz[:, 1] += cy
            intensity = rng.random(ppf).astype(np.float32)
            classification = rng.integers(0, 8, size=ppf, dtype=np.int8)
            frames.append(PointCloudFrame(t=t, xyz=xyz, intensity=intensity, classification=classification))
        entities.append(PointCloudEntity(entity_id=eid, srid=4326, frames=frames))
    return Workload(name=f"w4_pointcloud_{size}", entities=entities, interp=2)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

GENERATORS = {
    "w1": gen_workload1,
    "w2": gen_workload2,
    "w3": gen_workload3,
    "w4": gen_workload4,
}
