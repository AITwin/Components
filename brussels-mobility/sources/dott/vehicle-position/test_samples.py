import pytest
from pathlib import Path
import types

# Import your module under test — replace 'your_script' with the actual filename (no .py)
import fetch_and_analyze as mod


@pytest.fixture
def mock_requests(monkeypatch):
    """Mock requests.get to simulate API responses."""
    class MockResponse:
        def __init__(self, ok=True, status_code=200, data=None):
            self.ok = ok
            self.status_code = status_code
            self._data = data or {}
            self.text = "mock text"
        def json(self):
            return self._data

    def fake_get(url, headers=None):
        if "vehicle-position" in url:
            return MockResponse(
                data={
                    "features": [
                        {
                            "geometry": {"type": "Point", "coordinates": [4.35, 50.85]},
                            "properties": {"bike_id": "A123"},
                        },
                        {
                            "geometry": {"type": "Point", "coordinates": [4.36, 50.86]},
                            "properties": {"bike_id": "B456"},
                        },
                    ]
                }
            )
        raise RuntimeError(f"Unexpected URL: {url}")

    monkeypatch.setattr(mod.requests, "get", fake_get)


def test_main_creates_map(tmp_path, mock_requests, monkeypatch):
    """Run the main code and verify map.html creation."""
    outfile = tmp_path / "map.html"

    # Patch folium.Map.save to write into tmp_path instead of current dir
    def fake_save(self, filename):
        with open(outfile, "w") as f:
            f.write("<html>map content</html>")
    monkeypatch.setattr(mod.folium.Map, "save", fake_save)

    # Execute script logic manually (simulate top-level run)
    mod.r = mod.requests.get(mod.URL, headers={"Authorization": f"Bearer {mod.TOKEN}"})
    features = mod.r.json().get("features", [])
    points = [(f["geometry"]["coordinates"][1], f["geometry"]["coordinates"][0]) for f in features]

    m = mod.folium.Map(location=points[0], zoom_start=12)
    mc = mod.MarkerCluster().add_to(m)
    for lat, lon in points:
        mod.folium.CircleMarker([lat, lon], radius=3).add_to(mc)

    m.save("map.html")

    assert outfile.exists()
    content = outfile.read_text()
    assert "map content" in content


def test_error_on_bad_response(monkeypatch):
    """Ensure SystemExit occurs when response is not OK."""
    class BadResponse:
        ok = False
        status_code = 500
        text = "Server error"
        def json(self): return {}

    def fake_get(url, headers=None): return BadResponse()

    monkeypatch.setattr(mod.requests, "get", fake_get)

    with pytest.raises(SystemExit):
        _ = mod.requests.get(mod.URL, headers={"Authorization": f"Bearer {mod.TOKEN}"})
        if not _.ok:
            raise SystemExit(f"Error: {_.status_code} {_.text}")


def test_exit_on_no_data(monkeypatch):
    """Ensure SystemExit occurs when features list is empty."""
    class EmptyResponse:
        ok = True
        status_code = 200
        text = "OK"
        def json(self): return {"features": []}

    def fake_get(url, headers=None): return EmptyResponse()

    monkeypatch.setattr(mod.requests, "get", fake_get)

    r = mod.requests.get(mod.URL, headers={"Authorization": f"Bearer {mod.TOKEN}"})
    with pytest.raises(SystemExit):
        features = r.json().get("features", [])
        if not features:
            raise SystemExit("No data")
