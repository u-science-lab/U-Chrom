import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTAL_DB_PATH", str(tmp_path / "p.db"))
    from backend.db import make_engine, Base
    Base.metadata.create_all(make_engine(str(tmp_path / "p.db")))
    import importlib
    import backend.api.datasets, backend.main
    importlib.reload(backend.api.datasets)
    importlib.reload(backend.main)
    from backend.main import app
    return TestClient(app)


@pytest.mark.parametrize("attack", [
    "../../../etc/passwd",
    "..%2f..%2fsecret",
    "foo/bar",
    "Foo_Bar",      # uppercase not in slug whitelist
    "foo bar",
])
def test_notebook_rejects_bad_ids(client, attack):
    r = client.get(f"/api/datasets/{attack}/notebook")
    assert r.status_code == 404


@pytest.mark.parametrize("attack", ["../../etc", "Foo", "a b"])
def test_detail_rejects_bad_ids(client, attack):
    r = client.get(f"/api/datasets/{attack}")
    assert r.status_code == 404
