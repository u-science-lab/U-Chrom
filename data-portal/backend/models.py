"""SQLAlchemy model for the datasets table."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, String, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Dataset(Base):
    __tablename__ = "datasets"

    # identity / search
    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, default="")
    description: Mapped[str] = mapped_column(String, default="")
    organism: Mapped[str] = mapped_column(String, default="", index=True)
    assembly: Mapped[str] = mapped_column(String, default="")
    technology: Mapped[str] = mapped_column(String, default="", index=True)
    doi: Mapped[str] = mapped_column(String, default="")
    citation: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    # stats
    n_cells: Mapped[int] = mapped_column(Integer, default=0)
    n_traces: Mapped[int] = mapped_column(Integer, default=0)
    n_spots: Mapped[int] = mapped_column(Integer, default=0)
    n_markers: Mapped[int] = mapped_column(Integer, default=0)
    cell_types: Mapped[dict] = mapped_column(JSON, default=dict)
    genome_coverage: Mapped[str] = mapped_column(String, default="")
    xyz_unit: Mapped[str] = mapped_column(String, default="")
    resolution: Mapped[dict] = mapped_column(JSON, default=dict)

    # external hosting + artifacts
    files: Mapped[list] = mapped_column(JSON, default=list)
    notebook_html_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    analyzer_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="published", index=True)
