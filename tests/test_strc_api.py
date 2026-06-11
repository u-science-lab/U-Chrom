"""Tests for strc API endpoints (TAD, Loop, Compartment)."""
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

import webapp.backend.data_api as data_api
from webapp.backend.main import app

client = TestClient(app)


def _make_mock_cd():
    """Minimal ChromData mock with coords for strc callers."""
    cd = MagicMock()
    n = 20
    spots = pd.DataFrame({
        "chrom": pd.Categorical(["chr1"] * n),
        "start": np.arange(n) * 100_000,
        "end": np.arange(1, n + 1) * 100_000,
        "trace_id": pd.Categorical([f"t{i//10}" for i in range(n)]),
        "cell_id": pd.Categorical(["c0"] * n),
    })
    cd.spots = spots
    cd.coords = np.random.randn(n, 3).astype(np.float32)
    cd.cells = pd.DataFrame({"cell_id": ["c0"]}).set_index("cell_id")
    cd.cellm = {}
    cd.results = {}
    cd.uns = {}
    # get_chrom returns a mock with non-empty coords
    chrom_cd = MagicMock()
    chrom_cd.coords = np.random.randn(n, 3).astype(np.float32)
    cd.get_chrom.return_value = chrom_cd
    return cd


def test_tads_no_data():
    data_api.current_session = None
    resp = client.get("/api/tads/chr1")
    assert resp.status_code == 404


def test_tads_returns_list():
    cd = _make_mock_cd()
    mock_session = MagicMock()
    mock_session.chromdata = cd
    data_api.current_session = mock_session

    fake_tads = pd.DataFrame({
        "chrom": ["chr1", "chr1"],
        "start": [0, 1_000_000],
        "end": [1_000_000, 2_000_000],
        "level": [0, 0],
        "score": [5.0, 3.0],
        "pval": [1e-5, 1e-3],
        "fdr": [0.05, 0.09],
    })

    mock_tad_module = MagicMock()
    mock_tad_module.call_tads_by_pval.return_value = fake_tads
    mock_tad_module.TADCallerParams = MagicMock

    with patch.dict("sys.modules", {"uchrom.strc.tad": mock_tad_module}):
        resp = client.get("/api/tads/chr1")

    assert resp.status_code == 200
    data = resp.json()
    assert "tads" in data
    assert len(data["tads"]) == 2
    assert data["tads"][0]["chrom"] == "chr1"
    assert "start" in data["tads"][0]
    assert "end" in data["tads"][0]
    assert "level" in data["tads"][0]


def test_tads_format_gosling_returns_bare_array():
    """?format=gosling must return a bare JSON array (Gosling json loader
    requirement), not the {tads:[...]} wrapper."""
    cd = _make_mock_cd()
    mock_session = MagicMock()
    mock_session.chromdata = cd
    data_api.current_session = mock_session

    fake_tads = pd.DataFrame({
        "chrom": ["chr1", "chr1"],
        "start": [0, 1_000_000],
        "end": [1_000_000, 2_000_000],
        "level": [0, 0],
        "score": [5.0, 3.0],
        "pval": [1e-5, 1e-3],
        "fdr": [0.05, 0.09],
    })

    mock_tad_module = MagicMock()
    mock_tad_module.call_tads_by_pval.return_value = fake_tads
    mock_tad_module.TADCallerParams = MagicMock

    with patch.dict("sys.modules", {"uchrom.strc.tad": mock_tad_module}):
        resp = client.get("/api/tads/chr1?format=gosling")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["chrom"] == "chr1"


def test_loops_returns_list():
    cd = _make_mock_cd()
    mock_session = MagicMock()
    mock_session.chromdata = cd
    data_api.current_session = mock_session

    fake_loops = pd.DataFrame({
        "chrom1": ["chr1"],
        "start1": [100_000],
        "end1": [200_000],
        "chrom2": ["chr1"],
        "start2": [500_000],
        "end2": [600_000],
        "score": [8.0],
        "pval": [1e-6],
        "fdr": [0.01],
    })

    mock_loop_module = MagicMock()
    mock_loop_module.call_loops_axiswise_f.return_value = fake_loops
    mock_loop_module.LoopCallerParams = MagicMock

    with patch.dict("sys.modules", {"uchrom.strc.loop": mock_loop_module}):
        resp = client.get("/api/loops/chr1")

    assert resp.status_code == 200
    data = resp.json()
    assert "loops" in data
    assert len(data["loops"]) == 1
    assert data["loops"][0]["chrom1"] == "chr1"
    assert "start1" in data["loops"][0]


def test_compartments_returns_list():
    cd = _make_mock_cd()
    mock_session = MagicMock()
    mock_session.chromdata = cd
    data_api.current_session = mock_session

    fake_comp = pd.DataFrame({
        "chrom": ["chr1", "chr1"],
        "start": [0, 500_000],
        "end": [500_000, 1_000_000],
        "compartment": ["A", "B"],
        "pc2": [0.5, -0.3],
    })

    mock_comp_module = MagicMock()
    mock_comp_module.call_compartments_axes_pc.return_value = fake_comp
    mock_comp_module.CompartmentCallerParams = MagicMock

    with patch.dict("sys.modules", {"uchrom.strc.comp": mock_comp_module}):
        resp = client.get("/api/compartments/chr1")

    assert resp.status_code == 200
    data = resp.json()
    assert "compartments" in data
    assert len(data["compartments"]) == 2
    assert data["compartments"][0]["compartment"] == "A"


# ---------------------------------------------------------------------------
# E3: loop link-mark x1-channel field mapping
# ---------------------------------------------------------------------------

def test_loop_registry_declares_x1_chromosome_field():
    """Loop registry maps the second anchor's chrom to the x1 channel."""
    from webapp.backend.strc_api import ANALYSIS_REGISTRY
    loop = ANALYSIS_REGISTRY["loop"]
    assert loop["chromosome_field"] == "chrom1"
    assert loop["chromosome_field_x1"] == "chrom2"
    # genomic_fields cover both anchors (x/xe + x1/x1e)
    assert loop["genomic_fields"] == ["start1", "end1", "start2", "end2"]
    assert loop["suggested_mark"] == "link"


def test_run_registered_analysis_loop_surfaces_x1_field():
    """run_registered_analysis surfaces chromosome_field_x1 for loops only."""
    from webapp.backend import strc_api

    cd = _make_mock_cd()
    mock_session = MagicMock()
    mock_session.chromdata = cd
    data_api.current_session = mock_session

    fake_loops = pd.DataFrame({
        "chrom1": ["chr1"], "start1": [100_000], "end1": [200_000],
        "chrom2": ["chr1"], "start2": [500_000], "end2": [600_000],
        "score": [8.0], "pval": [1e-6], "fdr": [0.01],
    })
    mock_loop_module = MagicMock()
    mock_loop_module.call_loops_axiswise_f.return_value = fake_loops
    mock_loop_module.LoopCallerParams = MagicMock

    with patch.dict("sys.modules", {"uchrom.strc.loop": mock_loop_module}):
        handle = strc_api.run_registered_analysis("loop", "chr1")

    assert handle["chromosome_field"] == "chrom1"
    assert handle["chromosome_field_x1"] == "chrom2"
    assert handle["suggested_mark"] == "link"
    # cis-only caller: chrom2 == chrom1 in every record
    assert all(r["chrom2"] == r["chrom1"] for r in handle["records"])


def test_run_registered_analysis_tad_has_no_x1_field():
    """Non-link analyses (TAD) do not surface chromosome_field_x1."""
    from webapp.backend import strc_api

    cd = _make_mock_cd()
    mock_session = MagicMock()
    mock_session.chromdata = cd
    data_api.current_session = mock_session

    fake_tads = pd.DataFrame({
        "chrom": ["chr1"], "start": [0], "end": [500_000],
    })
    mock_tad_module = MagicMock()
    mock_tad_module.call_tads_by_pval.return_value = fake_tads
    mock_tad_module.TADCallerParams = MagicMock

    with patch.dict("sys.modules", {"uchrom.strc.tad": mock_tad_module}):
        handle = strc_api.run_registered_analysis("tad", "chr1")

    assert "chromosome_field_x1" not in handle
