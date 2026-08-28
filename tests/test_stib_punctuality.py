"""The STIB punctuality harvester, against a day of real observations.

The reconstruction it wraps is exercised by its own suite; what these check is
the seam — that a day of collector snapshots and the two declared dependencies
turn into the same table the reference build produces, and that the columns a
consumer relies on mean what the documentation says they mean.

The fixtures are the cached inputs of that reference build, sliced down to a few
lines so the suite stays cheap — a whole service day is roughly two million
observations and several gigabytes, which is a build, not a test. The full-day
comparison against the reference output is opt-in via STIB_FULL_DAY=1.

Where the fixtures are absent the tests skip rather than fail, so a checkout
without them is not a broken suite.
"""
import io
import json
import os
import sys
import zipfile
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REFERENCE = os.path.expanduser("~/Documents/Dev/CoDE/STIBRealtime")
CACHE = os.path.join(REFERENCE, ".cache")
DAY = date(2026, 8, 27)
STAMP = DAY.strftime("%Y%m%d")

OBS = os.path.join(CACHE, f"vehicle-distance-stib-{STAMP}.parquet")
GTFS = os.path.join(CACHE, f"gtfs-stib-{STAMP}.zip")
SEGMENTS = os.path.join(CACHE, f"stib-segments-{STAMP}.parquet")
EXPECTED = os.path.join(REFERENCE, "results", f"punctuality-stib-{STAMP}.parquet")

pytestmark = pytest.mark.skipif(
    not all(os.path.exists(p) for p in (OBS, GTFS, EXPECTED)),
    reason="reference day not cached; run STIBRealtime's build first",
)


# Enough lines to exercise tracking, merging and the metro's coarse positions
# without carrying the whole fleet through the pipeline.
SAMPLE_LINES = {"1", "5", "92", "71"}
FULL_DAY = os.environ.get("STIB_FULL_DAY") == "1"


def snapshots():
    """Rebuild the collector's output from the flattened cache.

    The cache was written from exactly these four fields, so regrouping it by
    timestamp reproduces what the collector stored per poll.
    """
    obs = pd.read_parquet(OBS)
    if not FULL_DAY:
        obs = obs[obs.line_id.isin(SAMPLE_LINES)]
    out = []
    for stamp, group in obs.groupby("ts", sort=True):
        out.append(SimpleNamespace(
            date=stamp.to_pydatetime(),
            data=[{"lineId": r.line_id, "directionId": r.direction_id,
                   "pointId": r.point_id, "distanceFromPoint": int(r.distance_from_point)}
                  for r in group.itertuples()],
        ))
    return out


def dependencies():
    gtfs = SimpleNamespace(data=open(GTFS, "rb").read())
    if os.path.exists(SEGMENTS):
        frame = pd.read_parquet(SEGMENTS)
        features = [{"type": "Feature",
                     "geometry": {"type": "LineString",
                                  "coordinates": json.loads(r.geometry)},
                     "properties": {k: getattr(r, k) for k in frame.columns
                                    if k not in ("geometry", "length_m")}}
                    for r in frame.itertuples()]
        payload = {"type": "FeatureCollection", "features": features}
    else:
        payload = {"type": "FeatureCollection", "features": []}
    return gtfs, SimpleNamespace(data=json.dumps(payload).encode())


@pytest.fixture(scope="module")
def built():
    from components.stib.harvesters.punctuality import STIBPunctualityHarvester
    gtfs, segments = dependencies()
    blob = STIBPunctualityHarvester().run(snapshots(), gtfs, segments)
    assert blob, "harvester produced nothing"
    return pd.read_parquet(io.BytesIO(blob))


@pytest.fixture(scope="module")
def expected():
    return pd.read_parquet(EXPECTED)


def test_matches_the_reference_on_the_sampled_lines(built, expected):
    """Every reconstructed call agrees with the reference build for its trip.

    The slice cannot reproduce the whole day, but each trip it does recover must
    carry the same times as the full build gave that trip — a wrong answer on a
    subset is still a wrong answer.
    """
    key = ["trip_id", "stop_sequence"]
    ref = expected.set_index(key)
    shared = built.set_index(key).index.intersection(ref.index)
    assert len(shared) > 500, f"only {len(shared)} shared calls to compare"
    a = built.set_index(key).loc[shared].sort_index()
    b = ref.loc[shared].sort_index()
    for column in ("stop_id", "route_id"):
        assert a[column].equals(b[column]), f"{column} differs"
    delta = (a.arrival_delay.astype("Float64") - b.arrival_delay.astype("Float64")).abs()
    assert delta.max(skipna=True) == 0, f"arrival_delay differs by up to {delta.max()}s"


def test_schema_matches_the_other_operators(built):
    """The 14 official punctuality columns, in order, before any extras."""
    official = ["trip_id", "start_date", "start_time", "stop_sequence", "stop_id",
                "route_id", "direction_id", "trip_schedule_relationship",
                "arrival_time", "arrival_delay", "departure_time",
                "departure_delay", "stop_schedule_relationship", "cancelled"]
    assert list(built.columns)[:len(official)] == official


@pytest.mark.skipif(not FULL_DAY, reason="set STIB_FULL_DAY=1 to compare a whole day")
def test_reproduces_the_reference_build(built, expected):
    """Same trips, same stop calls, same times as the command-line build."""
    assert len(built) == len(expected)
    key = ["trip_id", "stop_sequence"]
    a = built.sort_values(key).reset_index(drop=True)
    b = expected.sort_values(key).reset_index(drop=True)
    for column in ("trip_id", "stop_id", "route_id", "stop_sequence"):
        assert a[column].equals(b[column]), f"{column} differs"
    for column in ("arrival_delay", "departure_delay"):
        left, right = a[column].astype("Float64"), b[column].astype("Float64")
        assert left.equals(right), f"{column} differs"


def test_observed_and_inferred_are_exclusive(built):
    """A time is measured or derived, never counted as both."""
    assert not (built.observed & built.inferred).any()


def test_no_cancellation_is_ever_claimed(built):
    """The feed carries no cancellation signal, so neither may the output."""
    assert not built.cancelled.any()
    assert (built.trip_schedule_relationship == 0).all()


def test_every_row_has_a_time_or_a_reason(built):
    """A row without a time says why, so a gap is never silently a gap."""
    timed = built.arrival_time.notna() | built.departure_time.notna()
    assert built.loc[~timed, "missing_reason"].notna().all()


def test_empty_source_is_not_an_error(built):
    from components.stib.harvesters.punctuality import STIBPunctualityHarvester
    assert STIBPunctualityHarvester().run([], None, None) is None
