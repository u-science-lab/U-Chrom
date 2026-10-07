"""The web browser lists an atlas (``/api/atlas``, from a folder or over HTTP) and opens its datasets."""

import pytest

pytest.importorskip("cooler")
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from chromdata.testing import example_atlas, serve_directory  # noqa: E402
from uchrom_browser.data import DatasetStore  # noqa: E402
from uchrom_browser.server import create_app  # noqa: E402


@pytest.fixture
def atlas_dir(tmp_path):
    return example_atlas(tmp_path)


def test_api_atlas_and_off_switch(atlas_dir):
    c = TestClient(create_app(DatasetStore(), atlas=str(atlas_dir)))
    r = c.get("/api/atlas").json()
    assert r["root"] == str(atlas_dir) and r["catalog"]["datasets"][0]["id"] == "toy"
    assert TestClient(create_app(DatasetStore(), atlas="")).get("/api/atlas").json() == {"root": None, "catalog": None}
    assert TestClient(create_app(DatasetStore(), atlas="/no/such/atlas")).get("/api/atlas").status_code == 502


def test_over_http_to_an_open_dataset(atlas_dir):
    pytest.importorskip("aiohttp")
    with serve_directory(atlas_dir) as root:
        client = TestClient(create_app(DatasetStore(), atlas=root))
        d = client.get("/api/atlas").json()["catalog"]["datasets"][0]
        assert d["url"] == f"{root}/toy.chromdata.zarr"
        opened = client.post("/api/datasets", json={"path": d["url"]})
        assert opened.status_code == 200 and opened.json()["name"] == "toy" and opened.json()["n_cells"] == 3
        assert {m["key"] for m in opened.json()["contact_maps"]} == {"bulk", "cells"}
