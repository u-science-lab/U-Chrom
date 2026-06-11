"""Structural analysis API endpoints: TAD, Loop, A/B Compartment.

All endpoints read from the current session's ChromData and run
the corresponding uchrom.strc caller on demand.

Endpoints:
    GET /api/tads/{chrom}?cell_type=
    GET /api/loops/{chrom}?cell_type=
    GET /api/compartments/{chrom}?cell_type=
"""
from __future__ import annotations

import json
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


def _respond(key: str, records: list, fmt: Optional[str]):
    """Shape the response by `format`.

    - default / 'wrapped': {<key>: [...]}  (back-compat with existing tests/UI)
    - 'gosling':           [...]           (bare array — Gosling json loader wants this)
    """
    if fmt == "gosling":
        return JSONResponse(records, headers={"Cache-Control": _CACHE})
    return JSONResponse({key: records}, headers={"Cache-Control": _CACHE})


# ---------------------------------------------------------------------------
# GET /api/tads/{chrom}
# ---------------------------------------------------------------------------

@strc_router.get("/api/tads/{chrom}")
def get_tads(chrom: str, cell_type: Optional[str] = None, format: Optional[str] = None):
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
        return _respond("tads", [], format)

    # Filter to requested chrom only
    if "chrom" in tads.columns:
        tads = tads[tads["chrom"].astype(str) == chrom]

    return _respond("tads", _df_to_records(tads), format)


# ---------------------------------------------------------------------------
# GET /api/loops/{chrom}
# ---------------------------------------------------------------------------

@strc_router.get("/api/loops/{chrom}")
def get_loops(chrom: str, cell_type: Optional[str] = None, format: Optional[str] = None):
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
        return _respond("loops", [], format)

    return _respond("loops", _df_to_records(loops), format)


# ---------------------------------------------------------------------------
# GET /api/compartments/{chrom}
# ---------------------------------------------------------------------------

@strc_router.get("/api/compartments/{chrom}")
def get_compartments(chrom: str, cell_type: Optional[str] = None, format: Optional[str] = None):
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
        return _respond("compartments", [], format)

    if "chrom" in comp.columns:
        comp = comp[comp["chrom"].astype(str) == chrom]

    return _respond("compartments", _df_to_records(comp), format)


# ---------------------------------------------------------------------------
# Analysis registry
# ---------------------------------------------------------------------------
# Single source of truth mapping an analysis name to its getter + the metadata
# an agent needs to render the result with render_gosling. To add a new
# structural analysis (e.g. insulation, stripes): implement the caller in
# uchrom.strc, add a get_* endpoint above, and add ONE row here — the
# run_analysis tool loop and the analysis→render handoff pick it up for free.
#
# Fields:
#   getter_name:       name of the endpoint function in this module, resolved at
#                      call time (so it stays patchable in tests / hot-reload).
#   result_key:        key under which records live in the default (wrapped) response
#   chromosome_field:  the chrom column name in the records (for Gosling chromosomeField)
#   genomic_fields:    position columns (for Gosling genomicFields)
#   suggested_mark:    a sensible default Gosling mark for this result type
#   chromosome_field_x1 (optional): for link marks, the chrom column of the
#                      second anchor (the x1/x1e channel). The loop caller
#                      (uchrom.strc.loop.axiswise_f) is CIS-ONLY: it always sets
#                      chrom2 == chrom1 == the queried chromosome, so chrom2 here
#                      equals chromosome_field in practice. It is surfaced
#                      explicitly so a future trans-loop caller (chrom1 != chrom2)
#                      maps the x1 anchor to chrom2 correctly without changing the
#                      contract. Do NOT fabricate trans loops — see note below.

ANALYSIS_REGISTRY = {
    "tad": {
        "getter_name": "get_tads",
        "endpoint": "/api/tads",
        "result_key": "tads",
        "chromosome_field": "chrom",
        "genomic_fields": ["start", "end"],
        "suggested_mark": "rule",
    },
    "loop": {
        "getter_name": "get_loops",
        "endpoint": "/api/loops",
        "result_key": "loops",
        # Anchor 1 → x/xe channel; anchor 2 → x1/x1e channel of the link mark.
        "chromosome_field": "chrom1",
        "chromosome_field_x1": "chrom2",
        "genomic_fields": ["start1", "end1", "start2", "end2"],
        "suggested_mark": "link",
    },
    "compartment": {
        "getter_name": "get_compartments",
        "endpoint": "/api/compartments",
        "result_key": "compartments",
        "chromosome_field": "chrom",
        "genomic_fields": ["start", "end"],
        "suggested_mark": "bar",
    },
}


def _records_from_response(resp, result_key: str) -> list:
    """Extract the record list from a getter return value.

    Tolerates both a FastAPI JSONResponse (real call) and a plain dict
    (e.g. a mocked getter in tests)."""
    if isinstance(resp, dict):
        payload = resp
    else:
        body = getattr(resp, "body", None)
        payload = json.loads(body) if body is not None else {}
    if isinstance(payload, dict):
        return payload.get(result_key, [])
    if isinstance(payload, list):
        return payload
    return []


def run_registered_analysis(analysis_type: str, chrom: str) -> dict:
    """Run a registered analysis and return both records and a render handle.

    Returns:
        {
          "type": analysis_type,
          "chrom": chrom,
          "record_count": int,
          "records": [...],                # the raw records (wrapped-format list)
          "data_url": "/api/<x>/<chrom>?format=gosling",
          "chromosome_field": str,
          "genomic_fields": [str, ...],
          "suggested_mark": str,
        }

    Raises:
        ValueError: unknown analysis_type or missing chrom.
        HTTPException: propagated from the underlying getter (404/500/503).
    """
    if not chrom:
        raise ValueError("run_analysis requires a 'region' (e.g. 'chr21')")
    spec = ANALYSIS_REGISTRY.get(analysis_type)
    if spec is None:
        raise ValueError(
            f"Unknown analysis type: {analysis_type}. "
            f"Available: {', '.join(ANALYSIS_REGISTRY)}"
        )

    # Resolve the getter by name at call time so tests can patch the module
    # attribute (patch('webapp.backend.strc_api.get_tads')).
    getter = globals()[spec["getter_name"]]
    resp = getter(chrom)
    records = _records_from_response(resp, spec["result_key"])

    handle = {
        "type": analysis_type,
        "chrom": chrom,
        "record_count": len(records),
        "records": records,
        "data_url": f"{spec['endpoint']}/{chrom}?format=gosling",
        "chromosome_field": spec["chromosome_field"],
        "genomic_fields": spec["genomic_fields"],
        "suggested_mark": spec["suggested_mark"],
    }
    # Link marks (loops) need a second-anchor chromosome field for the x1
    # channel. Only present for analyses that declare it.
    if "chromosome_field_x1" in spec:
        handle["chromosome_field_x1"] = spec["chromosome_field_x1"]
    return handle
