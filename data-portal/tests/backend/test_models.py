from backend.db import make_engine, make_session, Base
from backend.models import Dataset


def test_create_and_query_dataset(tmp_path):
    engine = make_engine(str(tmp_path / "t.db"))
    Base.metadata.create_all(engine)
    Session = make_session(engine)
    with Session() as s:
        s.add(Dataset(
            id="ds1", title="Test DS", organism="Mus musculus",
            technology="DNA FISH", n_cells=20, n_traces=20, n_spots=1000,
            n_markers=0, cell_types={"A": 12, "B": 8},
            files=[{"label": "x", "url": "http://e/x", "size_mb": 1, "format": "h5cd"}],
            status="published",
        ))
        s.commit()
    with Session() as s:
        got = s.get(Dataset, "ds1")
        assert got.title == "Test DS"
        assert got.cell_types == {"A": 12, "B": 8}
        assert got.files[0]["url"] == "http://e/x"
        assert got.analyzer_url is None
