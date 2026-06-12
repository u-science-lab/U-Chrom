"""Tests for HiGlass-compatible tileset endpoints."""
import base64
import gzip
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from uchrom.core.cdata import ChromData
from webapp.backend.main import app
import webapp.backend.data_api as data_api
from webapp.backend import tileset_api


def _make_cd(n_cells=4, n_bins=8, bin_size=100):
    """Synthetic ChromData with predictable coords."""
    n = n_cells * n_bins
    coords = np.random.RandomState(0).randn(n, 3).astype(float)
    starts = np.tile(np.arange(n_bins) * bin_size, n_cells)
    spots = pd.DataFrame({
        "chrom": ["chr1"] * n,
        "start": starts,
        "end": starts + bin_size,
        "trace_id": np.repeat(np.arange(n_cells), n_bins),
        "cell_id": np.repeat([f"c{i}" for i in range(n_cells)], n_bins),
    })
    cells = pd.DataFrame({"cell_type": ["A"] * n_cells},
                          index=pd.Index([f"c{i}" for i in range(n_cells)], name="cell_id"))
    return ChromData(coords=coords, spots=spots, cells=cells)


@pytest.fixture(autouse=True)
def inject_session():
    from webapp.backend.session import Session
    s = Session(session_id="test")
    s.chromdata = _make_cd()
    data_api.current_session = s
    tileset_api.clear_cache()
    yield
    data_api.current_session = None


client = TestClient(app)


def test_tileset_info_returns_chrom_dataset():
    """tileset_info returns metadata for a chromosome's contact dataset."""
    r = client.get("/api/tileset_info?d=contact-chr1")
    assert r.status_code == 200
    body = r.json()
    assert "contact-chr1" in body
    info = body["contact-chr1"]
    assert info["datatype"] == "matrix"
    assert info["bins_per_dimension"] == 256
    assert info["max_zoom"] >= 0
    assert info["max_width"] >= 800  # n_bins * bin_size = 800
    assert info["min_pos"] == [0, 0]
    assert info["max_pos"][0] == info["max_pos"][1] == info["max_width"]


def test_tile_encoding_returns_valid_float32():
    """Tile endpoint returns base64 raw (un-gzipped) float32 array.

    Gosling's tile decoder reads `dense` as new Float32Array(base64ToArrayBuffer(dense))
    with no decompression, so the payload must be raw little-endian float32 — and its
    decoded byte length must be a multiple of 4 (256*256*4 = 262144).
    """
    r = client.get("/api/tiles?d=contact-chr1.0.0.0")
    assert r.status_code == 200
    body = r.json()
    assert "contact-chr1.0.0.0" in body
    tile = body["contact-chr1.0.0.0"]
    assert "dense" in tile
    raw = base64.b64decode(tile["dense"])
    assert len(raw) % 4 == 0
    arr = np.frombuffer(raw, dtype=np.float32)
    assert len(arr) == 256 * 256


def test_tileset_info_returns_correct_structure():
    """tileset_info returns correct structure for a single UID."""
    r = client.get("/api/tileset_info?d=contact-chr1")
    assert r.status_code == 200
    body = r.json()
    assert "contact-chr1" in body


def test_tileset_no_session_returns_404():
    """Tileset endpoints return 404 when no data loaded."""
    data_api.current_session = None
    r = client.get("/api/tileset_info?d=contact-chr1")
    assert r.status_code == 404
