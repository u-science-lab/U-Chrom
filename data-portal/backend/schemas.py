"""Pydantic response schemas — the API/SDK contract."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class FileEntry(BaseModel):
    label: str
    url: str
    size_mb: float | int | None = None
    format: str = ""


class DatasetSummary(BaseModel):
    id: str
    title: str
    organism: str
    technology: str
    n_cells: int
    n_markers: int
    thumbnail_url: Optional[str] = None

    model_config = {"from_attributes": True}


class DatasetDetail(BaseModel):
    id: str
    title: str
    description: str
    organism: str
    assembly: str
    technology: str
    doi: str
    citation: str
    n_cells: int
    n_traces: int
    n_spots: int
    n_markers: int
    cell_types: dict
    genome_coverage: str
    xyz_unit: str
    files: list[FileEntry]
    notebook_available: bool
    analyzer_url: Optional[str] = None

    model_config = {"from_attributes": True}
