"""Structural analysis API endpoints: TAD, Loop, A/B Compartment.

All endpoints read from the current session's ChromData and run
the corresponding uchrom.strc caller on demand.

Endpoints:
    GET /api/tads/{chrom}?cell_type=
    GET /api/loops/{chrom}?cell_type=
    GET /api/compartments/{chrom}?cell_type=
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

import webapp.backend.data_api as data_api
from uchrom.core import ChromData

strc_router = APIRouter()

_CACHE = "max-age=300"  # 5 min cache — computation is expensive


def _cd_or_404():
    if data_api.current_session is None or data_api.current_session.chromdata is None:
        raise HTTPException(status_code=404, detail={"error": "No data loaded"})
    return data_api.current_session.chromdata


def _filter_by_cell_type(cd: ChromData, cell_type: Optional[str]) -> ChromData:
    """Filter ChromData to cells matching the given cell_type.

    If cell_type is None or cd.cells is empty / lacks a cell_type column,
    returns cd unchanged.
    """
    if cell_type is None:
        return cd
    if cd.cells is None or cd.cells.empty or "cell_type" not in cd.cells.columns:
        return cd

    matched = cd.cells[cd.cells["cell_type"].astype(str) == cell_type]
    if matched.empty:
        raise HTTPException(
            status_code=404,
            detail={"error": f"No cells with cell_type '{cell_type}'"},
        )

    valid_cell_ids = set(matched.index.tolist())
    if "cell_id" not in cd.spots.columns:
        return cd

    mask = cd.spots["cell_id"].astype(str).isin({str(c) for c in valid_cell_ids})
    if mask.sum() == 0:
        raise HTTPException(
            status_code=404,
            detail={"error": f"No spots for cell_type '{cell_type}'"},
        )

    filtered_spots = cd.spots[mask].copy()
    filtered_coords = cd.coords[mask.values]
    return ChromData(coords=filtered_coords, spots=filtered_spots)


def _df_to_records(df: pd.DataFrame) -> list:
    """Convert DataFrame to JSON-serializable list of dicts."""
    records = df.copy()
    for col in records.select_dtypes(include=[np.integer]).columns:
        records[col] = records[col].astype(int)
    for col in records.select_dtypes(include=[np.floating, float]).columns:
        records[col] = records[col].apply(lambda v: float(v) if np.isfinite(v) else None)
    return records.to_dict(orient="records")


# ---------------------------------------------------------------------------
# GET /api/tads/{chrom}
# ---------------------------------------------------------------------------

@strc_router.get("/api/tads/{chrom}")
def get_tads(chrom: str, cell_type: Optional[str] = None):
    """Return TAD domains for the given chromosome."""
    cd = _cd_or_404()
    cd = _filter_by_cell_type(cd, cell_type)

    # Use get_chrom for correct index alignment
    try:
        chrom_cd = cd.get_chrom(chrom)
    except (KeyError, ValueError):
        raise HTTPException(status_code=404, detail={"error": f"Chromosome {chrom} not found"})

    if chrom_cd.coords.shape[0] == 0:
        raise HTTPException(status_code=404, detail={"error": f"Chromosome {chrom} not found"})

    try:
        from uchrom.strc.tad import call_tads_by_pval, TADCallerParams
        tads = call_tads_by_pval(chrom_cd, TADCallerParams())
    except ImportError:
        raise HTTPException(status_code=503, detail={"error": "TAD module unavailable (missing torch?)"})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "TAD calling failed", "detail": str(e)})

    if tads is None or len(tads) == 0:
        return JSONResponse({"tads": []}, headers={"Cache-Control": _CACHE})

    # Filter to requested chrom only
    if "chrom" in tads.columns:
        tads = tads[tads["chrom"].astype(str) == chrom]

    return JSONResponse({"tads": _df_to_records(tads)}, headers={"Cache-Control": _CACHE})


# ---------------------------------------------------------------------------
# GET /api/loops/{chrom}
# ---------------------------------------------------------------------------

@strc_router.get("/api/loops/{chrom}")
def get_loops(chrom: str, cell_type: Optional[str] = None):
    """Return loop anchors for the given chromosome."""
    cd = _cd_or_404()
    cd = _filter_by_cell_type(cd, cell_type)

    try:
        chrom_cd = cd.get_chrom(chrom)
    except (KeyError, ValueError):
        raise HTTPException(status_code=404, detail={"error": f"Chromosome {chrom} not found"})

    if chrom_cd.coords.shape[0] == 0:
        raise HTTPException(status_code=404, detail={"error": f"Chromosome {chrom} not found"})

    try:
        from uchrom.strc.loop import call_loops_axiswise_f, LoopCallerParams
        loops = call_loops_axiswise_f(chrom_cd, LoopCallerParams())
    except ImportError:
        raise HTTPException(status_code=503, detail={"error": "Loop module unavailable (missing torch?)"})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "Loop calling failed", "detail": str(e)})

    if loops is None or len(loops) == 0:
        return JSONResponse({"loops": []}, headers={"Cache-Control": _CACHE})

    return JSONResponse({"loops": _df_to_records(loops)}, headers={"Cache-Control": _CACHE})


# ---------------------------------------------------------------------------
# GET /api/compartments/{chrom}
# ---------------------------------------------------------------------------

@strc_router.get("/api/compartments/{chrom}")
def get_compartments(chrom: str, cell_type: Optional[str] = None):
    """Return A/B compartment assignments for the given chromosome."""
    cd = _cd_or_404()
    cd = _filter_by_cell_type(cd, cell_type)

    try:
        chrom_cd = cd.get_chrom(chrom)
    except (KeyError, ValueError):
        raise HTTPException(status_code=404, detail={"error": f"Chromosome {chrom} not found"})

    if chrom_cd.coords.shape[0] == 0:
        raise HTTPException(status_code=404, detail={"error": f"Chromosome {chrom} not found"})

    try:
        from uchrom.strc.comp import call_compartments_axes_pc, CompartmentCallerParams
        comp = call_compartments_axes_pc(chrom_cd, CompartmentCallerParams())
    except ImportError:
        raise HTTPException(status_code=503, detail={"error": "Compartment module unavailable (missing torch?)"})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "Compartment calling failed", "detail": str(e)})

    if comp is None or len(comp) == 0:
        return JSONResponse({"compartments": []}, headers={"Cache-Control": _CACHE})

    if "chrom" in comp.columns:
        comp = comp[comp["chrom"].astype(str) == chrom]

    return JSONResponse({"compartments": _df_to_records(comp)}, headers={"Cache-Control": _CACHE})
