"""SQLite engine + session factory. DB path from PORTAL_DB_PATH env."""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def default_db_path() -> str:
    env = os.getenv("PORTAL_DB_PATH")
    if env:
        return env
    # data/portal.db relative to the data-portal package root.
    root = Path(__file__).resolve().parent.parent
    return str(root / "data" / "portal.db")


def make_engine(db_path: str | None = None):
    path = db_path or default_db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{path}", future=True)


def make_session(engine):
    return sessionmaker(bind=engine, future=True)
