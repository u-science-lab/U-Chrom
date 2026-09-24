"""FastAPI app for the U-Chrom web browser (see ``API.md``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .data import DEFAULT_MAX_POINTS, DatasetStore, GeometryFilter

STATIC_DIR = Path(__file__).with_name("static")


class LoadRequest(BaseModel):
    path: str


class Region(BaseModel):
    chrom: str
    start: int
    end: int


class GeometryRequest(BaseModel):
    chroms: Optional[List[str]] = None
    region: Optional[Region] = None
    trace_ids: Optional[List[str]] = None
    max_points: int = DEFAULT_MAX_POINTS


def create_app(store: Optional[DatasetStore] = None) -> FastAPI:
    """Build the app around ``store`` (a fresh empty one by default)."""
    store = store if store is not None else DatasetStore()
    app = FastAPI(title="U-Chrom browser", docs_url="/api/docs",
                  openapi_url="/api/openapi.json")
    app.state.store = store

    def _dataset(dataset_id: str):
        try:
            return store.get(dataset_id)
        except KeyError:
            raise HTTPException(404, f"unknown dataset: {dataset_id}") from None

    @app.get("/api/health")
    def health() -> Dict[str, Any]:
        from uchrom import __version__
        return {"status": "ok", "version": __version__}

    @app.get("/api/datasets")
    def list_datasets() -> List[Dict[str, Any]]:
        return [ds.summary() for ds in store.list()]

    @app.post("/api/datasets")
    def load_dataset(req: LoadRequest) -> Dict[str, Any]:
        try:
            return store.load(req.path).summary()
        except FileNotFoundError as exc:
            raise HTTPException(400, str(exc)) from None
        except Exception as exc:  # unreadable / wrong format
            raise HTTPException(400, f"cannot load {req.path}: {exc}") from None

    @app.delete("/api/datasets/{dataset_id}", status_code=204)
    def delete_dataset(dataset_id: str) -> Response:
        _dataset(dataset_id)
        store.remove(dataset_id)
        return Response(status_code=204)

    @app.get("/api/datasets/{dataset_id}/traces")
    def list_traces(dataset_id: str, chrom: Optional[str] = None,
                    offset: int = Query(0, ge=0),
                    limit: int = Query(500, ge=1, le=100_000)) -> Dict[str, Any]:
        return _dataset(dataset_id).traces(chrom=chrom, offset=offset, limit=limit)

    @app.post("/api/datasets/{dataset_id}/geometry")
    def geometry(dataset_id: str, req: GeometryRequest) -> Response:
        ds = _dataset(dataset_id)
        try:
            flt = GeometryFilter(
                chroms=req.chroms,
                region=None if req.region is None else req.region.model_dump(),
                trace_ids=req.trace_ids,
                max_points=req.max_points,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return Response(ds.geometry(flt), media_type="application/octet-stream")

    if (STATIC_DIR / "index.html").is_file():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    else:
        @app.get("/", response_class=HTMLResponse)
        def missing_frontend() -> str:
            return (
                "<h1>U-Chrom browser</h1><p>The frontend has not been built. "
                "Run <code>npm install &amp;&amp; npm run build</code> in "
                "<code>uchrom/browser/web/frontend</code>.</p>"
            )

    return app
