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


def test_wig_range_filtered():
    # bins: start=0,1000,2000,...,9000 end=1000,2000,...,10000
    # query start=2000, end=5000 → overlap semantics: end>2000 AND start<5000
    # overlapping bins: [2000,3000), [3000,4000), [4000,5000) → starts 2000,3000,4000
    r = client.get("/api/track_wig/atac?chrom=chr1&start=2000&end=5000")
    assert r.status_code == 200
    text = r.text
    # Should contain track header
    assert "track type=wiggle_0 name=atac" in text
    # WIG positions are 1-based: 2001, 3001, 4001
    assert "2001 " in text
    assert "3001 " in text
    assert "4001 " in text
    # bins outside range should not appear
    assert "1001 " not in text
    assert "5001 " not in text


# ---------------------------------------------------------------------------
# CSV endpoint (E1): Gosling's data.type:'csv' loader needs real CSV, not WIG.
# ---------------------------------------------------------------------------

def test_csv_returns_csv_header():
    r = client.get("/api/track_csv/atac?chrom=chr1")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    lines = r.text.strip().split("\n")
    assert lines[0] == "chrom,start,end,value"


def test_csv_returns_data_rows():
    r = client.get("/api/track_csv/atac?chrom=chr1")
    assert r.status_code == 200
    lines = r.text.strip().split("\n")
    # header + one row per unique (chrom,start,end) bin (n_bins=10)
    assert len(lines) == 11
    # Each data row: chrom,start,end,value
    first = lines[1].split(",")
    assert len(first) == 4
    assert first[0] == "chr1"
    int(first[1]); int(first[2]); float(first[3])  # parseable


def test_csv_range_filtered():
    r = client.get("/api/track_csv/atac?chrom=chr1&start=2000&end=5000")
    assert r.status_code == 200
    lines = r.text.strip().split("\n")
    starts = [row.split(",")[1] for row in lines[1:]]
    # overlap semantics: end>2000 AND start<5000 → starts 2000,3000,4000
    assert starts == ["2000", "3000", "4000"]


def test_csv_unknown_track_returns_404():
    r = client.get("/api/track_csv/nonexistent?chrom=chr1")
    assert r.status_code == 404


def test_csv_no_session_returns_404():
    data_api.current_session = None
    r = client.get("/api/track_csv/atac?chrom=chr1")
    assert r.status_code == 404
