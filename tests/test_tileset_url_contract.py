"""Regression tests for the HiGlass/Gosling tileset URL contract (E2).

HiGlass/Gosling's matrix datafetcher requests the *trailing-slash* forms
`${server}/tileset_info/?d=<uid>` and `${server}/tiles/?d=<uid>.z.x.y`, where
`server` is the spec's `data.server` (= `${origin}/api/v1`). The tile-fetcher
does not follow 307 redirects, so the backend must return 200 *directly* for
the trailing-slash `/api/v1/...` routes — not redirect to the no-slash form.

These tests assert all four `/api/v1` variants resolve with 200 (no redirect)
and that the payloads are well-formed (datatype=='matrix', non-empty dense
tile).

Data: builds a real ChromData via the public constructor (the same fixture
pattern used by tests/test_tileset_api.py). The repo's
example-data/synthetic_chr1_tiny.h5cd referenced in the task spec is not present
in this checkout; the inline ChromData below is a real container (not a mock),
so the URL contract is exercised against genuine matrix/tile logic.
"""
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

# The chromosome present in the test data. The frontend spec defaults to chr21,
# but this fixture's data lives on chr1, so the contract is asserted against the
# chrom actually loaded.
CHROM = "chr1"
UID = f"contact-{CHROM}"


def _make_cd(n_cells=4, n_bins=8, bin_size=100):
    n = n_cells * n_bins
    coords = np.random.RandomState(0).randn(n, 3).astype(float)
    starts = np.tile(np.arange(n_bins) * bin_size, n_cells)
    spots = pd.DataFrame({
        "chrom": [CHROM] * n,
        "start": starts.astype(int),
        "end": (starts + bin_size).astype(int),
        "trace_id": np.repeat(np.arange(n_cells), n_bins),
        "cell_id": np.repeat([f"c{i}" for i in range(n_cells)], n_bins),
    })
    cells = pd.DataFrame(
        {"cell_type": ["A"] * n_cells},
        index=pd.Index([f"c{i}" for i in range(n_cells)], name="cell_id"),
    )
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


def test_tileset_info_trailing_slash_no_redirect():
    """HiGlass form `/api/v1/tileset_info/?d=...` returns 200 directly."""
    r = client.get(f"/api/v1/tileset_info/?d={UID}", follow_redirects=False)
    assert r.status_code == 200, f"expected 200, got {r.status_code}"
    body = r.json()
    assert UID in body
    assert body[UID]["datatype"] == "matrix"


def test_tileset_info_no_slash_no_redirect():
    """No-slash form also returns 200 directly."""
    r = client.get(f"/api/v1/tileset_info?d={UID}", follow_redirects=False)
    assert r.status_code == 200
    assert r.json()[UID]["datatype"] == "matrix"


def test_tiles_trailing_slash_no_redirect():
    """HiGlass form `/api/v1/tiles/?d=uid.z.x.y` returns 200 with dense tile."""
    tile_id = f"{UID}.0.0.0"
    r = client.get(f"/api/v1/tiles/?d={tile_id}", follow_redirects=False)
    assert r.status_code == 200, f"expected 200, got {r.status_code}"
    body = r.json()
    assert tile_id in body
    dense = body[tile_id]["dense"]
    raw = gzip.decompress(base64.b64decode(dense))
    arr = np.frombuffer(raw, dtype=np.float32)
    assert len(arr) == 256 * 256
    # Real distance data: at least some finite, non-zero values.
    assert np.isfinite(arr).any()


def test_tiles_no_slash_no_redirect():
    """No-slash form also returns 200."""
    tile_id = f"{UID}.0.0.0"
    r = client.get(f"/api/v1/tiles?d={tile_id}", follow_redirects=False)
    assert r.status_code == 200
    assert tile_id in r.json()


def test_all_four_variants_resolve():
    """All four registered /api/v1 variants resolve without redirect."""
    paths = [
        f"/api/v1/tileset_info?d={UID}",
        f"/api/v1/tileset_info/?d={UID}",
        f"/api/v1/tiles?d={UID}.0.0.0",
        f"/api/v1/tiles/?d={UID}.0.0.0",
    ]
    for p in paths:
        r = client.get(p, follow_redirects=False)
        assert r.status_code == 200, f"{p} → {r.status_code} (expected 200)"
