import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import numpy as np
import pandas as pd
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


def resolve_session(session_id: Optional[str] = None) -> Optional[Session]:
    """Resolve explicit session scope, falling back to the legacy global."""
    if session_id:
        try:
            from .main import sessions
            session = sessions.get(session_id)
        except Exception:
            session = None
        if session is not None:
            return session
    return current_session


def session_or_404(session_id: Optional[str] = None) -> Session:
    session = resolve_session(session_id)
    if session is None or session.chromdata is None:
        raise HTTPException(status_code=404, detail={"error": "No data loaded"})
    return session


def cd_or_404(session_id: Optional[str] = None):
    return session_or_404(session_id).chromdata


def _ranges_overlap(a_start, a_end, b_start, b_end) -> bool:
    try:
        return int(a_start) < int(b_end) and int(b_start) < int(a_end)
    except (TypeError, ValueError):
        return False


def _annotation_value_fields(record: dict, analysis_type: str) -> dict:
    skip = {"chrom", "chrom1", "chrom2", "start", "end", "start1", "end1", "start2", "end2"}
    out = {}
    for key, value in record.items():
        if key in skip:
            continue
        out[key] = value
        if key == "score":
            out[f"{analysis_type}_score"] = value
    return out


def _project_interval_annotations(bin_row: dict, analysis_type: str, records: list[dict]) -> dict:
    projected = {}
    chrom = str(bin_row.get("chrom", ""))
    start = bin_row.get("start")
    end = bin_row.get("end")
    for idx, record in enumerate(records):
        if str(record.get("chrom", record.get("chrom1", ""))) != chrom:
            continue
        if not _ranges_overlap(start, end, record.get("start"), record.get("end")):
            continue
        if analysis_type == "tad":
            projected["tad"] = True
            projected["tad_index"] = idx
        projected.update(_annotation_value_fields(record, analysis_type))
    return projected


def _project_loop_annotations(bin_row: dict, records: list[dict]) -> dict:
    chrom = str(bin_row.get("chrom", ""))
    start = bin_row.get("start")
    end = bin_row.get("end")
    count = 0
    for record in records:
        chrom1 = str(record.get("chrom", record.get("chrom1", "")))
        chrom2 = str(record.get("chrom2", chrom1))
        anchor1 = chrom1 == chrom and _ranges_overlap(start, end, record.get("start1"), record.get("end1"))
        anchor2 = chrom2 == chrom and _ranges_overlap(start, end, record.get("start2"), record.get("end2"))
        if anchor1 or anchor2:
            count += 1
    return {"loop_anchor_count": count} if count else {}


def _project_analysis_annotations(bin_row: dict, annotations: dict) -> dict:
    projected = {}
    for key, entry in (annotations or {}).items():
        analysis_type = str(entry.get("analysis_type") or key.split(":", 1)[0])
        records = entry.get("records") or []
        if analysis_type == "loop":
            projected.update(_project_loop_annotations(bin_row, records))
        else:
            projected.update(_project_interval_annotations(bin_row, analysis_type, records))
    return projected


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
# POST /api/coords/batch — accepts JSON body {cell_ids: [...]}
# GET  /api/coords/batch?ids=1,2,3 — legacy query string (URL length limit)
# ---------------------------------------------------------------------------

@data_router.post("/api/coords/batch")
async def post_coords_batch(request: Request):
    body = await request.json()
    cd = cd_or_404(body.get("session_id") or request.query_params.get("session_id"))
    id_list = body.get("cell_ids", [])
    rows = []
    for idx, cell_id in enumerate(id_list):
        cell = _coerce_cell_id(cd, str(cell_id))
        n = cell.coords.shape[0]
        col = np.full((n, 1), idx, dtype=np.float32)
        rows.append(np.hstack([col, cell.coords.astype(np.float32)]))
    if not rows:
        return _float32_response(np.empty((0, 4), dtype=np.float32))
    return _float32_response(np.vstack(rows))  # (n_cells * n_bins, 4)


@data_router.get("/api/coords/batch")
def get_coords_batch(ids: str, session_id: Optional[str] = None):
    cd = cd_or_404(session_id)
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
def get_coords(cell_id: str, session_id: Optional[str] = None):
    cd = cd_or_404(session_id)
    cell = _coerce_cell_id(cd, cell_id)
    return _float32_response(cell.coords)  # (n_bins, 3)


# ---------------------------------------------------------------------------
# GET /api/cells — lightweight cell list, independent of UMAP
# ---------------------------------------------------------------------------

@data_router.get("/api/cells")
def get_cells(session_id: Optional[str] = None):
    """Return the dataset's cell list, independent of any UMAP embedding.

    Source priority:
      1. ``cd.cells`` (DataFrame; cell ids from index or a ``cell_id`` column),
         carrying optional per-cell metadata such as ``cell_type``.
      2. Fallback: unique ``cell_id`` values from ``cd.spots`` when ``cd.cells``
         is empty or unavailable.
    """
    cd = cd_or_404(session_id)

    cells = []
    cell_types: list[str] = []

    cells_df = cd.cells
    if cells_df is not None and len(cells_df) > 0:
        df = cells_df.reset_index()
        if "cell_id" not in df.columns:
            df["cell_id"] = df.index
        has_type = "cell_type" in df.columns
        for i in range(len(df)):
            entry = {"cell_id": str(df.loc[i, "cell_id"])}
            if has_type:
                entry["cell_type"] = str(df.loc[i, "cell_type"])
            cells.append(entry)
        if has_type:
            cell_types = sorted(df["cell_type"].dropna().astype(str).unique().tolist())
    elif cd.spots is not None and "cell_id" in cd.spots.columns:
        # Fallback: derive cell list from spots, preserving first-seen order.
        seen = pd.unique(cd.spots["cell_id"].astype(str))
        cells = [{"cell_id": str(cid)} for cid in seen]

    return JSONResponse({"cells": cells, "cell_types": cell_types},
                        headers={"Cache-Control": _CACHE})


# ---------------------------------------------------------------------------
# GET /api/dataset_info — dataset-level metadata for default-spec construction
# ---------------------------------------------------------------------------

@data_router.get("/api/dataset_info")
def get_dataset_info(session_id: Optional[str] = None):
    """Return dataset-level metadata used to build default visualizations.

    The genomic panel uses this to construct its default contact-map spec
    against the actually-loaded chromosomes/assembly instead of a hardcoded
    chr21/hg38.

    Fields:
      - ``chroms``: unique chrom values from ``cd.spots["chrom"]``, in
        first-seen order.
      - ``genome_assembly``: ``cd.uns["genome_assembly"]`` if present, else null.
      - ``n_cells`` / ``n_spots``: simple size counts.
    """
    cd = cd_or_404(session_id)

    chroms: list[str] = []
    if cd.spots is not None and "chrom" in cd.spots.columns:
        chroms = [str(c) for c in pd.unique(cd.spots["chrom"].astype(str))]

    assembly = cd.uns.get("genome_assembly") if cd.uns is not None else None
    if assembly is not None:
        assembly = str(assembly)

    n_cells = int(len(cd.cells)) if cd.cells is not None else 0
    n_spots = int(len(cd.spots)) if cd.spots is not None else 0

    return JSONResponse(
        {"chroms": chroms, "genome_assembly": assembly,
         "n_cells": n_cells, "n_spots": n_spots},
        headers={"Cache-Control": _CACHE},
    )


# ---------------------------------------------------------------------------
# GET /api/umap
# ---------------------------------------------------------------------------

@data_router.get("/api/umap")
def get_umap(session_id: Optional[str] = None):
    cd = cd_or_404(session_id)
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
                      cell_type: Optional[str] = None,
                      session_id: Optional[str] = None):
    cd = cd_or_404(session_id)
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
              resolution: int = 1000,
              session_id: Optional[str] = None):
    cd = cd_or_404(session_id)
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
# GET /api/bins/{cell_id}  — genomic bin list for a cell
# ---------------------------------------------------------------------------

@data_router.get("/api/bins/{cell_id}")
def get_bins(cell_id: str, session_id: Optional[str] = None, annotations: bool = False):
    session = session_or_404(session_id)
    cd = session.chromdata
    cell = _coerce_cell_id(cd, cell_id)
    if len(cell.spots) == 0:
        raise HTTPException(status_code=404, detail={"error": f"Cell '{cell_id}' not found"})
    bins = cell.spots[["chrom", "start", "end"]].copy()
    # Convert categorical columns to plain strings for JSON serialisation
    for col in ("chrom",):
        if hasattr(bins[col], "cat"):
            bins[col] = bins[col].astype(str)
    records = bins.to_dict(orient="records")
    if annotations:
        session_annotations = getattr(session, "analysis_annotations", {}) or {}
        for row in records:
            projected = _project_analysis_annotations(row, session_annotations)
            if projected:
                row["annotations"] = projected
    return JSONResponse({"bins": records}, headers={"Cache-Control": _CACHE})


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


# ---------------------------------------------------------------------------
# GET /api/export_script  — generate standalone Python analysis script
# ---------------------------------------------------------------------------

@data_router.get("/api/export_script")
def export_script(session_id: Optional[str] = None):
    """Return a standalone Python script that reproduces the current session."""
    from fastapi.responses import PlainTextResponse
    cd = cd_or_404(session_id)
    source_path = getattr(cd, "_source_path", None) or "path/to/data.h5cd"

    lines = [
        "#!/usr/bin/env python3",
        '"""Auto-generated U-Chrom analysis script."""',
        "import numpy as np",
        "import pandas as pd",
        "import uchrom",
        "from uchrom.core.cdata import ChromData",
        "",
        "# Load data",
        f'cd = ChromData.read("{source_path}")',
        "",
        "# Session info",
    ]

    if cd.cells is not None:
        n_cells = len(cd.cells)
        lines.append(f"# {n_cells} cells loaded")

    if cd.spots is not None:
        chroms = sorted(cd.spots["chrom"].astype(str).unique().tolist())
        lines.append(f"# Chromosomes: {chroms}")

    lines += [
        "",
        "# Example: get a specific cell",
        "# cell = cd.get_cell('c1')",
        "",
        "# Example: compute distance matrix for a trace",
        "# dist = cd.compute_distances(trace_id=0)",
        "",
        "print(f'Loaded {len(cd.cells) if cd.cells is not None else 0} cells')",
    ]

    script = "\n".join(lines) + "\n"
    return PlainTextResponse(script, media_type="text/plain")
