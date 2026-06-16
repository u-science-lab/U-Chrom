"""Dynamic analysis registry + runtime route.

Agent-authored analysis functions are compiled (see dynamic_analysis.py) and
stored in an in-memory registry. A single wildcard route
``/api/custom/{analysis_id}/{chrom}`` looks them up at call time — we do NOT
call ``app.add_api_route`` at runtime (race conditions + memory leaks on
OpenAPI schema rebuild, and FastAPI can't safely remove routes).

Responses reuse strc_api's ``_respond`` / ``_df_to_records`` contract so the
agent's analysis→render_gosling handoff works unchanged for custom endpoints.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

import webapp.backend.data_api as data_api
from .dynamic_analysis import (
    CompiledAnalysis,
    compile_analysis,
    run_with_timeout,
)
from .strc_api import _df_to_records, _respond

dynamic_router = APIRouter()

# In-memory registry (single-user Phase 1; lost on restart).
_REGISTRY: dict[str, CompiledAnalysis] = {}

# Applicability limits (plan §7).
MAX_SPOTS = 100_000
TIMEOUT_S = 10.0


def _cd_or_404():
    if data_api.current_session is None or data_api.current_session.chromdata is None:
        raise HTTPException(status_code=404, detail={"error": "No data loaded"})
    return data_api.current_session.chromdata


def render_handle(c: CompiledAnalysis, chrom: str = "{chrom}") -> dict:
    """Return the same render-handle shape as run_analysis / run_registered_analysis."""
    return {
        "analysis_id": c.name,
        "data_url": f"/api/custom/{c.name}/{chrom}?format=gosling",
        "chromosome_field": c.chromosome_field,
        "genomic_fields": list(c.genomic_fields),
        "suggested_mark": c.suggested_mark,
    }


def register_analysis(name: str, source: str, **meta) -> dict:
    """Validate + compile + store an analysis, return its render handle.

    Raises:
        AnalysisValidationError: source rejected by the sandbox.
    """
    compiled = compile_analysis(name, source, **meta)
    _REGISTRY[compiled.name] = compiled
    return render_handle(compiled)


def clear_registry() -> None:
    """Test helper: drop all registered analyses."""
    _REGISTRY.clear()


# ---------------------------------------------------------------------------
# GET /api/custom — list registered analyses
# ---------------------------------------------------------------------------

@dynamic_router.get("/api/custom")
def list_custom(session_id: Optional[str] = None):
    return {
        "analyses": [
            render_handle(c) for c in _REGISTRY.values()
        ]
    }


# ---------------------------------------------------------------------------
# GET /api/custom/{analysis_id}/{chrom}
# ---------------------------------------------------------------------------

@dynamic_router.get("/api/custom/{analysis_id}/{chrom}")
def run_custom(analysis_id: str, chrom: str, format: Optional[str] = None,
               session_id: Optional[str] = None):
    """Look up a registered analysis, run it on `chrom`, return Gosling-ready records."""
    compiled = _REGISTRY.get(analysis_id)
    if compiled is None:
        raise HTTPException(
            status_code=404,
            detail={"error": f"No analysis '{analysis_id}' registered"},
        )

    cd = data_api.cd_or_404(session_id)

    try:
        sub = cd.get_chrom(chrom)
    except (KeyError, ValueError):
        raise HTTPException(status_code=404, detail={"error": f"Chromosome {chrom} not found"})

    if sub is None or sub.coords.shape[0] == 0:
        raise HTTPException(status_code=404, detail={"error": f"Chromosome {chrom} not found"})

    if sub.coords.shape[0] > MAX_SPOTS:
        raise HTTPException(
            status_code=413,
            detail={"error": f"Region too large ({sub.coords.shape[0]} spots > {MAX_SPOTS})"},
        )

    # Pass the chrom-subset copy so the function can't mutate the global cd.
    try:
        df = run_with_timeout(compiled, sub, chrom, params={}, timeout_s=TIMEOUT_S)
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail={"error": str(e)})
    except TypeError as e:
        raise HTTPException(status_code=500, detail={"error": str(e)})
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "Custom analysis failed", "detail": str(e)},
        )

    return _respond(compiled.result_key, _df_to_records(df), format)
