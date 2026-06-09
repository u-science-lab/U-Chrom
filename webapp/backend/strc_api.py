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
from uchrom.strc.tad import call_tads_by_pval, TADCallerParams
from uchrom.strc.loop import call_loops_axiswise_f, LoopCallerParams
from uchrom.strc.comp import call_compartments_axes_pc, CompartmentCallerParams

strc_router = APIRouter()

_CACHE = "max-age=300"  # 5 min cache — computation is expensive


def _cd_or_404():
    if data_api.current_session is None or data_api.current_session.chromdata is None:
        raise HTTPException(status_code=404, detail={"error": "No data loaded"})
    return data_api.current_session.chromdata


def _df_to_records(df: pd.DataFrame) -> list:
    """Convert DataFrame to JSON-serializable list of dicts."""
    records = []
    for _, row in df.iterrows():
        rec = {}
        for col in df.columns:
            v = row[col]
            if isinstance(v, (np.integer,)):
                v = int(v)
            elif isinstance(v, (np.floating, float)):
                try:
                    v = float(v) if np.isfinite(float(v)) else None
                except (TypeError, ValueError):
                    v = None
            elif not isinstance(v, (str, bool, type(None))):
                v = str(v)
            rec[col] = v
        records.append(rec)
    return records


# ---------------------------------------------------------------------------
# GET /api/tads/{chrom}
# ---------------------------------------------------------------------------

@strc_router.get("/api/tads/{chrom}")
def get_tads(chrom: str, cell_type: Optional[str] = None):
    """Return TAD domains for the given chromosome."""
    cd = _cd_or_404()

    # Filter to chrom
    chrom_mask = cd.spots["chrom"].astype(str) == chrom
    if chrom_mask.sum() == 0:
        raise HTTPException(status_code=404, detail={"error": f"Chromosome {chrom} not found"})

    chrom_spots = cd.spots[chrom_mask]
    chrom_coords = cd.coords[chrom_mask.values]

    from uchrom.core import ChromData
    chrom_cd = ChromData(
        coords=chrom_coords,
        spots=chrom_spots.copy(),
    )

    tads = call_tads_by_pval(chrom_cd, TADCallerParams())
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

    chrom_mask = cd.spots["chrom"].astype(str) == chrom
    if chrom_mask.sum() == 0:
        raise HTTPException(status_code=404, detail={"error": f"Chromosome {chrom} not found"})

    chrom_spots = cd.spots[chrom_mask]
    chrom_coords = cd.coords[chrom_mask.values]

    from uchrom.core import ChromData
    chrom_cd = ChromData(
        coords=chrom_coords,
        spots=chrom_spots.copy(),
    )

    loops = call_loops_axiswise_f(chrom_cd, LoopCallerParams())
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

    chrom_mask = cd.spots["chrom"].astype(str) == chrom
    if chrom_mask.sum() == 0:
        raise HTTPException(status_code=404, detail={"error": f"Chromosome {chrom} not found"})

    chrom_spots = cd.spots[chrom_mask]
    chrom_coords = cd.coords[chrom_mask.values]

    from uchrom.core import ChromData
    chrom_cd = ChromData(
        coords=chrom_coords,
        spots=chrom_spots.copy(),
    )

    comp = call_compartments_axes_pc(chrom_cd, CompartmentCallerParams())
    if comp is None or len(comp) == 0:
        return JSONResponse({"compartments": []}, headers={"Cache-Control": _CACHE})

    if "chrom" in comp.columns:
        comp = comp[comp["chrom"].astype(str) == chrom]

    return JSONResponse({"compartments": _df_to_records(comp)}, headers={"Cache-Control": _CACHE})
