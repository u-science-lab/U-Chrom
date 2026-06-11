"""Tests for the dynamic custom-analysis API endpoints.

Mirrors test_strc_api.py's TestClient pattern but uses a real ChromData
(synthetic_chr1_tiny.h5cd, chrom is 'chr1') loaded into the global session.
"""
import os

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import webapp.backend.data_api as data_api
import webapp.backend.dynamic_api as dynamic_api
from webapp.backend.main import app

client = TestClient(app)

DATASET_PATH = "example-data/synthetic_chr1_tiny.h5cd"


def _ensure_dataset():
    if os.path.exists(DATASET_PATH):
        return
    from uchrom.core import ChromData
    n = 100
    spots = pd.DataFrame({
        "chrom": pd.Categorical(["chr1"] * n),
        "start": np.arange(n) * 100_000,
        "end": (np.arange(n) + 1) * 100_000,
        "trace_id": pd.Categorical(["t0"] * n),
        "cell_id": pd.Categorical(["c0"] * n),
    })
    coords = (np.random.RandomState(0).randn(n, 3).astype(np.float32)) * 1000
    cells = pd.DataFrame({"cell_id": ["c0"]}).set_index("cell_id")
    cd = ChromData(coords=coords, spots=spots, cells=cells)
    os.makedirs(os.path.dirname(DATASET_PATH), exist_ok=True)
    cd.write(DATASET_PATH)


@pytest.fixture
def loaded_session():
    """Load the real tiny ChromData into the global session."""
    _ensure_dataset()
    from uchrom.core import ChromData
    from unittest.mock import MagicMock
    cd = ChromData.read(DATASET_PATH)
    sess = MagicMock()
    sess.chromdata = cd
    data_api.current_session = sess
    dynamic_api.clear_registry()
    yield cd
    dynamic_api.clear_registry()
    data_api.current_session = None


# A simple, legitimate analysis: per-bin radius from origin.
RG_CODE = '''
def analyze(cd, chrom, **params):
    n = cd.coords.shape[0]
    starts = cd.spots["start"].to_numpy()
    r = np.sqrt((cd.coords ** 2).sum(axis=1))
    return pd.DataFrame({
        "chrom": [chrom] * n,
        "start": starts,
        "end": starts + 100000,
        "radius": r,
    })
'''


def test_register_then_get_returns_records(loaded_session):
    handle = dynamic_api.register_analysis(
        "radius", RG_CODE,
        chromosome_field="chrom", genomic_fields=["start", "end"],
        suggested_mark="line", result_key="radius",
    )
    assert handle["analysis_id"] == "radius"
    assert handle["data_url"] == "/api/custom/radius/{chrom}?format=gosling"

    resp = client.get("/api/custom/radius/chr1")
    assert resp.status_code == 200
    data = resp.json()
    assert "radius" in data  # wrapped under result_key
    assert len(data["radius"]) == 100
    assert data["radius"][0]["chrom"] == "chr1"
    assert "radius" in data["radius"][0]


def test_format_gosling_bare_array(loaded_session):
    dynamic_api.register_analysis("radius", RG_CODE, result_key="radius")
    resp = client.get("/api/custom/radius/chr1?format=gosling")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 100
    assert data[0]["chrom"] == "chr1"


def test_unknown_id_404(loaded_session):
    resp = client.get("/api/custom/does_not_exist/chr1")
    assert resp.status_code == 404


def test_unknown_chrom_404(loaded_session):
    dynamic_api.register_analysis("radius", RG_CODE, result_key="radius")
    resp = client.get("/api/custom/radius/chrZZ")
    assert resp.status_code == 404


def test_no_data_404():
    data_api.current_session = None
    dynamic_api.clear_registry()
    dynamic_api.register_analysis("radius", RG_CODE, result_key="radius")
    resp = client.get("/api/custom/radius/chr1")
    assert resp.status_code == 404
    dynamic_api.clear_registry()


def test_list_custom(loaded_session):
    dynamic_api.register_analysis("radius", RG_CODE, result_key="radius")
    resp = client.get("/api/custom")
    assert resp.status_code == 200
    ids = [a["analysis_id"] for a in resp.json()["analyses"]]
    assert "radius" in ids


def test_region_too_large_413(loaded_session, monkeypatch):
    """Force the spot-count guard by lowering the cap below the fixture size."""
    monkeypatch.setattr(dynamic_api, "MAX_SPOTS", 10)
    dynamic_api.register_analysis("radius", RG_CODE, result_key="radius")
    resp = client.get("/api/custom/radius/chr1")
    assert resp.status_code == 413
