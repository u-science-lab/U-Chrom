"""Tests for the compute_embedding agent tool.

Covers:
  - core compute_cell_embedding on real rich_multicell.h5cd (8 cells) →
    writes cd.cellm['umap'] with shape (8, 2), no NaNs.
  - the executor emits the embedding_computed artifact + returns success.
  - n_neighbors clamping + small-n (n_cells < 3) edge handling.
  - cellm row order matches /api/umap's cell iteration (the executor populates
    cd.cells for FOF-CT-style data where it starts empty).
  - end-to-end /api/umap goes 404 → 200 with the right point count.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient

from uchrom.core.cdata import ChromData
from webapp.backend.tool_executors import (
    TOOL_EXECUTORS,
    compute_cell_embedding,
    _ordered_cell_ids,
)
from webapp.backend.main import app
import webapp.backend.data_api as data_api
from webapp.backend.session import Session

EXAMPLE_DATA = Path(__file__).resolve().parents[2] / "example-data"
RICH = EXAMPLE_DATA / "rich_multicell.h5cd"


def _make_session(cd):
    s = Session(session_id="test-emb")
    s.chromdata = cd
    return s


def _synthetic_cd(n_cells: int, n_bins: int = 8):
    """Aligned-bin synthetic data so the distance method engages."""
    rng = np.random.RandomState(0)
    starts = (np.arange(n_bins) * 100).tolist()
    ends = ((np.arange(n_bins) + 1) * 100).tolist()
    rows_chrom, rows_start, rows_end, rows_tid, rows_cid = [], [], [], [], []
    coords = []
    for c in range(n_cells):
        rows_chrom += ["chr1"] * n_bins
        rows_start += starts
        rows_end += ends
        rows_tid += [f"t{c}"] * n_bins
        rows_cid += [f"c{c}"] * n_bins
        coords.append(rng.rand(n_bins, 3) + c)  # separable per cell
    spots = pd.DataFrame({
        "chrom": rows_chrom, "start": rows_start, "end": rows_end,
        "trace_id": rows_tid, "cell_id": rows_cid,
    })
    cells = pd.DataFrame(
        index=pd.Index([f"c{c}" for c in range(n_cells)], name="cell_id"))
    return ChromData(coords=np.vstack(coords), spots=spots, cells=cells)


# ---------------------------------------------------------------------------
# Core compute on real rich data
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not RICH.exists(), reason="rich_multicell.h5cd missing")
def test_compute_on_rich_multicell():
    cd = ChromData.read(str(RICH))
    assert "umap" not in cd.cellm  # starts without an embedding
    summary = compute_cell_embedding(cd)
    assert summary["n_cells"] == 8
    assert summary["method"] == "distance"  # rich data has aligned bins
    umap = cd.cellm["umap"]
    assert umap.shape == (8, 2)
    assert not np.isnan(umap).any()
    assert np.isfinite(umap).all()


# ---------------------------------------------------------------------------
# Executor: artifact + tool_result
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.skipif(not RICH.exists(), reason="rich_multicell.h5cd missing")
async def test_executor_emits_artifact_and_writes_cellm():
    cd = ChromData.read(str(RICH))
    session = _make_session(cd)
    ws = AsyncMock()
    content = await TOOL_EXECUTORS["compute_embedding"](
        ws, {"_session": session, "_tool_use_id": "u1"}
    )
    result = json.loads(content)
    assert result["success"] is True
    assert result["n_cells"] == 8
    art = ws.send_json.call_args[0][0]
    assert art["type"] == "agent_artifact"
    assert art["artifact_type"] == "embedding_computed"
    assert art["n_cells"] == 8
    assert cd.cellm["umap"].shape == (8, 2)


@pytest.mark.asyncio
async def test_executor_no_data_returns_error():
    ws = AsyncMock()
    content = await TOOL_EXECUTORS["compute_embedding"](
        ws, {"_session": Session(session_id="empty")}
    )
    assert json.loads(content)["success"] is False


# ---------------------------------------------------------------------------
# n_neighbors clamping + small-n edges
# ---------------------------------------------------------------------------

def test_n_neighbors_clamped_for_small_n():
    cd = _synthetic_cd(n_cells=3)
    summary = compute_cell_embedding(cd)
    # min(15, n_cells-1) = 2
    assert summary["n_neighbors"] == 2
    assert cd.cellm["umap"].shape == (3, 2)
    assert not np.isnan(cd.cellm["umap"]).any()


def test_single_cell_raises():
    cd = _synthetic_cd(n_cells=1)
    with pytest.raises(ValueError):
        compute_cell_embedding(cd)


def test_geometric_method_fallback():
    cd = _synthetic_cd(n_cells=5)
    summary = compute_cell_embedding(cd, method="geometric")
    assert summary["method"] == "geometric"
    assert summary["n_features"] == 7
    assert cd.cellm["umap"].shape == (5, 2)


# ---------------------------------------------------------------------------
# cellm row order matches /api/umap iteration
# ---------------------------------------------------------------------------

def test_cellm_order_matches_api_umap_iteration():
    cd = _synthetic_cd(n_cells=4)
    ids_before = _ordered_cell_ids(cd)
    compute_cell_embedding(cd)
    # /api/umap iterates cd.cells.reset_index(); the order must be unchanged.
    df = cd.cells.reset_index()
    api_ids = [str(x) for x in df["cell_id"].tolist()]
    assert api_ids == ids_before


def test_populates_empty_cells_for_fofct_style():
    """When cd.cells is empty (FOF-CT), the executor must build matching rows."""
    cd = _synthetic_cd(n_cells=4)
    cd.cells = pd.DataFrame()  # simulate empty cells (FOF-CT import)
    ids = _ordered_cell_ids(cd)  # falls back to spots
    compute_cell_embedding(cd)
    assert len(cd.cells) == 4
    df = cd.cells.reset_index()
    assert [str(x) for x in df["cell_id"].tolist()] == ids


# ---------------------------------------------------------------------------
# End-to-end /api/umap 404 -> 200
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not RICH.exists(), reason="rich_multicell.h5cd missing")
def test_api_umap_goes_404_to_200():
    cd = ChromData.read(str(RICH))
    client = TestClient(app)
    data_api.current_session = _make_session(cd)
    try:
        r = client.get("/api/umap")
        assert r.status_code == 404  # no embedding yet
        compute_cell_embedding(cd)
        r = client.get("/api/umap")
        assert r.status_code == 200
        points = r.json()["points"]
        assert len(points) == 8
        for p in points:
            assert "x" in p and "y" in p and "cell_id" in p
    finally:
        data_api.current_session = None
