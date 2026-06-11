"""Integration test for code execution endpoint."""
import pytest
from fastapi.testclient import TestClient
from webapp.backend.main import app
from webapp.backend.notebook_api import start_kernel, stop_kernel


@pytest.fixture
def client():
    start_kernel()
    yield TestClient(app)
    stop_kernel()


def test_execute_code_simple(client):
    """Execute simple code via REST API."""
    response = client.post("/api/execute_code", json={"code": "2 + 2"})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "ok"
    assert "4" in result["output"]


def test_execute_code_no_code(client):
    """Request without code returns error."""
    response = client.post("/api/execute_code", json={})
    assert response.status_code == 200
    assert "error" in response.json()
