"""FastAPI app for the U-Chrom web browser (see ``API.md``)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .data import DEFAULT_MAX_POINTS, DatasetStore, GeometryFilter

STATIC_DIR = Path(__file__).with_name("static")


def _bundle_id() -> Optional[str]:
    """Name of the JS bundle the page loads (changes on every frontend build).

    Read once at start-up: a page that reports a different bundle was built
    after this server started, i.e. the server runs stale backend code.
    """
    try:
        m = re.search(r"assets/(index-[^\"']+\.js)", (STATIC_DIR / "index.html").read_text())
    except OSError:
        return None
    return m.group(1) if m else None


class LoadRequest(BaseModel):
    path: str


class Region(BaseModel):
    chrom: str
    start: int
    end: int


class PointsRequest(BaseModel):
    cell_ids: Optional[List[str]] = None
    labels: Optional[List[str]] = None


class GroupRequest(BaseModel):
    cells: List[str]
    name: Optional[str] = None


class GeometryRequest(BaseModel):
    chroms: Optional[List[str]] = None
    region: Optional[Region] = None
    trace_ids: Optional[List[str]] = None
    cell_ids: Optional[List[str]] = None
    max_points: int = DEFAULT_MAX_POINTS


def create_app(store: Optional[DatasetStore] = None, atlas: Optional[str] = None, hosted: Optional[Any] = None) -> FastAPI:
    """Build the app around ``store`` (a fresh empty one by default).  ``atlas``: root of the atlas the
    Open dialog lists (URL or folder; default ``UCHROM_ATLAS`` or :data:`uchrom.core.atlas.DEFAULT_ATLAS`;
    an empty string turns it off)."""
    import os

    from ...core.atlas import DEFAULT_ATLAS

    atlas = atlas if atlas is not None else os.environ.get("UCHROM_ATLAS", DEFAULT_ATLAS)
    if hosted is not None:     # the server of a public atlas: sessions, only atlas datasets, no folder listing
        from . import data as _data
        from .hosted import COOKIE, SessionStores, new_session_id, reset_session, set_session

        if not hosted.allowed_prefixes and atlas:
            hosted.allowed_prefixes = [atlas]
        _data.PSEUDOBULK_MAX_CELLS = min(_data.PSEUDOBULK_MAX_CELLS, int(hosted.max_pseudobulk_cells))
        store = SessionStores(hosted)
    store = store if store is not None else DatasetStore()
    app = FastAPI(title="U-Chrom browser", docs_url="/api/docs",
                  openapi_url="/api/openapi.json")
    app.state.store = store
    if hosted is not None:
        @app.middleware("http")
        async def _session(request, call_next):
            sid = request.cookies.get(COOKIE) or ""
            fresh = not sid
            if fresh:
                sid = new_session_id()
            token = set_session(sid)
            try:
                response = await call_next(request)
            finally:
                reset_session(token)
            if fresh:
                response.set_cookie(COOKIE, sid, httponly=True, samesite="lax", secure=request.url.scheme == "https",
                                    max_age=int(hosted.ttl))
            return response
    bundle = _bundle_id()

    def _dataset(dataset_id: str):
        try:
            return store.get(dataset_id)
        except KeyError:
            raise HTTPException(404, f"unknown dataset: {dataset_id}") from None

    @app.get("/api/health")
    def health() -> Dict[str, Any]:
        from uchrom import __version__
        return {"status": "ok", "version": __version__, "bundle": bundle, "hosted": hosted is not None}

    @app.get("/api/datasets")
    def list_datasets() -> List[Dict[str, Any]]:
        return [ds.summary() for ds in store.list()]

    @app.post("/api/datasets")
    def load_dataset(req: LoadRequest) -> Dict[str, Any]:
        try:
            return store.load(req.path).summary()
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from None
        except FileNotFoundError as exc:
            raise HTTPException(400, str(exc)) from None
        except Exception as exc:  # unreadable / wrong format
            raise HTTPException(400, f"cannot load {req.path}: {exc}") from None

    @app.get("/api/files")
    def files(path: Optional[str] = None, hidden: bool = False) -> Dict[str, Any]:
        if hosted is not None:
            raise HTTPException(403, "the server's folders cannot be listed on a hosted server")
        from .files import list_dir
        try:
            return list_dir(path, show_hidden=hidden)
        except (FileNotFoundError, NotADirectoryError) as exc:
            raise HTTPException(404, str(exc)) from None
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from None

    _atlas_cache: Dict[str, Any] = {}

    @app.get("/api/atlas")
    def atlas_catalog(refresh: bool = False) -> Dict[str, Any]:
        """The atlas catalog (fetched here, so the page needs no CORS; cached 5 min): ``{"root", "catalog"}``,
        every dataset with its ``url``; ``{"root": null}`` when no atlas is configured."""
        import time

        from ...core.atlas import fetch_catalog

        if not atlas:
            return {"root": None, "catalog": None}
        hit = _atlas_cache.get("c")
        if hit is None or refresh or time.time() - hit[0] > 300:
            try:
                _atlas_cache["c"] = hit = (time.time(), fetch_catalog(atlas))
            except Exception as exc:
                raise HTTPException(502, f"cannot read the atlas catalog at {atlas}: {type(exc).__name__}: {exc}") from None
        return {"root": atlas, "catalog": hit[1]}

    @app.get("/api/files/places")
    def file_places() -> List[Dict[str, str]]:
        if hosted is not None:
            return []
        from .files import places
        return places(ds.path for ds in store.list())

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

    @app.get("/api/datasets/{dataset_id}/cells")
    def list_cells(dataset_id: str, offset: int = Query(0, ge=0),
                   limit: int = Query(500, ge=1, le=100_000)) -> Dict[str, Any]:
        return _dataset(dataset_id).cells(offset=offset, limit=limit)

    @app.get("/api/datasets/{dataset_id}/cell_values")
    def cell_values(dataset_id: str, field: str) -> Dict[str, Any]:
        try:
            return _dataset(dataset_id).cell_values(field)
        except KeyError:
            raise HTTPException(404, f"unknown cell field: {field}") from None

    @app.get("/api/datasets/{dataset_id}/cell_info")
    def cell_info(dataset_id: str, cell_id: str) -> Dict[str, Any]:
        try:
            return _dataset(dataset_id).cell_info(cell_id)
        except KeyError:
            raise HTTPException(404, f"unknown cell: {cell_id}") from None

    def _call(fn, *args, **kwargs):
        """Map data-layer errors to HTTP: unknown key → 404, bad input → 422."""
        try:
            return fn(*args, **kwargs)
        except KeyError as exc:
            raise HTTPException(404, f"not found: {exc.args[0] if exc.args else exc}") from None
        except LookupError as exc:  # e.g. empty selection, per-cell map without a cell
            raise HTTPException(422, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    def _names(names: str) -> List[str]:
        return [n for n in (x.strip() for x in names.split(",")) if n]

    @app.post("/api/datasets/{dataset_id}/groups")
    def register_group(dataset_id: str, req: GroupRequest) -> Dict[str, Any]:
        return _call(_dataset(dataset_id).register_group, req.cells, req.name)

    @app.get("/api/datasets/{dataset_id}/groups")
    def list_groups(dataset_id: str) -> List[Dict[str, Any]]:
        return _dataset(dataset_id).groups()

    @app.get("/api/datasets/{dataset_id}/group_cells")
    def group_cells(dataset_id: str, group: str) -> Dict[str, Any]:
        return _call(_dataset(dataset_id).group_info, group)

    @app.get("/api/datasets/{dataset_id}/store")
    def store_structure(dataset_id: str) -> Dict[str, Any]:
        return _call(_dataset(dataset_id).store_tree)

    @app.get("/api/datasets/{dataset_id}/tracks")
    def tracks(dataset_id: str, names: str, chrom: str, start: Optional[int] = None,
               end: Optional[int] = None, cell_id: Optional[str] = None, agg: str = "mean",
               group: Optional[str] = None) -> Dict[str, Any]:
        return _call(_dataset(dataset_id).tracks, _names(names), chrom, start, end, cell_id, agg, group)

    @app.get("/api/datasets/{dataset_id}/intervals/{key}")
    def intervals(dataset_id: str, key: str, chrom: str, start: Optional[int] = None,
                  end: Optional[int] = None) -> Dict[str, Any]:
        return _call(_dataset(dataset_id).intervals, key, chrom, start, end)

    @app.get("/api/datasets/{dataset_id}/contacts/{key}")
    def contacts(dataset_id: str, key: str, chrom: str, start: Optional[int] = None,
                 end: Optional[int] = None, resolution: Optional[int] = None,
                 balance: bool = False, cell: Optional[str] = None, group: Optional[str] = None) -> Response:
        buf = _call(_dataset(dataset_id).contacts, key, chrom, start, end, resolution, balance, cell, group)
        return Response(buf, media_type="application/octet-stream")

    @app.get("/api/datasets/{dataset_id}/distance")
    def distance(dataset_id: str, chrom: str, start: Optional[int] = None, end: Optional[int] = None,
                 cell_id: Optional[str] = None, trace_id: Optional[str] = None,
                 stat: str = "median", threshold: Optional[float] = None, group: Optional[str] = None) -> Response:
        buf = _call(_dataset(dataset_id).distance, chrom, start, end, cell_id, trace_id, stat, threshold, group)
        return Response(buf, media_type="application/octet-stream")

    @app.get("/api/datasets/{dataset_id}/stats/rg")
    def stats_rg(dataset_id: str, chrom: Optional[str] = None, cell_id: Optional[str] = None,
                 group: Optional[str] = None) -> Dict[str, Any]:
        return _call(_dataset(dataset_id).stats_rg, chrom, cell_id, group)

    @app.get("/api/datasets/{dataset_id}/stats/scaling")
    def stats_scaling(dataset_id: str, chrom: Optional[str] = None, cell_id: Optional[str] = None,
                      group: Optional[str] = None) -> Dict[str, Any]:
        return _call(_dataset(dataset_id).stats_scaling, chrom, cell_id, group=group)

    @app.get("/api/datasets/{dataset_id}/embedding/{key}")
    def embedding(dataset_id: str, key: str, dims: str = "0,1") -> Dict[str, Any]:
        ds = _dataset(dataset_id)
        try:
            parsed = [int(d) for d in dims.split(",")]
            if len(parsed) != 2:
                raise ValueError("dims needs two comma-separated indices")
            return ds.embedding(key, parsed)
        except KeyError:
            raise HTTPException(404, f"unknown embedding: {key}") from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get("/api/datasets/{dataset_id}/spatial/{key}")
    def spatial(dataset_id: str, key: str, region: Optional[str] = None) -> Dict[str, Any]:
        try:
            return _dataset(dataset_id).spatial_points(key, region)
        except KeyError:
            raise HTTPException(404, f"unknown cell positions / region: {key} {region or ''}".strip()) from None

    @app.get("/api/datasets/{dataset_id}/images/{name}")
    def image(dataset_id: str, name: str) -> FileResponse:
        try:
            ds = _dataset(dataset_id)
            if ds._images().get(name) is None:
                raise KeyError(name)
            emb = ds.image_bytes(name)          # embedded in the store: no file needed
            if emb is not None:
                return Response(emb[0], media_type=emb[1])
            return FileResponse(ds.image_path(name))
        except KeyError:
            raise HTTPException(404, f"unknown image: {name}") from None

    @app.post("/api/datasets/{dataset_id}/points/{name}")
    def points(dataset_id: str, name: str, req: Optional[PointsRequest] = None) -> Dict[str, Any]:
        req = req or PointsRequest()
        try:
            return _dataset(dataset_id).points(name, cell_ids=req.cell_ids, labels=req.labels)
        except KeyError:
            raise HTTPException(404, f"unknown point set: {name}") from None

    @app.post("/api/datasets/{dataset_id}/geometry")
    def geometry(dataset_id: str, req: GeometryRequest) -> Response:
        ds = _dataset(dataset_id)
        try:
            flt = GeometryFilter(
                chroms=req.chroms,
                region=None if req.region is None else req.region.model_dump(),
                trace_ids=req.trace_ids,
                cell_ids=req.cell_ids,
                max_points=req.max_points,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return Response(ds.geometry(flt), media_type="application/octet-stream")

    from .control import ActionBroker, add_routes
    app.state.broker = ActionBroker()
    add_routes(app, app.state.broker)

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
