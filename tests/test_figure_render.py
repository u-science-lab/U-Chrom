"""Tests for figure_render API endpoint."""
from fastapi.testclient import TestClient
from webapp.backend.main import app

client = TestClient(app)


def test_figure_render_empty_panels():
    resp = client.post("/api/figure_render", json={
        "panels": [],
        "style": {"sizePreset": "nature-double", "fontSize": 7}
    })
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/svg+xml")
    assert b"<svg" in resp.content
    assert b'width="692"' in resp.content
    assert b'height="460"' in resp.content


def test_figure_render_with_panel():
    resp = client.post("/api/figure_render", json={
        "panels": [{"id": "p1", "label": "Structure", "x": 10, "y": 10, "w": 300, "h": 200}],
        "style": {"sizePreset": "nature-double", "fontSize": 7}
    })
    assert resp.status_code == 200
    svg = resp.text
    assert "Structure" in svg
    assert "<rect" in svg
    assert "<text" in svg


def test_figure_render_with_image():
    # Minimal 1x1 PNG base64
    tiny_png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    resp = client.post("/api/figure_render", json={
        "panels": [{"id": "p1", "label": "Test", "x": 0, "y": 0, "w": 100, "h": 80, "image": tiny_png}],
        "style": {}
    })
    assert resp.status_code == 200
    svg = resp.text
    assert "xlink:href" in svg
    assert "<image" in svg


def test_figure_render_size_preset_nature_single():
    resp = client.post("/api/figure_render", json={
        "panels": [],
        "style": {"sizePreset": "nature-single"}
    })
    assert resp.status_code == 200
    assert b'width="336"' in resp.content
    assert b'height="280"' in resp.content


def test_figure_render_content_disposition():
    resp = client.post("/api/figure_render", json={"panels": []})
    assert resp.status_code == 200
    assert "figure.svg" in resp.headers.get("content-disposition", "")
