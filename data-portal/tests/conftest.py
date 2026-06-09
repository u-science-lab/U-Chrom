import sys
from pathlib import Path
import pytest

# Make `backend` and `pipeline` importable as top-level packages.
DATA_PORTAL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DATA_PORTAL))

# Repo root (worktree) — for locating example-data fixtures.
REPO_ROOT = DATA_PORTAL.parent


@pytest.fixture
def rich_h5cd() -> str:
    """A ChromData fixture with cells (cell_type) and uns metadata."""
    p = REPO_ROOT / "example-data" / "test_20cells_chr21.h5cd"
    if not p.exists():
        pytest.skip(f"fixture missing: {p}")
    return str(p)


@pytest.fixture
def minimal_h5cd() -> str:
    """A minimal ChromData fixture: no cells, no tracks, no uns."""
    p = REPO_ROOT / "example-data" / "mESC_Sox2_5cells_wnan.h5cd"
    if not p.exists():
        pytest.skip(f"fixture missing: {p}")
    return str(p)


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """A temporary SQLite DB path, isolated per test."""
    db_path = tmp_path / "portal.db"
    monkeypatch.setenv("PORTAL_DB_PATH", str(db_path))
    return str(db_path)
