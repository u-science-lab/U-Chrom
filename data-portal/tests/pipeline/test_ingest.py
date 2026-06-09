from pathlib import Path
import pytest

from pipeline.ingest import ingest
from pipeline.catalog import CatalogError
from backend.db import make_engine, make_session, Base
from backend.models import Dataset

CATALOG = Path(__file__).resolve().parents[2] / "pipeline" / "catalog" / "mesc_sox2_test.yaml"


def _session(db_path):
    engine = make_engine(db_path)
    Base.metadata.create_all(engine)
    return make_session(engine)


def test_ingest_writes_row(tmp_path):
    db = str(tmp_path / "p.db")
    ingest(str(CATALOG), db_path=db, data_dir=str(tmp_path / "data"))
    Session = _session(db)
    with Session() as s:
        ds = s.get(Dataset, "mesc_sox2_test")
        assert ds is not None
        assert ds.n_traces == 5
        assert ds.organism == "Mus musculus"
        assert ds.files[0]["format"] == "h5cd"


def test_ingest_idempotent(tmp_path):
    db = str(tmp_path / "p.db")
    data = str(tmp_path / "data")
    ingest(str(CATALOG), db_path=db, data_dir=data)
    ingest(str(CATALOG), db_path=db, data_dir=data)  # second run
    Session = _session(db)
    with Session() as s:
        rows = s.query(Dataset).all()
        assert len(rows) == 1  # no duplicate


def test_ingest_bad_h5cd_aborts(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "id: bad_ds\ntitle: Bad\n"
        f"source_h5cd: {tmp_path / 'nonexistent.h5cd'}\n"
    )
    db = str(tmp_path / "p.db")
    with pytest.raises((CatalogError, FileNotFoundError, Exception)):
        ingest(str(bad), db_path=db, data_dir=str(tmp_path / "data"))
    if Path(db).exists():
        Session = _session(db)
        with Session() as s:
            assert s.get(Dataset, "bad_ds") is None
