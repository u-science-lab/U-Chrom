"""HTTP API tests for the web browser (``API.md``)."""

import numpy as np
import pandas as pd
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
    assert c.get("/api/health").json()["status"] == "ok"
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
