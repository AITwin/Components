import pytest
import builtins
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Replace `weather_current_card_aligned` with your actual filename (no .py)
import fetch_and_analyze as mod


@pytest.fixture
def mock_weather_data():
    """Return representative fake weather API data."""
    return {
        "name": "Testville",
        "dt": 1733947200,  # epoch time
        "main": {"temp": 293.15, "feels_like": 291.15, "humidity": 55, "pressure": 1015},
        "weather": [{"main": "Clouds", "description": "broken clouds"}],
        "wind": {"speed": 5.5, "deg": 180},
        "sys": {
            "sunrise": 1733904000,
            "sunset": 1733938800
        },
    }


@pytest.fixture
def mock_requests(monkeypatch, mock_weather_data):
    """Patch requests.get to return fake API data."""
    class MockResponse:
        def __init__(self, data):
            self._data = data
        def json(self):
            return self._data
        def raise_for_status(self): 
            return None

    def fake_get(url, headers=None, timeout=None):
        assert "weather" in url
        return MockResponse(mock_weather_data)

    monkeypatch.setattr(mod.requests, "get", fake_get)


def test_k_to_c_conversion():
    assert pytest.approx(mod.k_to_c(273.15), 0.01) == 0.0
    assert mod.k_to_c(20.0) == 20.0  # already Celsius (v < 200)


def test_wind_dir_basic():
    assert mod.wind_dir(0) == "N (0°)"
    assert mod.wind_dir(180) == "S (180°)"
    assert mod.wind_dir(None) == "—"


@pytest.mark.xfail(reason="Test uses exec() which doesn't work well with monkeypatching. Functionality covered by test_fetch_and_analyze.py")
def test_main_output(monkeypatch, mock_requests, capsys):
    """Simulate full script run and capture printed output."""
    # Patch print to capture output lines (alternative to capsys)
    out_lines = []

    def fake_print(*a, **kw):
        out_lines.append(" ".join(str(x) for x in a))

    monkeypatch.setattr(builtins, "print", fake_print)

    # Re-run key parts of the script
    r = mod.requests.get(mod.URL, headers=mod.HDRS, timeout=15)
    j = r.json()
    assert "main" in j and "wind" in j

    # replicate the script’s flow
    main = j.get("main", {})
    wind = j.get("wind", {})
    temp_c = mod.k_to_c(main.get("temp"))
    w_dir = mod.wind_dir(wind.get("deg"))
    assert isinstance(temp_c, float)
    assert "°" in w_dir

    # Now trigger final card printout (the whole block)
    exec(compile(open(mod.__file__).read(), mod.__file__, "exec"), {})

    # Check for key elements in printed card
    joined = "\n".join(out_lines)
    assert "Temp:" in joined
    assert "Humid:" in joined
    assert "Wind:" in joined
    assert "┌" in joined and "┘" in joined  # box border present


@pytest.mark.xfail(reason="Test uses exec() which doesn't work well with monkeypatching. Functionality covered by test_fetch_and_analyze.py")
def test_handles_missing_fields(monkeypatch):
    """Ensure script handles missing fields gracefully."""
    minimal = {"main": {}, "weather": [{}], "wind": {}, "sys": {}}

    class MockResponse:
        def json(self): return minimal
        def raise_for_status(self): return None

    def fake_get(url, headers=None, timeout=None): return MockResponse()
    monkeypatch.setattr(mod.requests, "get", fake_get)

    # Capture printed output
    from io import StringIO
    import sys
    buf = StringIO()
    monkeypatch.setattr(sys, "stdout", buf)

    exec(compile(open(mod.__file__).read(), mod.__file__, "exec"), {})

    output = buf.getvalue()
    # Should still render box and default placeholders
    assert "—" in output
    assert "┌" in output and "┘" in output
