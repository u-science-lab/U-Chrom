"""An atlas: catalog.json built from stores, read from a folder or over HTTP, served by the web browser."""

import functools
import http.server
import json
import threading

import pytest

pytest.importorskip("cooler")
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from tests.core.test_embedded import RES, _store  # noqa: E402
from tests.core.test_remote import _RangeHandler  # noqa: E402
from uchrom.browser.web.data import DatasetStore  # noqa: E402
from uchrom.browser.web.server import create_app  # noqa: E402
from uchrom.core import atlas, embedded  # noqa: E402


@pytest.fixture
def atlas_dir(tmp_path):
    _, emb = _store(tmp_path)
    embedded.embed_links(emb, verbose=False, trans_min_resolution=RES)
    root = tmp_path / "atlas"
    root.mkdir()
    emb.rename(root / "toy.chromdata.zarr")
    cfg = {"title": "Toy atlas", "datasets": [
        {"id": "toy", "store": "toy.chromdata.zarr", "path": "toy.chromdata.zarr", "title": "A toy dataset",
         "paper": "nobody 2026", "license": "CC0"}]}
    (tmp_path / "datasets.json").write_text(json.dumps(cfg))
    atlas.build_catalog(tmp_path / "datasets.json", root, root / "catalog.json")
    return root


def test_catalog_is_read_from_the_stores(atlas_dir):
    cat = json.loads((atlas_dir / "catalog.json").read_text())
    d = cat["datasets"][0]
    assert cat["version"] == 1 and d["title"] == "A toy dataset" and d["license"] == "CC0"
    assert d["n_cells"] == 3 and d["contact_maps"] == 2 and d["images"] == 1
    assert {"Hi-C per spot", "Hi-C bulk", "RNA", "A/B per spot", "images"} <= set(d["modalities"])
    assert d["size_mb"] > 0 and d["files"] > 10


def test_fetch_from_a_folder_gives_urls(atlas_dir):
    cat = atlas.fetch_catalog(str(atlas_dir))
    assert cat["datasets"][0]["url"] == f"{atlas_dir}/toy.chromdata.zarr"


def test_api_atlas_and_off_switch(atlas_dir):
    c = TestClient(create_app(DatasetStore(), atlas=str(atlas_dir)))
    r = c.get("/api/atlas").json()
    assert r["root"] == str(atlas_dir) and r["catalog"]["datasets"][0]["id"] == "toy"
    assert TestClient(create_app(DatasetStore(), atlas="")).get("/api/atlas").json() == {"root": None, "catalog": None}
    assert TestClient(create_app(DatasetStore(), atlas="/no/such/atlas")).get("/api/atlas").status_code == 502


def test_over_http_to_an_open_dataset(atlas_dir):
    pytest.importorskip("aiohttp")
    handler = functools.partial(_RangeHandler, directory=str(atlas_dir))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        root = f"http://127.0.0.1:{srv.server_address[1]}"
        client = TestClient(create_app(DatasetStore(), atlas=root))
        d = client.get("/api/atlas").json()["catalog"]["datasets"][0]
        assert d["url"] == f"{root}/toy.chromdata.zarr"
        opened = client.post("/api/datasets", json={"path": d["url"]})
        assert opened.status_code == 200 and opened.json()["name"] == "toy" and opened.json()["n_cells"] == 3
        assert {m["key"] for m in opened.json()["contact_maps"]} == {"bulk", "cells"}
    finally:
        srv.shutdown()
