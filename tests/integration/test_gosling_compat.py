"""End-to-end tests for the HiGlass/Gosling contact-map tileset integration.

These exercise the *real* endpoints the frontend uses:

  * HiGlassPanel presence check:  GET /api/tileset_info?d=contact-{chrom}
  * HiGlass tile library fetches:  GET /api/v1/tileset_info  and
    GET /api/v1/tiles/  (aliased in main.py to the tileset_api handlers).

HiGlass batches tile requests with *repeated* query params
(``?d=a&d=b``), so the repeated-param path is covered explicitly — it
previously regressed to returning only the last tile.
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
from webapp.backend.session import Session


def _make_cd(n_cells=4, n_bins=8, bin_size=100):
    """Synthetic ChromData with deterministic coords on chr1."""
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
    cells = pd.DataFrame(
        {"cell_type": ["A"] * n_cells},
        index=pd.Index([f"c{i}" for i in range(n_cells)], name="cell_id"),
    )
    return ChromData(coords=coords, spots=spots, cells=cells)


@pytest.fixture
def client_with_data():
    s = Session(session_id="test")
    s.chromdata = _make_cd()
    data_api.current_session = s
    tileset_api.clear_cache()
    yield TestClient(app)
    data_api.current_session = None


def _decode_dense(tile):
    raw = gzip.decompress(base64.b64decode(tile["dense"]))
    return np.frombuffer(raw, dtype=np.float32)


# ---------------------------------------------------------------------------
# tileset_info — HiGlass-required fields
# ---------------------------------------------------------------------------

GOSLING_REQUIRED_FIELDS = {
    "max_zoom", "min_pos", "max_pos", "bins_per_dimension", "datatype",
}


def test_tileset_info_has_gosling_fields(client_with_data):
    """tileset_info must return the fields HiGlass/Gosling require to render."""
    r = client_with_data.get("/api/tileset_info?d=contact-chr1")
    assert r.status_code == 200
    info = r.json()["contact-chr1"]
    assert GOSLING_REQUIRED_FIELDS <= set(info)
    assert info["datatype"] == "matrix"
    assert info["bins_per_dimension"] == 256
    assert info["min_pos"] == [0, 0]
    assert info["max_pos"][0] == info["max_pos"][1] == info["max_width"]


def test_v1_alias_matches_canonical(client_with_data):
    """The /api/v1/ alias (used by the HiGlass lib) matches the canonical route."""
    a = client_with_data.get("/api/tileset_info?d=contact-chr1")
    b = client_with_data.get("/api/v1/tileset_info?d=contact-chr1")
    assert a.status_code == b.status_code == 200
    assert a.json() == b.json()


# ---------------------------------------------------------------------------
# tiles — encoding + correctness
# ---------------------------------------------------------------------------

def test_tile_is_256x256_float32(client_with_data):
    """A tile decodes to a 256×256 float32 dense array with sane min/max."""
    r = client_with_data.get("/api/v1/tiles/?d=contact-chr1.0.0.0")
    assert r.status_code == 200
    tile = r.json()["contact-chr1.0.0.0"]
    arr = _decode_dense(tile)
    assert len(arr) == 256 * 256
    assert tile["min_value"] == 0.0
    assert tile["max_value"] >= 0.0


def test_tile_reflects_distance_matrix(client_with_data):
    """Tile values trace back to the averaged pairwise-distance matrix.

    The diagonal of the distance matrix is zero (self-distance) and the
    matrix is symmetric; the off-diagonal max must be positive and match
    the tile's reported max_value at zoom 0 (whole matrix in one tile).
    """
    matrix = tileset_api._build_matrix("chr1")
    assert np.allclose(np.diag(matrix), 0.0)
    assert np.allclose(matrix, matrix.T)
    assert matrix.max() > 0

    r = client_with_data.get("/api/v1/tiles/?d=contact-chr1.0.0.0")
    tile = r.json()["contact-chr1.0.0.0"]
    # At zoom 0 the entire matrix downsamples into the single tile, so the
    # tile's max must equal the matrix max (within float32 tolerance).
    assert tile["max_value"] == pytest.approx(float(matrix.max()), rel=1e-5)


# ---------------------------------------------------------------------------
# repeated-param batching — the real HiGlass fetch pattern
# ---------------------------------------------------------------------------

def test_repeated_d_params_return_all_tiles(client_with_data):
    """HiGlass batches tiles as ?d=a&d=b — all requested tiles come back.

    Regression: a single ``d: str`` signature bound only the last repeated
    value, so multi-tile batches rendered only one tile.
    """
    r = client_with_data.get(
        "/api/v1/tiles/?d=contact-chr1.1.0.0&d=contact-chr1.1.0.1"
        "&d=contact-chr1.1.1.0&d=contact-chr1.1.1.1"
    )
    assert r.status_code == 200
    assert set(r.json()) == {
        "contact-chr1.1.0.0", "contact-chr1.1.0.1",
        "contact-chr1.1.1.0", "contact-chr1.1.1.1",
    }


def test_comma_separated_still_supported(client_with_data):
    """Comma-separated ids remain valid (backward compat)."""
    repeated = client_with_data.get(
        "/api/tiles?d=contact-chr1.0.0.0&d=contact-chr1.1.0.0"
    )
    comma = client_with_data.get(
        "/api/tiles?d=contact-chr1.0.0.0,contact-chr1.1.0.0"
    )
    assert repeated.status_code == comma.status_code == 200
    assert set(repeated.json()) == set(comma.json())


def test_tileset_info_repeated_params(client_with_data):
    """tileset_info also honors repeated params for multi-dataset views."""
    r = client_with_data.get(
        "/api/tileset_info?d=contact-chr1&d=contact-chr1"
    )
    assert r.status_code == 200
    assert "contact-chr1" in r.json()


# ---------------------------------------------------------------------------
# error handling
# ---------------------------------------------------------------------------

def test_no_data_returns_404(client_with_data):
    """Both canonical and v1 routes 404 when no data is loaded."""
    data_api.current_session = None
    assert client_with_data.get("/api/tileset_info?d=contact-chr1").status_code == 404
    assert client_with_data.get("/api/v1/tileset_info?d=contact-chr1").status_code == 404


def test_unknown_uid_returns_400(client_with_data):
    """A uid without the contact- prefix is rejected."""
    r = client_with_data.get("/api/tileset_info?d=bogus-chr1")
    assert r.status_code == 400


def test_malformed_tile_id_returns_400(client_with_data):
    """A tile id that isn't uid.z.x.y is rejected."""
    r = client_with_data.get("/api/tiles?d=contact-chr1.0.0")
    assert r.status_code == 400
