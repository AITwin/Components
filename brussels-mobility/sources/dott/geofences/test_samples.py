import pytest
import types
import json
import geopandas as gpd
from shapely.geometry import Point, Polygon
import builtins

import fetch_and_analyze as mod


# ---- MOCK HELPERS ----

@pytest.fixture
def sample_data():
    """Provide small sample geofence and vehicle GeoJSONs."""
    zones = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "rules": json.dumps([{"ride_allowed": False}])
                },
                "geometry": Polygon([
                    (4.35, 50.85),
                    (4.36, 50.85),
                    (4.36, 50.86),
                    (4.35, 50.86),
                    (4.35, 50.85)
                ]).__geo_interface__
            }
        ],
    }

    vehicles = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"bike_id": "X123", "current_range_meters": 2500},
                "geometry": Point(4.355, 50.855).__geo_interface__,
            },
            {
                "type": "Feature",
                "properties": {"bike_id": "Y999", "current_range_meters": 5000},
                "geometry": Point(4.40, 50.80).__geo_interface__,
            },
        ],
    }

    return zones, vehicles


@pytest.fixture
def mock_requests(monkeypatch, sample_data):
    """Mock requests.get to avoid API calls."""
    zones, vehicles = sample_data

    class MockResponse:
        def __init__(self, js): self._js = js
        def json(self): return self._js

    def fake_get(url, *a, **kw):
        if "geofence" in url:
            return MockResponse(zones)
        elif "vehicle" in url:
            return MockResponse(vehicles)
        raise RuntimeError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)


# ---- TESTS ----

def test_normalize_rules_basic():
    assert mod.normalize_rules([1, 2]) == [1, 2]
    assert mod.normalize_rules('["a"]') == ["a"]
    assert mod.normalize_rules("invalid-json") == []
    assert mod.normalize_rules(123) == []


def test_main_runs_and_creates_html(tmp_path, mock_requests, monkeypatch):
    """Run main() end-to-end with mocked data and temporary output."""
    outfile = tmp_path / "output.html"

    # Patch folium.Map.save() to write to tmp_path instead of cwd
    def fake_save(self, filename):
        with open(outfile, "w") as f:
            f.write("<html>dummy map</html>")
    monkeypatch.setattr(mod.folium.Map, "save", fake_save)

    # Run the main function
    mod.main()

    # Ensure HTML was created
    assert outfile.exists()
    content = outfile.read_text()
    assert "dummy map" in content


def test_main_handles_no_vehicles(monkeypatch, sample_data):
    """Ensure graceful exit when no vehicles are inside."""
    zones, vehicles = sample_data
    # move all vehicles far away
    for f in vehicles["features"]:
        f["geometry"]["coordinates"] = [10.0, 10.0]

    class MockResponse:
        def __init__(self, js): self._js = js
        def json(self): return self._js

    def fake_get(url, *a, **kw):
        if "geofence" in url:
            return MockResponse(zones)
        elif "vehicle" in url:
            return MockResponse(vehicles)

    monkeypatch.setattr(mod.requests, "get", fake_get)

    # Expect a SystemExit when no vehicles are found inside zones
    with pytest.raises(SystemExit):
        mod.main()
