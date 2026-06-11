"""Integration test: WS load_data → REST API data pipeline.

Regression guard for the Phase 1 fix where load_data only set h5cd_path
but never read the ChromData into the session, leaving every REST endpoint
returning 404. Drives the exact message flow the frontend uses.
"""
import os

import pytest
from fastapi.testclient import TestClient

from webapp.backend.main import app
import webapp.backend.data_api as data_api

H5CD = "/Users/bakezq/Coding/U-Chrom/example-data/test_20cells_chr21.h5cd"

pytestmark = pytest.mark.skipif(
    not os.path.exists(H5CD),
    reason="test_20cells_chr21.h5cd not available",
)


@pytest.fixture
def client():
    data_api.current_session = None
    c = TestClient(app)
    yield c
    data_api.current_session = None


def test_umap_404_before_load(client):
    """REST endpoints 404 until data is loaded."""
    assert client.get("/api/umap").status_code == 404


def test_ws_load_data_populates_session(client):
    """WS load_data reads ChromData and sets data_api.current_session."""
    with client.websocket_connect("/ws/main") as wsc:
        wsc.send_json({"type": "load_data", "payload": {"path": H5CD}})
        loaded = wsc.receive_json()
        assert loaded["type"] == "data_loaded"
        assert loaded["n_cells"] == 20
        assert loaded["n_spots"] == 1000
        # Followed by a human-readable text artifact
        artifact = wsc.receive_json()
        assert artifact["type"] == "artifact"
        assert artifact["artifact_type"] == "text"

    assert data_api.current_session is not None
    assert data_api.current_session.chromdata is not None


def test_rest_apis_serve_after_load(client):
    """After load_data, the REST endpoints the frontend calls return data."""
    with client.websocket_connect("/ws/main") as wsc:
        wsc.send_json({"type": "load_data", "payload": {"path": H5CD}})
        wsc.receive_json()  # data_loaded
        wsc.receive_json()  # text artifact

    # UMAP
    r = client.get("/api/umap")
    assert r.status_code == 200
    assert len(r.json()["points"]) == 20

    # Tileset info for a chrom present in the data
    cd = data_api.current_session.chromdata
    chrom = str(cd.spots["chrom"].iloc[0])
    assert client.get(f"/api/tileset_info?d=contact-{chrom}").status_code == 200

    # 3D coords batch
    cell_ids = list(cd.cells.index[:3].astype(str))
    r = client.post("/api/coords/batch", json={"cell_ids": cell_ids})
    assert r.status_code == 200
    assert len(r.content) > 0


def test_load_data_missing_file_errors(client):
    """A non-existent path yields an error message, not a crash."""
    with client.websocket_connect("/ws/main") as wsc:
        wsc.send_json({"type": "load_data", "payload": {"path": "/nope/missing.h5cd"}})
        msg = wsc.receive_json()
        assert msg["type"] == "error"
        assert "not found" in msg["message"].lower()
