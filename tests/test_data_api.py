"""Tests for the ChromData HTTP data API endpoints."""
import struct
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from uchrom.core.cdata import ChromData
from webapp.backend.main import app
import webapp.backend.data_api as data_api

EXAMPLE_DATA = Path(__file__).resolve().parents[1] / "example-data"


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
# /api/cells — cell list independent of UMAP
# ---------------------------------------------------------------------------

def _set_session(cd):
    from webapp.backend.session import Session
    s = Session(session_id="cells-test")
    s.chromdata = cd
    data_api.current_session = s


def test_cells_no_session():
    data_api.current_session = None
    r = client.get("/api/cells")
    assert r.status_code == 404


def test_cells_from_cells_df():
    # Synthetic cd has cells c1, c2 with cell_type metadata
    r = client.get("/api/cells")
    assert r.status_code == 200
    body = r.json()
    assert "cells" in body
    ids = [c["cell_id"] for c in body["cells"]]
    assert ids == ["c1", "c2"]
    assert all("cell_type" in c for c in body["cells"])
    assert body["cell_types"] == ["A", "B"]


def test_cells_independent_of_umap():
    # Same dataset minus UMAP: /api/cells must still list cells, /api/umap 404s.
    cd = _make_cd()
    cd.cellm.pop("umap")
    _set_session(cd)
    r = client.get("/api/cells")
    assert r.status_code == 200
    ids = [c["cell_id"] for c in r.json()["cells"]]
    assert ids == ["c1", "c2"]
    # Proof of decoupling: UMAP is gone but cells still resolve.
    assert client.get("/api/umap").status_code == 404


def test_cells_fallback_to_spots():
    # cd.cells empty → derive cell list from spots.cell_id
    cd = _make_cd()
    cd.cells = pd.DataFrame()
    _set_session(cd)
    r = client.get("/api/cells")
    assert r.status_code == 200
    ids = [c["cell_id"] for c in r.json()["cells"]]
    assert ids == ["c1", "c2"]


@pytest.mark.skipif(
    not (EXAMPLE_DATA / "rich_multicell.h5cd").exists(),
    reason="rich_multicell.h5cd example data not present",
)
def test_cells_real_rich_multicell():
    """Real-data validation: 8 cells, no UMAP — exactly the decoupling case."""
    cd = ChromData.read(str(EXAMPLE_DATA / "rich_multicell.h5cd"))
    assert "umap" not in cd.cellm  # precondition: this dataset has no UMAP
    _set_session(cd)

    r = client.get("/api/cells")
    assert r.status_code == 200
    ids = [c["cell_id"] for c in r.json()["cells"]]
    assert ids == [f"c{i}" for i in range(8)]

    # /api/umap stays 404 for this dataset, proving /api/cells is independent.
    assert client.get("/api/umap").status_code == 404


# ---------------------------------------------------------------------------
# /api/dataset_info — dataset-level metadata for default-spec construction
# ---------------------------------------------------------------------------

def test_dataset_info_no_session():
    data_api.current_session = None
    r = client.get("/api/dataset_info")
    assert r.status_code == 404


def test_dataset_info_synthetic():
    # Synthetic cd: 1 chrom (chr1), no assembly in uns, 2 cells, 6 spots.
    r = client.get("/api/dataset_info")
    assert r.status_code == 200
    body = r.json()
    assert body["chroms"] == ["chr1"]
    assert body["genome_assembly"] is None
    assert body["n_cells"] == 2
    assert body["n_spots"] == 6


def test_dataset_info_prefers_explicit_session_id_over_global_fallback():
    from webapp.backend.main import sessions
    from webapp.backend.session import Session

    global_cd = _make_cd()
    global_cd.uns["genome_assembly"] = "global"
    explicit_cd = _make_cd()
    explicit_cd.spots["chrom"] = ["chr2"] * len(explicit_cd.spots)
    explicit_cd.uns["genome_assembly"] = "explicit"

    global_session = Session(session_id="global-session")
    global_session.chromdata = global_cd
    explicit_session = Session(session_id="explicit-session")
    explicit_session.chromdata = explicit_cd

    data_api.current_session = global_session
    sessions["explicit-session"] = explicit_session
    try:
        r = client.get("/api/dataset_info?session_id=explicit-session")
    finally:
        sessions.pop("explicit-session", None)

    assert r.status_code == 200
    body = r.json()
    assert body["chroms"] == ["chr2"]
    assert body["genome_assembly"] == "explicit"


def test_bins_can_include_session_analysis_annotations():
    session = data_api.current_session
    session.analysis_annotations = {
        "compartment:chr1": {
            "analysis_type": "compartment",
            "chrom": "chr1",
            "records": [
                {"chrom": "chr1", "start": 0, "end": 150, "compartment": "A", "score": 0.9},
                {"chrom": "chr1", "start": 150, "end": 300, "compartment": "B", "score": -0.4},
            ],
        }
    }

    default_body = client.get("/api/bins/c1").json()
    assert "annotations" not in default_body["bins"][0]

    r = client.get("/api/bins/c1?annotations=true")
    assert r.status_code == 200
    bins = r.json()["bins"]
    assert bins[0]["annotations"]["compartment"] == "A"
    assert bins[0]["annotations"]["compartment_score"] == 0.9
    assert bins[1]["annotations"]["compartment"] == "B"
    assert bins[2]["annotations"]["compartment"] == "B"


def test_bins_project_tad_membership_and_loop_anchor_counts():
    session = data_api.current_session
    session.analysis_annotations = {
        "tad:chr1": {
            "analysis_type": "tad",
            "chrom": "chr1",
            "records": [{"chrom": "chr1", "start": 0, "end": 150}],
        },
        "loop:chr1": {
            "analysis_type": "loop",
            "chrom": "chr1",
            "records": [{
                "chrom": "chr1",
                "chrom2": "chr1",
                "start1": 0,
                "end1": 100,
                "start2": 200,
                "end2": 300,
            }],
        },
    }

    r = client.get("/api/bins/c1?annotations=true")
    assert r.status_code == 200
    bins = r.json()["bins"]
    assert bins[0]["annotations"]["tad"] is True
    assert bins[0]["annotations"]["tad_index"] == 0
    assert bins[0]["annotations"]["loop_anchor_count"] == 1
    assert bins[1]["annotations"]["tad"] is True
    assert "tad" not in bins[2]["annotations"]
    assert bins[2]["annotations"]["loop_anchor_count"] == 1


@pytest.mark.skipif(
    not (EXAMPLE_DATA / "rich_multicell.h5cd").exists(),
    reason="rich_multicell.h5cd example data not present",
)
def test_dataset_info_real_rich_multicell():
    """Real-data: chr1+chr2, assembly mm10."""
    cd = ChromData.read(str(EXAMPLE_DATA / "rich_multicell.h5cd"))
    _set_session(cd)
    r = client.get("/api/dataset_info")
    assert r.status_code == 200
    body = r.json()
    assert body["chroms"] == ["chr1", "chr2"]
    assert body["genome_assembly"] == "mm10"
    assert body["n_cells"] == 8
    assert body["n_spots"] > 0


@pytest.mark.skipif(
    not (EXAMPLE_DATA / "synthetic_chr1_tiny.h5cd").exists(),
    reason="synthetic_chr1_tiny.h5cd example data not present",
)
def test_dataset_info_real_chr1_tiny():
    """Real-data: chr1 only, no assembly → genome_assembly null."""
    cd = ChromData.read(str(EXAMPLE_DATA / "synthetic_chr1_tiny.h5cd"))
    _set_session(cd)
    r = client.get("/api/dataset_info")
    assert r.status_code == 200
    body = r.json()
    assert body["chroms"] == ["chr1"]
    assert body["genome_assembly"] is None


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
