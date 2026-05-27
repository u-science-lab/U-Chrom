"""Tests for /api/export_script — Python script generation."""
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from uchrom.core.cdata import ChromData
from webapp.backend.main import app
import webapp.backend.data_api as data_api

client = TestClient(app)


def _make_cd():
    n = 6
    coords = np.arange(n * 3, dtype=float).reshape(n, 3)
    spots = pd.DataFrame({
        "chrom": ["chr1"] * n,
        "start": [0, 100, 200, 0, 100, 200],
        "end": [100, 200, 300, 100, 200, 300],
        "trace_id": [1, 1, 1, 2, 2, 2],
        "cell_id": ["c1", "c1", "c1", "c2", "c2", "c2"],
    })
    cells = pd.DataFrame({"cell_type": ["A", "B"]},
                          index=pd.Index(["c1", "c2"], name="cell_id"))
    return ChromData(coords=coords, spots=spots, cells=cells)


@pytest.fixture(autouse=True)
def inject_session():
    from webapp.backend.session import Session
    s = Session(session_id="test")
    s.chromdata = _make_cd()
    s.chromdata._source_path = "/data/test.h5cd"
    data_api.current_session = s
    yield
    data_api.current_session = None


def test_export_script_returns_python():
    r = client.get("/api/export_script")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    script = r.text
    assert "import uchrom" in script
    assert "ChromData.read" in script


def test_export_script_contains_data_path():
    r = client.get("/api/export_script")
    assert "/data/test.h5cd" in r.text


def test_export_script_no_session_404():
    data_api.current_session = None
    r = client.get("/api/export_script")
    assert r.status_code == 404


def test_export_script_is_valid_python():
    r = client.get("/api/export_script")
    script = r.text
    # Should compile without syntax errors
    compile(script, "<export_script>", "exec")
