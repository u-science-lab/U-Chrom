"""Tests for the ChromData HTTP data API endpoints."""
import struct
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from uchrom.core.cdata import ChromData
from webapp.backend.main import app
import webapp.backend.data_api as data_api


def _make_cd():
    """Synthetic ChromData: 2 cells, 1 chrom, 3 bins each."""
    n = 6  # 2 cells * 3 bins
    coords = np.arange(n * 3, dtype=float).reshape(n, 3)
    spots = pd.DataFrame({
        "chrom": ["chr1"] * n,
        "start": [0, 100, 200] * 2,
        "end":   [100, 200, 300] * 2,
        "trace_id": [1, 1, 1, 2, 2, 2],
        "cell_id":  ["c1", "c1", "c1", "c2", "c2", "c2"],
    })
    cells = pd.DataFrame({"cell_type": ["A", "B"]}, index=pd.Index(["c1", "c2"], name="cell_id"))
    umap = np.array([[0.1, 0.2], [0.3, 0.4]])
    tracks = pd.DataFrame({"atac": np.ones(n)})
    return ChromData(coords=coords, spots=spots, cells=cells,
                     cellm={"umap": umap}, tracks=tracks)


@pytest.fixture(autouse=True)
def inject_session():
    cd = _make_cd()
    from webapp.backend.session import Session
    s = Session(session_id="test")
    s.chromdata = cd
    data_api.current_session = s
    yield
    data_api.current_session = None


client = TestClient(app)


# ---------------------------------------------------------------------------
# 404 when no session
# ---------------------------------------------------------------------------

def test_coords_no_session():
    data_api.current_session = None
    r = client.get("/api/coords/c1")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# /api/coords/{cell_id}
# ---------------------------------------------------------------------------

def test_coords_cell():
    r = client.get("/api/coords/c1")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/octet-stream"
    arr = np.frombuffer(r.content, dtype=np.float32).reshape(-1, 3)
    assert arr.shape == (3, 3)
    # cell c1 is first 3 spots: coords rows 0-2
    expected = np.arange(9, dtype=np.float32).reshape(3, 3)
    np.testing.assert_array_almost_equal(arr, expected)


def test_coords_cell_not_found():
    r = client.get("/api/coords/nonexistent")
    # get_cell returns empty ChromData, not an error — shape (0,3) is valid
    arr = np.frombuffer(r.content, dtype=np.float32).reshape(-1, 3)
    assert arr.shape[1] == 3


# ---------------------------------------------------------------------------
# /api/coords/batch
# ---------------------------------------------------------------------------

def test_coords_batch():
    r = client.get("/api/coords/batch?ids=c1,c2")
    assert r.status_code == 200
    arr = np.frombuffer(r.content, dtype=np.float32).reshape(-1, 4)
    assert arr.shape == (6, 4)
    # cell_idx column
    assert list(arr[:3, 0]) == [0.0, 0.0, 0.0]
    assert list(arr[3:, 0]) == [1.0, 1.0, 1.0]


# ---------------------------------------------------------------------------
# /api/umap
# ---------------------------------------------------------------------------

def test_umap():
    r = client.get("/api/umap")
    assert r.status_code == 200
    body = r.json()
    assert "points" in body and "cell_types" in body
    assert len(body["points"]) == 2
    assert body["cell_types"] == ["A", "B"]
    pt = body["points"][0]
    assert "x" in pt and "y" in pt and "cell_id" in pt


def test_umap_no_umap():
    from webapp.backend.session import Session
    s = Session(session_id="t2")
    cd = _make_cd()
    cd.cellm.pop("umap")
    s.chromdata = cd
    data_api.current_session = s
    r = client.get("/api/umap")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# /api/track/{name}
# ---------------------------------------------------------------------------

def test_track():
    r = client.get("/api/track/atac?chrom=chr1")
    assert r.status_code == 200
    arr = np.frombuffer(r.content, dtype=np.float32)
    assert len(arr) == 6
    np.testing.assert_array_equal(arr, np.ones(6, dtype=np.float32))


def test_track_missing():
    r = client.get("/api/track/nonexistent")
    assert r.status_code == 404


def test_track_downsample():
    r = client.get("/api/track/atac?resolution=2")
    arr = np.frombuffer(r.content, dtype=np.float32)
    assert len(arr) == 2
