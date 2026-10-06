"""Hosted mode: one session per visitor, only atlas datasets, no folder listing, bounded memory."""

import functools
import http.server
import threading

import pytest

pytest.importorskip("cooler")
pytest.importorskip("aiohttp")
from fastapi.testclient import TestClient  # noqa: E402

from tests.core.test_embedded import RES, _store  # noqa: E402
from tests.core.test_remote import _RangeHandler  # noqa: E402
from uchrom.browser.web.hosted import COOKIE, HostedConfig, SessionStores  # noqa: E402
from uchrom.browser.web.server import create_app  # noqa: E402
from chromdata import catalog as atlas, embedded  # noqa: E402


@pytest.fixture
def served(tmp_path):
    import json

    _, emb = _store(tmp_path)
    embedded.embed_links(emb, verbose=False, trans_min_resolution=RES)
    root = tmp_path / "atlas"
    root.mkdir()
    emb.rename(root / "toy.chromdata.zarr")
    for name in ("two.chromdata.zarr", "three.chromdata.zarr"):
        import shutil
        shutil.copytree(root / "toy.chromdata.zarr", root / name)
    cfg = {"datasets": [{"id": n, "store": f"{n}.chromdata.zarr", "path": f"{n}.chromdata.zarr", "title": n}
                        for n in ("toy", "two", "three")]}
    (tmp_path / "d.json").write_text(json.dumps(cfg))
    atlas.build_catalog(tmp_path / "d.json", root, root / "catalog.json")
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_RangeHandler, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _client(root, **cfg):
    return TestClient(create_app(atlas=root, hosted=HostedConfig(**cfg)))


def test_each_visitor_has_their_own_datasets(served):
    app = create_app(atlas=served, hosted=HostedConfig())
    a, b = TestClient(app), TestClient(app)                     # two cookie jars
    r = a.post("/api/datasets", json={"path": f"{served}/toy.chromdata.zarr"})
    assert r.status_code == 200 and COOKIE in a.cookies
    assert [d["name"] for d in a.get("/api/datasets").json()] == ["toy"]
    assert b.get("/api/datasets").json() == []                  # the other visitor sees nothing
    assert a.get(f"/api/datasets/{r.json()['id']}/cells?limit=2").status_code == 200
    assert b.get(f"/api/datasets/{r.json()['id']}/cells?limit=2").status_code == 404


def test_only_the_atlas_can_be_opened(served, tmp_path):
    c = _client(served)
    for bad in (str(tmp_path / "atlas" / "toy.chromdata.zarr"), "/etc/passwd", "https://evil.example/x.chromdata.zarr",
                f"{served}/../toy.chromdata.zarr", f"{served}x/toy.chromdata.zarr", "file:///etc/hosts"):
        r = c.post("/api/datasets", json={"path": bad})
        assert r.status_code == 403, bad
    assert c.get("/api/datasets").json() == []


def test_server_folders_are_not_listed(served):
    c = _client(served)
    assert c.get("/api/files").status_code == 403
    assert c.get("/api/files/places").json() == []
    assert c.get("/api/atlas").json()["catalog"]["datasets"][0]["id"] == "toy"     # the catalog still works


def test_memory_is_bounded(served):
    c = _client(served, max_datasets=2)
    ids = [c.post("/api/datasets", json={"path": f"{served}/{n}.chromdata.zarr"}).json()["name"] for n in ("toy", "two", "three")]
    assert ids == ["toy", "two", "three"]
    assert [d["name"] for d in c.get("/api/datasets").json()] == ["two", "three"]   # the oldest was closed


def test_sessions_expire_and_are_capped():
    now = [0.0]
    st = SessionStores(HostedConfig(allowed_prefixes=["https://a"], max_sessions=2, ttl=10), clock=lambda: now[0])
    from uchrom.browser.web.hosted import reset_session, set_session
    tokens = []
    for sid in ("s1", "s2", "s3"):
        tokens.append(set_session(sid)); st.list(); reset_session(tokens[-1])
    assert st.n_sessions == 2                                    # s1 (idle longest) was dropped
    now[0] = 100.0
    t = set_session("s3"); st.list(); reset_session(t)
    assert st.n_sessions == 1                                    # the idle ones expired


def test_local_mode_is_unchanged(served):
    c = TestClient(create_app(atlas=served))
    assert c.get("/api/files/places").status_code == 200 and c.get("/api/files").status_code == 200


def test_hosted_geometry_is_capped(tmp_path):
    """A hosted server sends at most HostedConfig.max_points points of a 3-D view, whatever the request asks."""
    import json
    import struct

    import numpy as np
    import pandas as pd
    from fastapi.testclient import TestClient

    from uchrom import ChromData
    from uchrom.browser.web.hosted import HostedConfig
    from uchrom.browser.web.server import create_app

    spots = pd.DataFrame({"chrom": "chr1", "start": np.arange(300) * 100, "end": np.arange(300) * 100 + 100,
                          "trace_id": np.repeat(["t0", "t1", "t2"], 100)})
    ChromData(np.random.default_rng(0).normal(size=(300, 3)), spots).write(tmp_path / "x.chromdata.zarr")
    app = create_app(atlas=str(tmp_path), hosted=HostedConfig(allowed_prefixes=[str(tmp_path)], max_points=150))
    c = TestClient(app)
    d = c.post("/api/datasets", json={"path": str(tmp_path / "x.chromdata.zarr")}).json()
    buf = c.post(f"/api/datasets/{d['id']}/geometry", json={"max_points": 10_000}).content
    head = json.loads(buf[4:4 + struct.unpack("<I", buf[:4])[0]])
    assert head["n_points"] == 100 and head["total_points"] == 300 and head["truncated"]
