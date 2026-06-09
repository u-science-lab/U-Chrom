"""Tests for figure_render API endpoint."""
import pytest
from fastapi.testclient import TestClient
from webapp.backend.main import app

client = TestClient(app)


def test_figure_render_empty_panels():
    resp = client.post("/api/figure_render", json={
        "panels": [],
        "style": {"sizePreset": "nature-double", "fontSize": 7}
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "svg" in data
    assert "url" in data
    assert "<svg" in data["svg"]


def test_figure_render_with_panel():
    resp = client.post("/api/figure_render", json={
        "panels": [{"id": "p1", "label": "Structure", "x": 10, "y": 10, "w": 300, "h": 200}],
        "style": {"sizePreset": "nature-double", "fontSize": 7}
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "Structure" in data["svg"]
    assert 'rect' in data["svg"]


def test_figure_render_with_image():
    # Minimal 1x1 PNG base64
    tiny_png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    resp = client.post("/api/figure_render", json={
        "panels": [{"id": "p1", "label": "Test", "x": 0, "y": 0, "w": 100, "h": 80, "image": tiny_png}],
        "style": {}
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "xlink:href" in data["svg"]
    assert "image" in data["svg"]
