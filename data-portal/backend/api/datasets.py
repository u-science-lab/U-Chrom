"""Read-only REST endpoints for datasets."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select

from backend.db import Base, default_db_path, make_engine, make_session
from backend.models import Dataset
from backend.schemas import DatasetDetail, DatasetSummary

router = APIRouter(prefix="/api")

SLUG_RE = re.compile(r"^[a-z0-9_]+$")

_engine = make_engine()
Base.metadata.create_all(_engine)
_Session = make_session(_engine)


def _data_root() -> Path:
    return Path(default_db_path()).parent


@router.get("/datasets", response_model=list[DatasetSummary])
def list_datasets(
    organism: str | None = Query(None),
    technology: str | None = Query(None),
    q: str | None = Query(None),
):
    with _Session() as s:
        stmt = select(Dataset).where(Dataset.status == "published")
        if organism:
            stmt = stmt.where(Dataset.organism == organism)
        if technology:
            stmt = stmt.where(Dataset.technology == technology)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(Dataset.title.like(like) | Dataset.description.like(like))
        rows = s.scalars(stmt).all()
        return [
            DatasetSummary(
                id=r.id, title=r.title, organism=r.organism,
                technology=r.technology, n_cells=r.n_cells, n_markers=r.n_markers,
                thumbnail_url=(f"/api/datasets/{r.id}/thumbnail" if r.thumbnail_path else None),
            )
            for r in rows
        ]


@router.get("/facets")
def facets():
    with _Session() as s:
        rows = s.scalars(select(Dataset).where(Dataset.status == "published")).all()
        return {
            "organism": sorted({r.organism for r in rows if r.organism}),
            "technology": sorted({r.technology for r in rows if r.technology}),
        }


@router.get("/health")
def health():
    with _Session() as s:
        n = len(s.scalars(select(Dataset)).all())
    return {"status": "ok", "n_datasets": n}


@router.get("/datasets/{dataset_id}", response_model=DatasetDetail)
def get_dataset(dataset_id: str):
    if not SLUG_RE.match(dataset_id):
        raise HTTPException(status_code=404, detail="not found")
    with _Session() as s:
        r = s.get(Dataset, dataset_id)
        if r is None or r.status != "published":
            raise HTTPException(status_code=404, detail="not found")
        return DatasetDetail(
            id=r.id, title=r.title, description=r.description, organism=r.organism,
            assembly=r.assembly, technology=r.technology, doi=r.doi, citation=r.citation,
            n_cells=r.n_cells, n_traces=r.n_traces, n_spots=r.n_spots, n_markers=r.n_markers,
            cell_types=r.cell_types or {}, genome_coverage=r.genome_coverage,
            xyz_unit=r.xyz_unit, files=r.files or [],
            notebook_available=bool(r.notebook_html_path), analyzer_url=r.analyzer_url,
        )


@router.get("/datasets/{dataset_id}/notebook")
def get_notebook(dataset_id: str):
    if not SLUG_RE.match(dataset_id):
        raise HTTPException(status_code=404, detail="not found")
    with _Session() as s:
        r = s.get(Dataset, dataset_id)
        if r is None or r.status != "published" or not r.notebook_html_path:
            raise HTTPException(status_code=404, detail="notebook unavailable")
        nb_dir = (_data_root() / "notebooks").resolve()
        target = (_data_root() / r.notebook_html_path).resolve()
        if not target.is_relative_to(nb_dir) or not target.exists():
            raise HTTPException(status_code=404, detail="notebook unavailable")
        return FileResponse(str(target), media_type="text/html")
