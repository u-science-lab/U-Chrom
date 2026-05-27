"""Phase 0 smoke: full HiGlass + IGV + bins workflow against a real fixture."""
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


def _make_cd():
    n_cells, n_bins = 3, 12
    n = n_cells * n_bins
    coords = np.random.RandomState(42).randn(n, 3).astype(float)
    starts = np.tile(np.arange(n_bins) * 1000, n_cells)
    spots = pd.DataFrame({
        "chrom": ["chr1"] * n,
        "start": starts,
        "end": starts + 1000,
        "trace_id": np.repeat(np.arange(n_cells), n_bins),
        "cell_id": np.repeat([f"c{i}" for i in range(n_cells)], n_bins),
    })
    cells = pd.DataFrame({"cell_type": ["A"] * n_cells},
                          index=pd.Index([f"c{i}" for i in range(n_cells)], name="cell_id"))
    tracks = pd.DataFrame({"H3K27me3": np.linspace(0, 1, n, dtype=np.float32)})
    return ChromData(coords=coords, spots=spots, cells=cells, tracks=tracks)


@pytest.fixture(autouse=True)
def inject_session():
    from webapp.backend.session import Session
    s = Session(session_id="smoke")
    s.chromdata = _make_cd()
    data_api.current_session = s
    tileset_api.clear_cache()
    yield
    data_api.current_session = None


client = TestClient(app)


def test_phase0_full_pipeline():
    """All four backend endpoints work together."""
    # 1. tileset_info
    info = client.get("/api/tileset_info?d=contact-chr1").json()["contact-chr1"]
    assert info["datatype"] == "matrix"
    max_z = info["max_zoom"]

    # 2. tile fetch decodes to a square Float32 array
    tile = client.get(f"/api/tiles?d=contact-chr1.{max_z}.0.0").json()[f"contact-chr1.{max_z}.0.0"]
    arr = np.frombuffer(gzip.decompress(base64.b64decode(tile["dense"])), dtype="<f4")
    assert arr.size == 256 * 256

    # 3. WIG track has 12 unique positions (one per bin)
    wig = client.get("/api/track_wig/H3K27me3?chrom=chr1").text
    data = [ln for ln in wig.splitlines() if ln and not ln.startswith("track") and not ln.startswith("variableStep")]
    assert len(data) == 12

    # 4. bins endpoint returns 12 bins for cell c0 (chrom/start/end)
    bins = client.get("/api/bins/c0").json()["bins"]
    assert len(bins) == 12
    assert bins[0]["chrom"] == "chr1"
    assert bins[0]["start"] == 0
    assert bins[-1]["end"] == 12000
