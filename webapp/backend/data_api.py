import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import numpy as np
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from .session import Session

data_router = APIRouter()

# Single global session for Phase 1 (single-user app).
# Set by ws_handler when a WebSocket connects.
current_session: Optional[Session] = None

_CACHE = "max-age=60"


def _cd_or_404():
    if current_session is None or current_session.chromdata is None:
        raise HTTPException(status_code=404, detail={"error": "No data loaded"})
    return current_session.chromdata


def _coerce_cell_id(cd, cell_id: str):
    """Try str first, then int, to match categorical cell_id dtype."""
    sub = cd.get_cell(cell_id)
    if len(sub.spots) == 0:
        try:
            sub = cd.get_cell(int(cell_id))
        except (ValueError, TypeError):
            pass
    return sub


def _float32_response(arr: np.ndarray) -> Response:
    data = arr.astype(np.float32, copy=False).tobytes()
    return Response(content=data, media_type="application/octet-stream",
                    headers={"Cache-Control": _CACHE})


# ---------------------------------------------------------------------------
# GET /api/coords/batch?ids=1,2,3  — must be registered before /{cell_id}
# ---------------------------------------------------------------------------

@data_router.get("/api/coords/batch")
def get_coords_batch(ids: str):
    cd = _cd_or_404()
    id_list = [i.strip() for i in ids.split(",") if i.strip()]
    rows = []
    for idx, cell_id in enumerate(id_list):
        cell = _coerce_cell_id(cd, cell_id)
        n = cell.coords.shape[0]
        col = np.full((n, 1), idx, dtype=np.float32)
        rows.append(np.hstack([col, cell.coords.astype(np.float32)]))
    if not rows:
        return _float32_response(np.empty((0, 4), dtype=np.float32))
    return _float32_response(np.vstack(rows))  # (n_cells * n_bins, 4)


# ---------------------------------------------------------------------------
# GET /api/coords/{cell_id}
# ---------------------------------------------------------------------------

@data_router.get("/api/coords/{cell_id}")
def get_coords(cell_id: str):
    cd = _cd_or_404()
    cell = _coerce_cell_id(cd, cell_id)
    return _float32_response(cell.coords)  # (n_bins, 3)


# ---------------------------------------------------------------------------
# GET /api/umap
# ---------------------------------------------------------------------------

@data_router.get("/api/umap")
def get_umap():
    cd = _cd_or_404()
    umap = cd.cellm.get("umap")
    if umap is None:
        raise HTTPException(status_code=404, detail={"error": "No UMAP computed"})
    cells_df = cd.cells.reset_index()
    if "cell_id" not in cells_df.columns:
        cells_df["cell_id"] = cells_df.index
    points = [
        {"cell_id": str(cells_df.loc[i, "cell_id"]),
         "x": float(umap[i, 0]), "y": float(umap[i, 1]),
         **({"cell_type": str(cells_df.loc[i, "cell_type"])} if "cell_type" in cells_df.columns else {})}
        for i in range(len(cells_df))
    ]
    cell_types = sorted(cells_df["cell_type"].dropna().unique().tolist()) if "cell_type" in cells_df.columns else []
    return JSONResponse({"points": points, "cell_types": cell_types},
                        headers={"Cache-Control": _CACHE})


# ---------------------------------------------------------------------------
# GET /api/contact/{chrom}?start=&end=&cell_type=
# ---------------------------------------------------------------------------

def _compute_contact_matrix(cd, chrom: str, start: Optional[int],
                            end: Optional[int], cell_type: Optional[str]) -> np.ndarray:
    """CPU-intensive: compute average pairwise distance matrix across cells."""
    sub = cd.get_chrom(chrom)

    # Filter by genomic range
    if start is not None or end is not None:
        mask = np.ones(len(sub.spots), dtype=bool)
        if start is not None:
            mask &= (sub.spots["end"] > start).values
        if end is not None:
            mask &= (sub.spots["start"] < end).values
        sub = sub[mask]

    cells_df = sub.cells
    if cell_type and len(cells_df) > 0 and "cell_type" in cells_df.columns:
        keep = cells_df[cells_df["cell_type"] == cell_type].index
        mask = sub.spots["cell_id"].isin(keep)
        sub = sub[mask.values]

    trace_ids = sub.spots["trace_id"].unique()
    matrices = []
    for tid in trace_ids:
        try:
            m = sub.compute_distances(trace_id=tid)
            matrices.append(m)
        except Exception:
            continue

    if not matrices:
        raise ValueError("No traces found")

    # Pad to common size and average
    max_n = max(m.shape[0] for m in matrices)
    padded = np.zeros((len(matrices), max_n, max_n), dtype=np.float32)
    counts = np.zeros((max_n, max_n), dtype=np.float32)
    for i, m in enumerate(matrices):
        n = m.shape[0]
        padded[i, :n, :n] = m
        counts[:n, :n] += 1

    counts = np.maximum(counts, 1)
    avg = padded.sum(axis=0) / counts
    return avg


@data_router.get("/api/contact/{chrom}")
async def get_contact(chrom: str,
                      start: Optional[int] = None, end: Optional[int] = None,
                      cell_type: Optional[str] = None):
    cd = _cd_or_404()
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=1) as executor:
        try:
            avg = await loop.run_in_executor(
                executor, _compute_contact_matrix, cd, chrom, start, end, cell_type
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail={"error": str(e)})
    return _float32_response(avg.flatten())


# ---------------------------------------------------------------------------
# GET /api/track/{name}?chrom=&start=&end=&resolution=
# ---------------------------------------------------------------------------

@data_router.get("/api/track/{name}")
def get_track(name: str, chrom: Optional[str] = None,
              start: Optional[int] = None, end: Optional[int] = None,
              resolution: int = 1000):
    cd = _cd_or_404()
    if cd.tracks is None or name not in cd.tracks.columns:
        raise HTTPException(status_code=404, detail={"error": f"Track '{name}' not found"})

    mask = np.ones(len(cd.spots), dtype=bool)
    if chrom:
        mask &= (cd.spots["chrom"] == chrom).values
    if start is not None:
        mask &= (cd.spots["end"] > start).values
    if end is not None:
        mask &= (cd.spots["start"] < end).values

    values = cd.tracks.loc[mask, name].to_numpy(dtype=np.float32)

    if len(values) > resolution:
        # Downsample by averaging bins
        indices = np.linspace(0, len(values), resolution + 1, dtype=int)
        values = np.array([values[indices[i]:indices[i+1]].mean()
                           for i in range(resolution)], dtype=np.float32)

    return _float32_response(values)


# ---------------------------------------------------------------------------
# GET /api/browse?path=/some/dir  — filesystem browser
# ---------------------------------------------------------------------------

import os as _os

@data_router.get("/api/browse")
def browse_directory(path: str = ""):
    """List directories and supported data files at the given path."""
    resolved = _os.path.abspath(path) if path else _os.path.expanduser("~")
    if not _os.path.isdir(resolved):
        raise HTTPException(status_code=400, detail={"error": "Not a directory"})

    try:
        names = sorted(_os.listdir(resolved))
    except PermissionError:
        raise HTTPException(status_code=403, detail={"error": "Permission denied"})

    entries = []
    for name in names:
        if name.startswith("."):
            continue
        full = _os.path.join(resolved, name)
        if _os.path.isdir(full):
            entries.append({"name": name, "type": "dir", "path": full})
        elif name.endswith((".h5cd", ".csv")):
            size = _os.path.getsize(full)
            entries.append({"name": name, "type": "file", "path": full, "size": size})

    parent = _os.path.dirname(resolved) if resolved != "/" else None
    return {"path": resolved, "parent": parent, "entries": entries}
