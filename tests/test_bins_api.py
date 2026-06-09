"""Tests for the /api/bins/{cell_id} endpoint."""
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from uchrom.core.cdata import ChromData
from webapp.backend.main import app
import webapp.backend.data_api as data_api


def _make_cd():
    """Synthetic ChromData: 2 cells, 2 chroms, 3 bins each."""
    n = 12  # 2 cells * 2 chroms * 3 bins
    coords = np.arange(n * 3, dtype=float).reshape(n, 3)
    spots = pd.DataFrame({
        "chrom": ["chr1", "chr1", "chr1", "chr2", "chr2", "chr2"] * 2,
        "start": [0, 100, 200, 0, 500, 1000] * 2,
        "end":   [100, 200, 300, 500, 1000, 1500] * 2,
        "trace_id": [1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4],
        "cell_id":  ["c1"] * 6 + ["c2"] * 6,
    })
    cells = pd.DataFrame({"cell_type": ["A", "B"]},
                         index=pd.Index(["c1", "c2"], name="cell_id"))
    return ChromData(coords=coords, spots=spots, cells=cells)


@pytest.fixture(autouse=True)
def inject_session():
    cd = _make_cd()
    from webapp.backend.session import Session
    s = Session(session_id="test-bins")
    s.chromdata = cd
    data_api.current_session = s
    yield
    data_api.current_session = None


client = TestClient(app)


# ---------------------------------------------------------------------------
# 404 when no session
# ---------------------------------------------------------------------------

def test_bins_no_session():
    data_api.current_session = None
    r = client.get("/api/bins/c1")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# /api/bins/{cell_id} — normal cases
# ---------------------------------------------------------------------------

def test_bins_cell_c1():
    r = client.get("/api/bins/c1")
    assert r.status_code == 200
    body = r.json()
    assert "bins" in body
    bins = body["bins"]
    assert len(bins) == 6  # 2 chroms * 3 bins
    # Check structure of each bin
    for b in bins:
        assert "chrom" in b
        assert "start" in b
        assert "end" in b
    # Check first bin values
    assert bins[0]["chrom"] == "chr1"
    assert bins[0]["start"] == 0
    assert bins[0]["end"] == 100


def test_bins_cell_c2():
    r = client.get("/api/bins/c2")
    assert r.status_code == 200
    body = r.json()
    bins = body["bins"]
    assert len(bins) == 6


def test_bins_cell_not_found():
    r = client.get("/api/bins/nonexistent")
    assert r.status_code == 404
    body = r.json()
    assert "error" in body.get("detail", body)


def test_bins_integer_cell_id():
    """Integer cell_id coercion should work."""
    # Make a ChromData with integer cell_ids
    n = 3
    coords = np.zeros((n, 3))
    spots = pd.DataFrame({
        "chrom": ["chr1"] * n,
        "start": [0, 100, 200],
        "end":   [100, 200, 300],
        "trace_id": [1, 1, 1],
        "cell_id": [42, 42, 42],
    })
    cells = pd.DataFrame(index=pd.Index([42], name="cell_id"))
    cd = ChromData(coords=coords, spots=spots, cells=cells)
    from webapp.backend.session import Session
    s = Session(session_id="int-test")
    s.chromdata = cd
    data_api.current_session = s

    r = client.get("/api/bins/42")
    assert r.status_code == 200
    body = r.json()
    assert len(body["bins"]) == 3
