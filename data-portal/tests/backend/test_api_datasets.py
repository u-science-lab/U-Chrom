import pytest
from fastapi.testclient import TestClient

from backend.db import make_engine, make_session, Base
from backend.models import Dataset


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = str(tmp_path / "p.db")
    monkeypatch.setenv("PORTAL_DB_PATH", db)
    engine = make_engine(db)
    Base.metadata.create_all(engine)
    Session = make_session(engine)
    with Session() as s:
        s.add(Dataset(
            id="ds1", title="DS One", organism="Mus musculus",
            technology="DNA FISH", n_cells=20, n_traces=20, n_spots=1000,
            n_markers=0, cell_types={"A": 20},
            files=[{"label": "x", "url": "http://e/x", "size_mb": 1, "format": "h5cd"}],
            status="published",
        ))
        s.commit()
    from backend.main import app
    return TestClient(app)


def test_list_datasets(client):
    r = client.get("/api/datasets")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["id"] == "ds1"
    assert data[0]["n_cells"] == 20
    assert "files" not in data[0]


def test_get_detail(client):
    r = client.get("/api/datasets/ds1")
    assert r.status_code == 200
    d = r.json()
    assert d["files"][0]["url"] == "http://e/x"
    assert d["cell_types"] == {"A": 20}


def test_get_missing_404(client):
    assert client.get("/api/datasets/nope").status_code == 404


def test_facets(client):
    r = client.get("/api/facets")
    assert r.status_code == 200
    assert "Mus musculus" in r.json()["organism"]


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["n_datasets"] == 1


def test_notebook_unpublished_404(tmp_path, monkeypatch):
    db = str(tmp_path / "p2.db")
    monkeypatch.setenv("PORTAL_DB_PATH", db)
    from backend.db import make_engine, make_session, Base
    from backend.models import Dataset
    engine = make_engine(db)
    Base.metadata.create_all(engine)
    Session = make_session(engine)
    nb_dir = tmp_path / "notebooks"
    nb_dir.mkdir(parents=True, exist_ok=True)
    (nb_dir / "draftds.html").write_text("<html>x</html>")
    with Session() as s:
        s.add(Dataset(id="draftds", title="Draft", status="draft",
                       notebook_html_path="notebooks/draftds.html"))
        s.commit()
    import importlib
    import backend.api.datasets, backend.main
    importlib.reload(backend.api.datasets)
    importlib.reload(backend.main)
    from fastapi.testclient import TestClient
    client = TestClient(backend.main.app)
    assert client.get("/api/datasets/draftds/notebook").status_code == 404
