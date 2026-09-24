"""HTTP API tests for the web browser (``API.md``)."""

import numpy as np
import pandas as pd
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from uchrom import ChromData  # noqa: E402
from uchrom.browser.web import create_app, decode_geometry  # noqa: E402
from uchrom.browser.web.data import DatasetStore  # noqa: E402


@pytest.fixture
def client(tmp_path):
    spots = pd.DataFrame({
        "chrom": ["chr1"] * 4 + ["chr2"] * 2,
        "start": [0, 10, 20, 30, 0, 10],
        "end": [10, 20, 30, 40, 10, 20],
        "trace_id": ["a"] * 4 + ["b"] * 2,
    })
    cd = ChromData(np.arange(18, dtype=float).reshape(6, 3), spots)
    path = tmp_path / "toy.h5cd"
    cd.write(path)
    store = DatasetStore()
    store.load(path)
    return TestClient(create_app(store)), path


def test_health_and_list(client):
    c, path = client
    health = c.get("/api/health").json()
    assert health["status"] == "ok"
    # the committed bundle, so the page can tell a server older than itself
    html = (Path(__file__).resolve().parents[2] / "uchrom/browser/web/static/index.html").read_text()
    assert health["bundle"] and f"assets/{health['bundle']}" in html
    ds = c.get("/api/datasets").json()
    assert len(ds) == 1 and ds[0]["id"] == "d1" and ds[0]["path"] == str(path.resolve())
    assert [x["name"] for x in ds[0]["chroms"]] == ["chr1", "chr2"]


def test_load_and_delete(client, tmp_path):
    c, path = client
    r = c.post("/api/datasets", json={"path": str(path)})
    assert r.status_code == 200 and r.json()["id"] == "d2"
    assert c.post("/api/datasets", json={"path": str(tmp_path / "missing.h5cd")}).status_code == 400
    bad = tmp_path / "bad.h5cd"
    bad.write_text("not hdf5")
    assert c.post("/api/datasets", json={"path": str(bad)}).status_code == 400
    assert c.delete("/api/datasets/d2").status_code == 204
    assert c.delete("/api/datasets/d2").status_code == 404
    assert [d["id"] for d in c.get("/api/datasets").json()] == ["d1"]


def test_traces(client):
    c, _ = client
    t = c.get("/api/datasets/d1/traces", params={"chrom": "chr2"}).json()
    assert t == {"total": 1, "traces": [{"trace_id": "b", "chrom": "chr2", "cell_id": None,
                                          "n_spots": 2, "start": 0, "end": 20}]}
    assert c.get("/api/datasets/nope/traces").status_code == 404
    assert c.get("/api/datasets/d1/traces", params={"limit": 0}).status_code == 422


def test_geometry_binary(client):
    c, _ = client
    r = c.post("/api/datasets/d1/geometry",
               json={"region": {"chrom": "chr1", "start": 5, "end": 25}})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/octet-stream"
    g = decode_geometry(r.content)
    assert g["header"]["n_points"] == 3
    assert list(g["starts"]) == [0, 10, 20]
    np.testing.assert_array_equal(g["positions"][0], [0, 1, 2])

    assert c.post("/api/datasets/d1/geometry",
                  json={"region": {"chrom": "chr1", "start": 9, "end": 9}}).status_code == 422
    assert c.post("/api/datasets/d1/geometry", json={"max_points": 0}).status_code == 422
    assert c.post("/api/datasets/zz/geometry", json={}).status_code == 404


def test_root_serves_frontend_or_build_hint(client):
    c, _ = client
    r = c.get("/")
    assert r.status_code == 200
    assert "U-Chrom" in r.text


def test_cli_serves_over_http(tmp_path):
    """`python -m uchrom.browser --web file` starts a working server."""
    import json
    import socket
    import subprocess
    import sys
    import time
    import urllib.request

    pytest.importorskip("uvicorn")
    path = tmp_path / "cli.h5cd"
    spots = pd.DataFrame({"chrom": ["chr1"] * 3, "start": [0, 10, 20],
                          "end": [10, 20, 30], "trace_id": ["a"] * 3})
    ChromData(np.zeros((3, 3)), spots).write(path)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, "-m", "uchrom.browser", str(path), "--web",
         f"--port={port}", "--noopen_browser"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        url = f"http://127.0.0.1:{port}/api/datasets"
        for _ in range(100):
            try:
                with urllib.request.urlopen(url, timeout=1) as r:
                    datasets = json.load(r)
                break
            except OSError:
                if proc.poll() is not None:
                    pytest.fail(proc.stdout.read().decode())
                time.sleep(0.1)
        else:
            pytest.fail("server did not come up")
        assert datasets[0]["name"] == "cli" and datasets[0]["n_spots"] == 3
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_cells_endpoint_and_cell_filter(tmp_path):
    spots = pd.DataFrame({"chrom": ["chr1"] * 4, "start": [0, 10, 0, 10], "end": [10, 20, 10, 20],
                          "trace_id": ["a", "a", "b", "b"], "cell_id": ["c10", "c10", "c2", "c2"]})
    path = tmp_path / "cells.h5cd"
    ChromData(np.arange(12, dtype=float).reshape(4, 3), spots).write(path)
    store = DatasetStore()
    store.load(path)
    c = TestClient(create_app(store))
    cells = c.get("/api/datasets/d1/cells").json()
    assert [x["cell_id"] for x in cells["cells"]] == ["c2", "c10"]
    g = decode_geometry(c.post("/api/datasets/d1/geometry", json={"cell_ids": ["c10"]}).content)
    assert [s["trace_id"] for s in g["header"]["segments"]] == ["a"]
    assert c.get("/api/datasets/zz/cells").status_code == 404


def test_cell_fields_and_points_endpoints(tmp_path):
    spots = pd.DataFrame({"chrom": ["chr1"] * 4, "start": [0, 10, 0, 10], "end": [10, 20, 10, 20],
                          "trace_id": ["a", "a", "b", "b"], "cell_id": ["c1", "c1", "c2", "c2"]})
    cells = pd.DataFrame({"nucleus_area_um2": [150.5, np.nan], "rna.Nanog": [3, 12], "label": ["x", "y"]},
                         index=pd.Index(["c1", "c2"], name="cell_id"))
    rna = pd.DataFrame({"x": [0.1, 0.2, 0.3], "y": [0.0, 0.0, 0.0], "z": [1.0, 1.0, 1.0],
                        "gene": ["Nanog", "Sox2", "Nanog"], "cell_id": ["c1", "c2", "c2"],
                        "spot_id": [1, 2, 3], "peak_intensity": [100, 200, np.nan]})
    path = tmp_path / "multi.h5cd"
    ChromData(np.arange(12, dtype=float).reshape(4, 3), spots, cells=cells, points={"rna": rna}).write(path)
    store = DatasetStore()
    store.load(path)
    c = TestClient(create_app(store))

    s = c.get("/api/datasets").json()[0]
    assert [(f["name"], f["group"], f["label"]) for f in s["cell_fields"]] == [
        ("nucleus_area_um2", "cell", "nucleus_area_um2"), ("rna.Nanog", "rna", "Nanog")]
    assert s["cell_fields"][0]["n_valid"] == 1
    assert s["point_sets"] == [{"name": "rna", "n_points": 3, "label_field": "gene",
                                "labels": [{"value": "Nanog", "count": 2}, {"value": "Sox2", "count": 1}],
                                "value_fields": ["peak_intensity"]}]

    v = c.get("/api/datasets/d1/cell_values", params={"field": "nucleus_area_um2"}).json()
    assert v == {"field": "nucleus_area_um2", "kind": "numeric", "cell_ids": ["c1", "c2"], "values": [150.5, None]}
    assert c.get("/api/datasets/d1/cell_values", params={"field": "label"}).status_code == 404

    info = c.get("/api/datasets/d1/cell_info", params={"cell_id": "c2"}).json()
    assert info == {"cell_id": "c2", "fields": {"nucleus_area_um2": None, "rna.Nanog": 12, "label": "y"}}
    assert c.get("/api/datasets/d1/cell_info", params={"cell_id": "zz"}).status_code == 404

    allp = c.post("/api/datasets/d1/points/rna").json()
    assert allp["n"] == 3 and allp["labels"] == ["Nanog", "Sox2", "Nanog"]
    assert allp["values"] == {"peak_intensity": [100, 200, None]}
    one = c.post("/api/datasets/d1/points/rna", json={"cell_ids": ["c2"], "labels": ["Nanog"]}).json()
    assert one == {"n": 1, "positions": [0.3, 0.0, 1.0], "cell_ids": ["c2"], "labels": ["Nanog"],
                   "values": {"peak_intensity": [None]}}
    assert c.post("/api/datasets/d1/points/nope").status_code == 404


def test_embedding_endpoint(tmp_path):
    spots = pd.DataFrame({"chrom": ["chr1"] * 2, "start": [0, 10], "end": [10, 20],
                          "trace_id": ["a", "b"], "cell_id": ["c1", "c2"]})
    cells = pd.DataFrame({"rna.A": [1, 2]}, index=pd.Index(["c1", "c2"], name="cell_id"))
    cellm = {"rna_pca": np.array([[0.5, 1.5, 2.5], [-1.0, np.nan, 0.0]]),
             "rna_umap": np.array([[1.0, 2.0], [3.0, 4.0]]), "scalar": np.array([1.0, 2.0])}
    uns = {"embeddings": {"rna_pca": {"method": "pca", "source": "rna", "label": "RNA PCA", "axis_prefix": "PC"}}}
    path = tmp_path / "emb.h5cd"
    ChromData(np.zeros((2, 3)), spots, cells=cells, cellm=cellm, uns=uns).write(path)
    store = DatasetStore()
    store.load(path)
    c = TestClient(create_app(store))
    embs = c.get("/api/datasets").json()[0]["embeddings"]
    assert embs == [{"key": "rna_pca", "method": "pca", "source": "rna", "label": "RNA PCA", "n_dims": 3},
                    {"key": "rna_umap", "method": None, "source": None, "label": "rna_umap", "n_dims": 2}]
    e = c.get("/api/datasets/d1/embedding/rna_pca", params={"dims": "1,2"}).json()
    assert e == {"key": "rna_pca", "label": "RNA PCA", "cell_ids": ["c1", "c2"],
                 "x": [1.5, None], "y": [2.5, 0.0], "axis_labels": ["PC2", "PC3"]}
    assert c.get("/api/datasets/d1/embedding/rna_pca", params={"dims": "0,3"}).status_code == 422
    assert c.get("/api/datasets/d1/embedding/scalar").status_code == 404


def test_categorical_cell_fields(tmp_path):
    n = 6
    ids = [f"c{i}" for i in range(n)]
    spots = pd.DataFrame({"chrom": "chr1", "start": 0, "end": 1, "trace_id": ids, "cell_id": ids})
    cells = pd.DataFrame({"cell_type": ["L5IT", "Astro", "L5IT", "Astro", "L23IT", "L5IT"],
                          "barcode": [f"b{i}" for i in range(n)]}, index=pd.Index(ids, name="cell_id"))
    path = tmp_path / "cat.h5cd"
    ChromData(np.zeros((n, 3)), spots, cells=cells).write(path)
    store = DatasetStore()
    store.load(path)
    c = TestClient(create_app(store))
    fields = c.get("/api/datasets").json()[0]["cell_fields"]
    assert [f["name"] for f in fields] == ["cell_type"]  # the per-cell barcode is not offered
    assert fields[0]["kind"] == "category"
    # natural order: numbers inside names compare numerically (L5IT < L23IT)
    assert fields[0]["categories"] == [{"value": "Astro", "count": 2}, {"value": "L5IT", "count": 3},
                                       {"value": "L23IT", "count": 1}]
    v = c.get("/api/datasets/d1/cell_values", params={"field": "cell_type"}).json()
    assert v["kind"] == "category" and v["values"][:2] == ["L5IT", "Astro"]
