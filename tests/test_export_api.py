"""Tests for /api/export SVG generation."""
import pytest
from fastapi.testclient import TestClient
from webapp.backend.main import app

client = TestClient(app)

FIGURE_STATE = {
    "panels": [
        {"id": "fp1", "label": "3D Structure", "x": 8, "y": 8, "w": 320, "h": 180},
        {"id": "fp2", "label": "Contact Map", "x": 348, "y": 8, "w": 320, "h": 180},
    ],
    "style": {
        "sizePreset": "nature-double",
        "fontSize": 7,
        "colormap": "RdBu",
        "vmin": -2,
        "vmax": 2,
    },
}


def test_export_returns_url():
    r = client.post("/api/export", json={"figure_state": FIGURE_STATE, "format": "svg"})
    assert r.status_code == 200
    body = r.json()
    assert "url" in body
    assert body["url"].endswith(".svg")


def test_export_svg_is_downloadable():
    r = client.post("/api/export", json={"figure_state": FIGURE_STATE, "format": "svg"})
    url = r.json()["url"]
    # Download the generated file
    dl = client.get(url)
    assert dl.status_code == 200
    content = dl.text
    assert content.startswith("<?xml") or content.startswith("<svg")
    assert "3D Structure" in content
    assert "Contact Map" in content


def test_export_svg_has_correct_dimensions():
    r = client.post("/api/export", json={"figure_state": FIGURE_STATE, "format": "svg"})
    url = r.json()["url"]
    svg = client.get(url).text
    # nature-double is 692x460
    assert "692" in svg
    assert "460" in svg
