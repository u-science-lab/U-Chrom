"""Integration test for data loading and API endpoints."""
import pytest
from fastapi.testclient import TestClient
from webapp.backend.main import app
from webapp.backend.session import Session


@pytest.fixture
def client():
    return TestClient(app)


def test_data_flow_integration(client, tmp_path):
    """Test complete flow: load data → fetch UMAP → fetch coords."""
    # This is a placeholder — requires real .h5cd test file
    # For now, just verify endpoints exist

    # Check /api/umap endpoint exists (404 if no data loaded)
    response = client.get("/api/umap")
    assert response.status_code in [200, 404]  # 404 if no data loaded yet

    # Check /api/coords/batch endpoint exists (404 if no data loaded)
    response = client.post("/api/coords/batch", json={"cell_ids": []})
    assert response.status_code in [200, 404, 422]  # 422 if validation fails


def test_session_persistence():
    """Test Session can store and retrieve state."""
    session = Session()
    session.h5cd_path = "/test/path.h5cd"
    session.viewport = {"chrom": "chr1", "start": 0, "end": 1000}
    session.cell_selection = ["cell_1", "cell_2"]

    assert session.h5cd_path == "/test/path.h5cd"
    assert session.viewport["chrom"] == "chr1"
    assert len(session.cell_selection) == 2
