"""Tests for WIG-format track endpoint."""
import pytest
from fastapi.testclient import TestClient
import numpy as np
import pandas as pd
from uchrom.core.cdata import ChromData
from webapp.backend.main import app
import webapp.backend.data_api as data_api


def _make_cd_with_tracks():
    n_cells, n_bins, bin_size = 3, 10, 1000
    n = n_cells * n_bins
    coords = np.zeros((n, 3))
    starts = np.tile(np.arange(n_bins) * bin_size, n_cells)
    spots = pd.DataFrame({
        "chrom": ["chr1"] * n,
        "start": starts.astype(int),
        "end": (starts + bin_size).astype(int),
        "trace_id": np.repeat(np.arange(n_cells), n_bins),
        "cell_id": np.repeat([f"c{i}" for i in range(n_cells)], n_bins),
    })
    cells = pd.DataFrame({"cell_type": ["A"] * n_cells},
                          index=pd.Index([f"c{i}" for i in range(n_cells)], name="cell_id"))
    # Track: atac signal linearly increasing per bin
    tracks = pd.DataFrame({"atac": np.tile(np.linspace(0, 1, n_bins), n_cells)}, index=spots.index)
    return ChromData(coords=coords, spots=spots, cells=cells, tracks=tracks)


@pytest.fixture(autouse=True)
def inject():
    from webapp.backend.session import Session
    s = Session(session_id="test")
    s.chromdata = _make_cd_with_tracks()
    data_api.current_session = s
    yield
    data_api.current_session = None


client = TestClient(app)


def test_wig_returns_text():
    r = client.get("/api/track_wig/atac?chrom=chr1")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]


def test_wig_contains_variablestep_header():
    r = client.get("/api/track_wig/atac?chrom=chr1")
    assert r.status_code == 200
    assert "variableStep chrom=chr1" in r.text


def test_wig_unknown_track_returns_404():
    r = client.get("/api/track_wig/nonexistent?chrom=chr1")
    assert r.status_code == 404


def test_wig_no_session_returns_404():
    data_api.current_session = None
    r = client.get("/api/track_wig/atac?chrom=chr1")
    assert r.status_code == 404
