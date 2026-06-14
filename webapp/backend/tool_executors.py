"""Tool executors for the A2UI agent loop.

Each tool the agent can call has an executor registered in ``TOOL_EXECUTORS``.
An executor is an async callable ``(websocket, tool_input) -> str`` that:

  1. performs the tool's side effect (e.g. emits an ``agent_artifact`` to the
     frontend, runs an analysis), and
  2. returns the **string content** for the Anthropic ``tool_result`` block.

This replaces the previous 300-line ``if/elif`` ladder in ``run_agent_loop``.
Adding a tool now means: define the schema in ``agent_tools.TOOLS``, register
an executor here, and (if it renders) handle its ``artifact_type`` on the
frontend. ``run_agent_loop`` itself stays tool-agnostic.
"""
from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable

from .url_safety import is_safe_url, sanitize_artifact_urls

logger = logging.getLogger(__name__)

# An executor: takes the live websocket + the tool_use.input dict, returns the
# tool_result content. Normally a JSON-encoded string. A vision-returning tool
# (capture_view_snapshot) instead returns a dict ``{"_content_blocks": [...]}``
# carrying an Anthropic content-block list (text + image) — run_agent_loop
# passes that through verbatim so the model can SEE the image.
Executor = Callable[[object, dict], Awaitable["str | dict"]]

# Registry, populated by @register below.
TOOL_EXECUTORS: dict[str, Executor] = {}


def register(name: str) -> Callable[[Executor], Executor]:
    def deco(fn: Executor) -> Executor:
        TOOL_EXECUTORS[name] = fn
        return fn
    return deco


def _normalize_ops(patch) -> list[dict]:
    """Coerce a patch input into a list of RFC 6902 ops.

    Accepts either a single ``{op, path, value}`` object (legacy patch_gosling
    shape) or an already-standard JSON-Patch array. Always returns a list so
    the rest of the pipeline is uniform.
    """
    if isinstance(patch, list):
        return [op for op in patch if isinstance(op, dict)]
    if isinstance(patch, dict):
        return [patch]
    return []


def apply_json_patch(doc, ops: list[dict]):
    """Apply an RFC 6902 JSON-Patch op list to ``doc`` (deep-copied).

    Returns ``(new_doc, error)``. ``error`` is a string if the patch is
    malformed or its path doesn't resolve, else None and ``new_doc`` is the
    patched document. Uses the ``jsonpatch`` library so the backend mirrors the
    frontend's ``fast-json-patch`` semantics exactly (same RFC 6902 standard).
    """
    import jsonpatch
    try:
        patcher = jsonpatch.JsonPatch(ops)
        new_doc = patcher.apply(doc)  # not in-place: returns a patched copy
        return new_doc, None
    except jsonpatch.JsonPatchException as e:
        return doc, f"JSON-Patch failed: {e}"
    except Exception as e:  # JsonPointerException etc.
        return doc, f"JSON-Patch failed: {e}"


def _apply_json_patch_to_view(view, ops: list[dict]) -> str | None:
    """Apply a standard JSON-Patch op list to a Gosling view's ``spec``.

    Paths are rooted at the Gosling spec (e.g. ``/tracks/0/mark``), matching
    the agent's mental model and what the frontend renders. Bumps the view's
    revision on success so a reconnect/patch reflects the new state. Returns an
    error string on failure (leaving the spec untouched), else None.
    """
    spec = view.state.get("spec")
    if not isinstance(spec, dict):
        return "view has no Gosling spec to patch."
    new_spec, error = apply_json_patch(spec, ops)
    if error is not None:
        return error
    view.state["spec"] = new_spec
    # Bump revision so a reconnect snapshot reflects the patched spec.
    view.revision += 1
    return None


# ---------------------------------------------------------------------------
# Gosling rendering
# ---------------------------------------------------------------------------

@register("render_gosling")
async def _render_gosling(ws, ti: dict) -> str:
    spec = ti.get("spec", {})
    title = ti.get("title", "Genomic Visualization")
    view_id = ti.get("_tool_use_id")
    # Sanitize agent-controlled URLs (Gosling data.url etc.) BEFORE the spec
    # reaches the frontend or the backend-authoritative snapshot. Relative API
    # paths pass; pseudo-protocols and private/loopback hosts are dropped.
    spec, rejected_urls = sanitize_artifact_urls(spec)
    if rejected_urls:
        logger.warning(
            "render_gosling: rejected %d unsafe URL(s) in spec %s: %s",
            len(rejected_urls), view_id, rejected_urls,
        )
    # Record backend-authoritative view state so the agent can later read it
    # (get_view_state) and the frontend can rebuild it after a reconnect.
    session = ti.get("_session")
    view = None
    if session is not None and view_id:
        view = session.get_or_create_view(view_id, "gosling", title=title)
        view.replace({"spec": spec, "title": title})
    await ws.send_json({
        "type": "agent_artifact",
        "artifact_type": "gosling_spec",
        "artifact_id": view_id,
        "title": title,
        "spec": spec,
        # Initial revision so the client can base subsequent patch reconciliation
        # on it (matches the backend ViewSession.revision after replace()).
        "revision": view.revision if view is not None else None,
    })
    result = {
        "success": True,
        "message": f"Gosling spec rendered successfully. Title: {title}",
        "spec_tracks": len(spec.get("tracks", [])),
        "view_id": view_id,
    }
    if rejected_urls:
        result["rejected_urls"] = rejected_urls
        result["warning"] = (
            "The following URL(s) were removed by the URL safety policy "
            "(only relative paths and public http(s) are allowed; "
            f"javascript:/data:/file: and private/loopback hosts are blocked): {rejected_urls}"
        )
    return json.dumps(result)


@register("patch_gosling")
async def _patch_gosling(ws, ti: dict) -> str:
    target_id = ti.get("target_id", "")
    raw_patch = ti.get("patch", {})
    ops = _normalize_ops(raw_patch)
    # Validate BEFORE emitting — an invalid patch must not reach the frontend.
    if not target_id or not ops:
        return json.dumps({
            "success": False,
            "error": (
                "patch_gosling requires 'target_id' and a 'patch' that is either "
                "a JSON-Patch op {op, path, value} or an array of such ops."
            ),
        })
    for op in ops:
        if not op.get("path") or not op.get("op"):
            return json.dumps({
                "success": False,
                "error": "each JSON-Patch op needs an 'op' and a 'path'.",
            })
    # The op 'value' is agent-controlled and may carry URL fields (e.g.
    # replacing a track's `data` object). Sanitize each op the same way as a
    # full spec; reject the whole patch if a path/value targets an unsafe URL so
    # we never write or ship it.
    cleaned_ops: list[dict] = []
    for op in ops:
        leaf = [p for p in op.get("path", "").split("/") if p != ""]
        leaf_key = leaf[-1] if leaf else ""
        raw_value = op.get("value")
        if leaf_key.lower() in {"url", "href", "src", "uri"} and isinstance(raw_value, str):
            if not is_safe_url(raw_value):
                logger.warning(
                    "patch_gosling: rejected unsafe URL value at %s on %s: %s",
                    op.get("path"), target_id, raw_value,
                )
                return json.dumps({
                    "success": False,
                    "error": (
                        f"URL '{raw_value}' was rejected by the URL safety policy. "
                        "Only relative paths and public http(s) are allowed; "
                        "javascript:/data:/file: and private/loopback hosts are blocked."
                    ),
                })
            cleaned_ops.append(op)
        elif isinstance(raw_value, (dict, list)):
            cleaned_value, rejected_urls = sanitize_artifact_urls(raw_value)
            if rejected_urls:
                logger.warning(
                    "patch_gosling: rejected %d unsafe URL(s) in patch value on %s: %s",
                    len(rejected_urls), target_id, rejected_urls,
                )
                cleaned_ops.append({**op, "value": cleaned_value})
            else:
                cleaned_ops.append(op)
        else:
            cleaned_ops.append(op)
    ops = cleaned_ops
    # Keep the backend-authoritative spec in sync with the patch the frontend
    # will apply, so a reconnect snapshot reflects the patched state. Capture
    # the pre-patch revision as base_revision: the frontend applies the ops only
    # if its local revision matches, else it re-pulls a full snapshot (RFC-6902
    # STATE_DELTA + reconcile, AG-UI style).
    session = ti.get("_session")
    base_revision = None
    view = None
    if session is not None and target_id in getattr(session, "views", {}):
        view = session.views[target_id]
        base_revision = view.revision
        error = _apply_json_patch_to_view(view, ops)
        if error is not None:
            return json.dumps({
                "success": False,
                "error": f"patch_gosling: {error}",
                "hint": "Check the path resolves against the current spec (call get_view_state).",
            })
    await ws.send_json({
        "type": "agent_artifact",
        "artifact_type": "gosling_patch",
        "target_id": target_id,
        # Standard RFC 6902 op array. base_revision lets the client detect a
        # gap and reconcile via view.request_snapshot. new_revision is the
        # backend revision after applying (frontend adopts it on success).
        "ops": ops,
        "base_revision": base_revision,
        "new_revision": view.revision if view is not None else None,
    })
    summary = "; ".join(f"{o.get('op')} {o.get('path')}" for o in ops)
    return json.dumps({
        "success": True,
        "message": f"Applied {len(ops)} JSON-Patch op(s) to spec {target_id}: {summary}.",
        "base_revision": base_revision,
        "new_revision": view.revision if view is not None else None,
    })


# ---------------------------------------------------------------------------
# Notebook
# ---------------------------------------------------------------------------

@register("add_notebook_cell")
async def _add_notebook_cell(ws, ti: dict) -> str:
    code = ti.get("code", "")
    try:
        from .notebook_api import execute_code
        result = execute_code(code)
    except Exception as e:
        result = {"status": "error", "output": "", "error": f"Execution failed: {e}", "images": []}

    images = result.get("images", []) or []
    await ws.send_json({
        "type": "agent_artifact",
        "artifact_type": "notebook_cell",
        "content": {
            "code": code,
            "output": result.get("output", ""),
            "error": result.get("error"),
            "status": result.get("status", "ok"),
            "images": images,
        },
    })

    output_preview = result.get("output", "")[:100]
    error_preview = result.get("error", "")[:100] if result.get("error") else None
    if error_preview:
        return f"Cell added with error. Error: {error_preview}"
    img_note = f" Produced {len(images)} figure(s)." if images else ""
    return f"Cell added. Output: {output_preview}{img_note}"


# ---------------------------------------------------------------------------
# Built-in structure analyses (tad / loop / compartment)
# ---------------------------------------------------------------------------

@register("run_analysis")
async def _run_analysis(ws, ti: dict) -> str:
    analysis_type = ti.get("type", "")
    region = ti.get("region", "") or ""
    chrom = region.split(":")[0].strip() if region else ""

    try:
        from .strc_api import run_registered_analysis
        handle = run_registered_analysis(analysis_type, chrom)
    except Exception as e:
        return f"Analysis failed: {e}"

    await ws.send_json({
        "type": "agent_artifact",
        "artifact_type": "analysis_result",
        "analysis_type": analysis_type,
        "chrom": chrom,
        "result": {handle["type"] + "s": handle["records"]},
    })

    payload = {
        "success": True,
        "type": handle["type"],
        "chrom": handle["chrom"],
        "record_count": handle["record_count"],
        "data_url": handle["data_url"],
        "chromosome_field": handle["chromosome_field"],
        "genomic_fields": handle["genomic_fields"],
        "suggested_mark": handle["suggested_mark"],
        "next_step": (
            "To visualize, call render_gosling with a track whose "
            'data = {"type":"json","url":data_url,'
            '"chromosomeField":chromosome_field,'
            '"genomicFields":genomic_fields} and mark = suggested_mark.'
        ),
    }
    # Loops are cis-only links: anchor 1 -> x/xe, anchor 2 -> x1/x1e.
    if "chromosome_field_x1" in handle:
        payload["chromosome_field_x1"] = handle["chromosome_field_x1"]
        payload["next_step"] = (
            "To visualize loops, call render_gosling with a link-mark track: "
            'data = {"type":"json","url":data_url,"chromosomeField":chromosome_field,'
            '"genomicFields":genomic_fields}, mark = "link", and map anchor 1 to '
            'x={field:"start1"}, xe={field:"end1"} and anchor 2 to '
            'x1={field:"start2"}, x1e={field:"end2"}. Loops are CIS-ONLY '
            "(chrom2 == chrom1); do not attempt trans-chromosome links — the "
            "caller does not emit them."
        )
    return json.dumps(payload)


# ---------------------------------------------------------------------------
# Dynamic agent-authored analysis
# ---------------------------------------------------------------------------

@register("write_analysis_function")
async def _write_analysis_function(ws, ti: dict) -> str:
    name = (ti.get("name") or "").strip()
    code = ti.get("code", "")
    meta: dict = {}
    if ti.get("chromosome_field"):
        meta["chromosome_field"] = ti["chromosome_field"]
    if ti.get("genomic_fields"):
        meta["genomic_fields"] = tuple(ti["genomic_fields"])
    if ti.get("suggested_mark"):
        meta["suggested_mark"] = ti["suggested_mark"]
    if name:
        meta["result_key"] = name

    from .dynamic_api import register_analysis
    from .dynamic_analysis import AnalysisValidationError
    try:
        handle = register_analysis(name, code, **meta)
    except AnalysisValidationError as ve:
        return json.dumps({
            "success": False,
            "error": f"Rejected by sandbox: {ve}",
            "hint": (
                "Remove imports/IO/dunder access; define "
                "analyze(cd, chrom, **params) returning a DataFrame."
            ),
        })
    except Exception as e:
        return f"Deploy failed: {e}"

    await ws.send_json({
        "type": "agent_artifact",
        "artifact_type": "custom_analysis_deployed",
        "analysis_id": name,
        "data_url": handle["data_url"],
        "chromosome_field": handle["chromosome_field"],
        "genomic_fields": handle["genomic_fields"],
        "suggested_mark": handle["suggested_mark"],
    })
    return json.dumps({
        "success": True,
        "analysis_id": name,
        "data_url": handle["data_url"],
        "chromosome_field": handle["chromosome_field"],
        "genomic_fields": handle["genomic_fields"],
        "suggested_mark": handle["suggested_mark"],
        "next_step": (
            "Endpoint deployed. Replace {chrom} in data_url with the real "
            'chromosome, then call render_gosling with data={"type":"json",'
            '"url":<data_url>,"chromosomeField":chromosome_field,'
            '"genomicFields":genomic_fields} and mark=suggested_mark.'
        ),
    })


# ---------------------------------------------------------------------------
# compute_embedding — compute cell-level UMAP and write back to cd.cellm["umap"]
# ---------------------------------------------------------------------------


def _ordered_cell_ids(cd) -> list[str]:
    """Canonical cell-id order, matching what /api/umap iterates.

    /api/umap walks ``cd.cells.reset_index()`` row by row and pairs row ``i``
    with ``umap[i]``. So the umap matrix we write MUST be in this exact order.
    When ``cd.cells`` is empty (e.g. FOF-CT imports leave it unpopulated) we
    fall back to first-seen ``cell_id`` from spots — and the executor then
    builds a matching ``cd.cells`` so /api/umap has rows to iterate.
    """
    import pandas as pd

    cells_df = cd.cells
    if cells_df is not None and len(cells_df) > 0:
        df = cells_df.reset_index()
        if "cell_id" not in df.columns:
            df["cell_id"] = df.index
        return [str(x) for x in df["cell_id"].tolist()]
    if cd.spots is not None and "cell_id" in cd.spots.columns:
        return [str(x) for x in pd.unique(cd.spots["cell_id"].astype(str))]
    return []


def _geometric_features(coords) -> list:
    """Method B fallback: fixed-length geometric scalars for one cell's coords.

    Order-invariant, length-invariant descriptors so cells with differing bin
    counts still map to the same feature space:
      radius of gyration, per-axis std (x/y/z), mean & std of pairwise
      distances, and the max pairwise extent.
    """
    import numpy as np

    if coords is None or len(coords) == 0:
        return [0.0] * 7
    c = np.asarray(coords, dtype=float)
    center = c.mean(axis=0)
    rg = float(np.sqrt(((c - center) ** 2).sum(axis=1).mean()))
    std = c.std(axis=0)
    # Pairwise distance stats (cap N to keep O(n^2) cheap for huge traces).
    if len(c) > 400:
        idx = np.linspace(0, len(c) - 1, 400, dtype=int)
        cc = c[idx]
    else:
        cc = c
    dm = np.sqrt(((cc[:, None, :] - cc[None, :, :]) ** 2).sum(-1))
    iu = np.triu_indices(len(cc), k=1)
    pd_vals = dm[iu] if len(iu[0]) else np.array([0.0])
    return [rg, float(std[0]), float(std[1]), float(std[2]),
            float(pd_vals.mean()), float(pd_vals.std()), float(pd_vals.max())]


def compute_cell_embedding(cd, chrom: str | None = None,
                           method: str = "auto", n_components: int = 2,
                           random_state: int = 42) -> dict:
    """Compute a 2D cell-level embedding and write it to ``cd.cellm['umap']``.

    Returns a summary dict (no websocket / no I/O), so it is unit-testable and
    reusable by the executor.

    Feature design
    --------------
    Method A (default, preferred): for a reference chromosome, take each cell's
    per-bin mean coordinate, intersect bins across all cells to a common set,
    build the pairwise distance matrix, and flatten its upper triangle. This
    captures the chromosome's 3D folding and is comparable across cells because
    every cell uses the same bins. Requires >= 3 common bins.

    Method B (fallback): order/length-invariant geometric scalars per cell
    (radius of gyration, per-axis std, pairwise-distance mean/std/max). Used
    when bins don't align across cells (common in sparse FISH like FOF-CT) or
    when the caller forces ``method='geometric'``.

    n_neighbors is clamped to ``min(15, n_cells - 1)`` (UMAP needs < n_cells).
    For small n the spectral initializer's eigendecomposition fails, so we use
    ``init='random'`` when n_cells < 10. Needs n_cells >= 2.
    """
    import numpy as np

    ids = _ordered_cell_ids(cd)
    n_cells = len(ids)
    if n_cells < 2:
        raise ValueError(
            f"Need at least 2 cells to compute an embedding (found {n_cells})."
        )

    # Pick reference chromosome for method A.
    ref_chrom = chrom
    if ref_chrom is None and cd.spots is not None and "chrom" in cd.spots.columns:
        chroms = [str(c) for c in cd.spots["chrom"].astype(str).unique()]
        ref_chrom = chroms[0] if chroms else None

    used_method = None
    X = None

    if method in ("auto", "distance") and ref_chrom is not None:
        # Per cell: bin-start -> mean coordinate on the reference chromosome.
        percell: dict[str, dict] = {}
        for cid in ids:
            sub = cd.get_cell(cid)
            if len(sub.spots) == 0:
                try:
                    sub = cd.get_cell(int(cid))
                except (ValueError, TypeError):
                    pass
            sub = sub.get_chrom(ref_chrom)
            d: dict[int, np.ndarray] = {}
            if len(sub.spots) > 0:
                starts = sub.spots["start"].to_numpy()
                co = sub.coords
                for s in np.unique(starts):
                    d[int(s)] = co[starts == s].mean(axis=0)
            percell[cid] = d
        bin_sets = [set(d.keys()) for d in percell.values() if d]
        common = sorted(set.intersection(*bin_sets)) if bin_sets else []
        if len(common) >= 3:
            iu = np.triu_indices(len(common), k=1)
            rows = []
            for cid in ids:
                d = percell[cid]
                if all(s in d for s in common):
                    co = np.stack([d[s] for s in common])
                    dm = np.sqrt(((co[:, None, :] - co[None, :, :]) ** 2).sum(-1))
                    rows.append(dm[iu])
                else:
                    # Cell missing some common bins → defer to geometric below.
                    rows = None
                    break
            if rows is not None:
                X = np.asarray(rows, dtype=float)
                used_method = "distance"

    if X is None:
        # Method B fallback (or method='geometric').
        rows = []
        for cid in ids:
            sub = cd.get_cell(cid)
            if len(sub.spots) == 0:
                try:
                    sub = cd.get_cell(int(cid))
                except (ValueError, TypeError):
                    pass
            if ref_chrom is not None and method == "geometric":
                sub = sub.get_chrom(ref_chrom)
            rows.append(_geometric_features(sub.coords))
        X = np.asarray(rows, dtype=float)
        used_method = "geometric"

    # Guard against NaN/inf in features before UMAP.
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    import umap

    n_neighbors = min(15, n_cells - 1)
    init = "random" if n_cells < 10 else "spectral"
    reducer = umap.UMAP(
        n_neighbors=n_neighbors,
        n_components=n_components,
        init=init,
        random_state=random_state,
    )
    emb = reducer.fit_transform(X)
    emb = np.asarray(emb, dtype=float)

    # Ensure cd.cells has rows in the SAME order as `ids`, so /api/umap pairs
    # umap[i] with the right cell. FOF-CT imports often leave cd.cells empty.
    import pandas as pd
    if cd.cells is None or len(cd.cells) == 0:
        cd.cells = pd.DataFrame(index=pd.Index(ids, name="cell_id"))

    cd.cellm["umap"] = emb
    return {
        "n_cells": n_cells,
        "method": used_method,
        "ref_chrom": ref_chrom if used_method == "distance" else None,
        "n_features": int(X.shape[1]),
        "n_neighbors": n_neighbors,
        "shape": list(emb.shape),
    }


@register("compute_embedding")
async def _compute_embedding(ws, ti: dict) -> str:
    session = ti.get("_session")
    import webapp.backend.data_api as _data_api
    cd = getattr(session, "chromdata", None) if session is not None else None
    if cd is None:
        cd = getattr(_data_api.current_session, "chromdata", None)
    if cd is None:
        return json.dumps({"success": False,
                           "error": "No data loaded; cannot compute embedding."})

    chrom = ti.get("chrom") or None
    method = (ti.get("method") or "auto").lower()
    if method not in ("auto", "distance", "geometric"):
        method = "auto"

    try:
        import asyncio
        loop = asyncio.get_running_loop()
        summary = await loop.run_in_executor(
            None, lambda: compute_cell_embedding(cd, chrom=chrom, method=method)
        )
    except ValueError as ve:
        return json.dumps({"success": False, "error": str(ve)})
    except Exception as e:  # pragma: no cover - surfaced to the agent
        logger.exception("compute_embedding failed")
        return json.dumps({"success": False, "error": f"Embedding failed: {e}"})

    # Tell the frontend to re-fetch /api/umap (bumpDataVersion on the client).
    await ws.send_json({
        "type": "agent_artifact",
        "artifact_type": "embedding_computed",
        "n_cells": summary["n_cells"],
        "method": summary["method"],
    })
    return json.dumps({
        "success": True,
        "message": (
            f"Computed UMAP embedding for {summary['n_cells']} cells "
            f"(method={summary['method']}"
            + (f", ref_chrom={summary['ref_chrom']}" if summary["ref_chrom"] else "")
            + f", {summary['n_features']} features, "
            f"n_neighbors={summary['n_neighbors']}). "
            "The Embedding tab will refresh to show it."
        ),
        **summary,
    })


# ---------------------------------------------------------------------------
# Embedding / 3D structure / cells — simple artifact forwarders
# ---------------------------------------------------------------------------

@register("select_cells")
async def _select_cells(ws, ti: dict) -> str:
    cell_ids = ti.get("cell_ids", []) or []
    criteria = ti.get("criteria", "")
    await ws.send_json({
        "type": "agent_artifact",
        "artifact_type": "select_cells",
        "cell_ids": cell_ids,
        "criteria": criteria,
    })
    return f"Selected {len(cell_ids)} cell(s)." + (f" Criteria: {criteria}" if criteria else "")


def _resolve_cd(ti: dict):
    """Best-effort fetch of the live ChromData for validation.

    Mirrors _compute_embedding: prefer the session passed into the executor,
    else fall back to data_api's module-level current_session. Returns None
    when nothing is loaded — callers must tolerate that and skip validation.
    """
    session = ti.get("_session")
    cd = getattr(session, "chromdata", None) if session is not None else None
    if cd is None:
        try:
            import webapp.backend.data_api as _data_api
            cd = getattr(_data_api.current_session, "chromdata", None)
        except Exception:
            cd = None
    return cd


@register("color_embedding")
async def _color_embedding(ws, ti: dict) -> str:
    """Color the Embedding (UMAP) scatter by a per-cell field.

    `color_by` should be a column of ``cd.cells`` (e.g. ``cell_type``). We
    validate against the live data so the agent gets a concrete error + the
    list of valid fields instead of silently "succeeding" on a field the
    frontend can't color by.
    """
    color_by = ti.get("color_by", "")
    if not color_by:
        return json.dumps({
            "success": False,
            "error": "color_embedding requires a 'color_by' field.",
        })

    cd = _resolve_cd(ti)
    if cd is not None and getattr(cd, "cells", None) is not None and len(cd.cells) > 0:
        # Reset index so the cell-id column is selectable alongside metadata.
        valid = list(cd.cells.reset_index().columns)
        if color_by not in valid:
            return json.dumps({
                "success": False,
                "error": (
                    f"color_embedding: '{color_by}' is not a cell field. "
                    f"Available fields: {valid}."
                ),
            })

    await ws.send_json({
        "type": "agent_artifact",
        "artifact_type": "color_embedding",
        "color_by": color_by,
    })
    return json.dumps({
        "success": True,
        "message": f"Embedding now colored by '{color_by}'.",
        "color_by": color_by,
    })


@register("show_structure")
async def _show_structure(ws, ti: dict) -> str:
    """Filter the 3D Structure view to a single cell (and optional chrom).

    `cell_id` is required. We validate it exists in the dataset so the agent
    isn't told it "showed" a cell that isn't there.
    """
    cell_id = str(ti.get("cell_id", "") or "")
    chrom = str(ti.get("chrom", "") or "")
    if not cell_id:
        return json.dumps({
            "success": False,
            "error": "show_structure requires a 'cell_id'.",
        })

    cd = _resolve_cd(ti)
    if cd is not None:
        sub = cd.get_cell(cell_id)
        if len(sub.spots) == 0:
            try:
                sub = cd.get_cell(int(cell_id))
            except (ValueError, TypeError):
                pass
        if len(sub.spots) == 0:
            return json.dumps({
                "success": False,
                "error": f"show_structure: no cell '{cell_id}' in the dataset.",
            })
        if chrom:
            chroms = {str(c) for c in sub.spots["chrom"].astype(str).unique()}
            if chrom not in chroms:
                return json.dumps({
                    "success": False,
                    "error": (
                        f"show_structure: cell '{cell_id}' has no chromosome "
                        f"'{chrom}'. Available: {sorted(chroms)}."
                    ),
                })

    await ws.send_json({
        "type": "agent_artifact",
        "artifact_type": "show_structure",
        "cell_id": cell_id,
        "chrom": chrom,
    })
    return json.dumps({
        "success": True,
        "message": (f"3D view now shows cell '{cell_id}'"
                    + (f", {chrom}" if chrom else "") + "."),
        "cell_id": cell_id,
        "chrom": chrom or None,
    })


@register("color_structure")
async def _color_structure(ws, ti: dict) -> str:
    """Color the 3D Structure traces by a field.

    Pragmatic support: ``chrom`` (always present) and any existing ``cd.spots``
    column (e.g. ``trace_id``, or a ``compartment``/marker column if a prior
    analysis added one). compartment/TAD coloring needs run_analysis to have
    populated such a column first; if the requested field is absent we tell the
    agent exactly what's available.
    """
    color_by = ti.get("color_by", "")
    if not color_by:
        return json.dumps({
            "success": False,
            "error": "color_structure requires a 'color_by' field.",
        })

    cd = _resolve_cd(ti)
    if cd is not None and getattr(cd, "spots", None) is not None:
        valid = list(cd.spots.columns)
        if color_by not in valid:
            return json.dumps({
                "success": False,
                "error": (
                    f"color_structure: '{color_by}' is not a spot field. "
                    f"Available: {valid}. (compartment/TAD coloring requires "
                    "running the matching analysis first so the column exists.)"
                ),
            })

    await ws.send_json({
        "type": "agent_artifact",
        "artifact_type": "color_structure",
        "color_by": color_by,
    })
    return json.dumps({
        "success": True,
        "message": f"3D structure now colored by '{color_by}'.",
        "color_by": color_by,
    })


@register("export_view")
async def _export_view(ws, ti: dict) -> str:
    fmt = (ti.get("format") or "png").lower()
    if fmt not in ("png", "pdf"):
        fmt = "png"
    await ws.send_json({
        "type": "agent_artifact",
        "artifact_type": "export_view",
        "format": fmt,
    })
    return (f"Triggered export of the current view as {fmt.upper()}. "
            "The download will start in the user's browser.")


# ---------------------------------------------------------------------------
# Tier 2: agent-composed component tree (generative UI, no code execution)
# ---------------------------------------------------------------------------

# Whitelisted components the agent may compose. The frontend has the matching
# registry; validating here too is defense-in-depth (reject before it ships).
ALLOWED_COMPONENTS = frozenset({
    "Panel", "Row", "Column", "Text", "Table",
    "Button", "Slider", "Select",
    "GoslingView", "EmbeddingView", "StructureView",
})
MAX_COMPONENT_NODES = 200


def _validate_component_tree(node, counter: list) -> str | None:
    """Return an error string if the tree is invalid, else None."""
    if not isinstance(node, dict):
        return "each node must be an object with a 'component' field"
    name = node.get("component")
    if name not in ALLOWED_COMPONENTS:
        return f"unknown component '{name}'; allowed: {sorted(ALLOWED_COMPONENTS)}"
    counter[0] += 1
    if counter[0] > MAX_COMPONENT_NODES:
        return f"component tree too large (> {MAX_COMPONENT_NODES} nodes)"
    children = node.get("children", [])
    if children:
        if not isinstance(children, list):
            return f"'children' of {name} must be a list"
        for child in children:
            err = _validate_component_tree(child, counter)
            if err:
                return err
    return None


@register("render_component")
async def _render_component(ws, ti: dict) -> str:
    tree = ti.get("tree")
    title = ti.get("title", "Custom View")
    view_id = ti.get("_tool_use_id")

    err = _validate_component_tree(tree, [0])
    if err:
        return json.dumps({
            "success": False,
            "error": f"Invalid component tree: {err}",
            "hint": f"Use only these components: {sorted(ALLOWED_COMPONENTS)}.",
        })

    # Defense-in-depth: the component whitelist gates which components render,
    # not what their props carry. Strip any unsafe URL fields from props before
    # the tree ships (current registry consumes no URLs, but a future component
    # might — don't let that be an injection vector).
    tree, rejected_urls = sanitize_artifact_urls(tree)
    if rejected_urls:
        logger.warning(
            "render_component: rejected %d unsafe URL(s) in tree %s: %s",
            len(rejected_urls), view_id, rejected_urls,
        )

    session = ti.get("_session")
    if session is not None and view_id:
        view = session.get_or_create_view(view_id, "component", title=title)
        view.replace({"tree": tree, "title": title})

    await ws.send_json({
        "type": "agent_artifact",
        "artifact_type": "component_tree",
        "artifact_id": view_id,
        "title": title,
        "tree": tree,
    })
    result = {
        "success": True,
        "message": f"Composed custom view '{title}'.",
        "view_id": view_id,
    }
    if rejected_urls:
        result["rejected_urls"] = rejected_urls
        result["warning"] = (
            "The following URL(s) were removed by the URL safety policy: "
            f"{rejected_urls}"
        )
    return json.dumps(result)

@register("get_view_state")
async def _get_view_state(ws, ti: dict) -> str:
    session = ti.get("_session")
    views = getattr(session, "views", {}) if session is not None else {}
    view_id = ti.get("view_id")
    if view_id:
        v = views.get(view_id)
        if v is None:
            return json.dumps({"success": False, "error": f"No view '{view_id}'."})
        return json.dumps({"success": True, "view": v.to_dict()})
    # No id → list all views (id, type, revision, last_interaction, #diagnostics).
    return json.dumps({
        "success": True,
        "views": [
            {
                "view_id": v.view_id,
                "view_type": v.view_type,
                "revision": v.revision,
                "last_interaction": v.state.get("last_interaction"),
                "n_diagnostics": len(v.diagnostics),
            }
            for v in views.values()
        ],
    })


@register("query_user_interaction")
async def _query_user_interaction(ws, ti: dict) -> str:
    session = ti.get("_session")
    view_id = ti.get("view_id")
    wait = bool(ti.get("wait", False))
    timeout = float(ti.get("timeout_seconds", 30) or 30)

    if not wait:
        # Return the last recorded interaction immediately, if any.
        views = getattr(session, "views", {}) if session is not None else {}
        if view_id:
            v = views.get(view_id)
            last = v.state.get("last_interaction") if v is not None else None
        else:
            # Most recent across all views.
            last = None
            best = -1.0
            for v in views.values():
                li = v.state.get("last_interaction")
                if li and li.get("timestamp", 0) > best:
                    best, last = li["timestamp"], li
        return json.dumps({"success": True, "interaction": last})

    # Blocking mode: wait for the next interaction. Mint an interaction_id and
    # announce it to the frontend (AG-UI style) so the UI can echo it back on the
    # matching ui_event — letting the backend resolve EXACTLY this waiter. The
    # announcement also lets the UI show an "agent is waiting for you" affordance
    # and tells the user which view to act on (e.g. pick a spot in the 3D tab).
    import uuid as _uuid
    interaction_id = _uuid.uuid4().hex
    await ws.send_json({
        "type": "await_interaction",
        "interaction_id": interaction_id,
        "view_id": view_id,
        "timeout_seconds": timeout,
    })

    from .ws_handler import wait_for_interaction
    event = await wait_for_interaction(session, view_id, timeout,
                                       interaction_id=interaction_id)
    # Tell the frontend the wait is over (resolved or timed out) so it can clear
    # the pending-interaction affordance and stop echoing the id.
    await ws.send_json({
        "type": "await_interaction_done",
        "interaction_id": interaction_id,
        "resolved": event is not None,
    })
    if event is None:
        return json.dumps({
            "success": True, "interaction": None,
            "message": f"No interaction within {timeout:.0f}s.",
        })
    return json.dumps({"success": True, "interaction": event})


# ---------------------------------------------------------------------------
# capture_view_snapshot — let the agent SEE a rendered view and self-correct
# ---------------------------------------------------------------------------

# Views the agent can ask to capture. These map 1:1 to the frontend tabs /
# panels that know how to render-to-PNG (Three.js 3D, Gosling, deck.gl UMAP).
_SNAPSHOT_VIEWS = ("genomic", "structure3d", "embedding")
# Capture can be slow (tab switch + force-render a WebGL frame + toDataURL);
# give the round-trip generous headroom before falling back to a text error.
_SNAPSHOT_TIMEOUT_DEFAULT = 30.0
_MAX_DATA_URL_BYTES = 8 * 1024 * 1024  # 8 MB guard on the returned image


def _parse_data_url(data_url: str) -> tuple[str, str] | None:
    """Split a ``data:<media_type>;base64,<data>`` URL into (media_type, data).

    Returns None if the string isn't a base64 data URL we can turn into an
    Anthropic image block.
    """
    if not isinstance(data_url, str) or not data_url.startswith("data:"):
        return None
    header, sep, b64 = data_url.partition(",")
    if not sep or ";base64" not in header:
        return None
    media_type = header[len("data:"):].split(";", 1)[0].strip() or "image/png"
    if not media_type.startswith("image/"):
        return None
    return media_type, b64


def build_snapshot_content_blocks(view_id: str, data_url: str) -> list[dict]:
    """Build the tool_result content-block list for a captured view image.

    A text block (so the agent has a textual anchor + the view id) followed by
    an Anthropic image block sourced from the base64 data URL. Returns the list
    that goes under ``_content_blocks``; raises ValueError if the data URL is
    not a usable base64 image.
    """
    parsed = _parse_data_url(data_url)
    if parsed is None:
        raise ValueError("snapshot data URL is not a base64 image data URL")
    media_type, b64 = parsed
    return [
        {
            "type": "text",
            "text": (
                f"Snapshot of the '{view_id}' view (captured from the live "
                "render). Inspect it and, if it doesn't match what was "
                "intended, fix the visualization and capture again."
            ),
        },
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": b64,
            },
        },
    ]


@register("capture_view_snapshot")
async def _capture_view_snapshot(ws, ti: dict) -> "str | dict":
    """Capture the current pixels of a rendered view and return them as an image.

    Sends a ``request_snapshot`` to the frontend (request_id + view_id), blocks
    on a Future until the frontend replies ``snapshot_result`` with a base64
    PNG data URL, then returns a tool_result carrying an inline image block so
    the (vision-capable) agent can SEE its own output and self-correct. On
    timeout / capture error, returns a plain-text error so the loop continues.
    """
    import uuid as _uuid

    view_id = (ti.get("view_id") or "").strip()
    if view_id not in _SNAPSHOT_VIEWS:
        return json.dumps({
            "success": False,
            "error": (
                f"capture_view_snapshot: unknown view_id '{view_id}'. "
                f"Valid views: {list(_SNAPSHOT_VIEWS)}."
            ),
        })

    timeout = float(ti.get("timeout_seconds") or _SNAPSHOT_TIMEOUT_DEFAULT)
    request_id = _uuid.uuid4().hex
    await ws.send_json({
        "type": "request_snapshot",
        "request_id": request_id,
        "view_id": view_id,
    })

    from .ws_handler import wait_for_snapshot
    result = await wait_for_snapshot(request_id, timeout)

    if result is None:
        return json.dumps({
            "success": False,
            "error": (
                f"capture_view_snapshot: no snapshot for '{view_id}' within "
                f"{timeout:.0f}s. The view may not be rendered/visible yet."
            ),
        })
    if result.get("error"):
        return json.dumps({
            "success": False,
            "error": f"capture_view_snapshot: frontend reported '{result['error']}'.",
        })

    data_url = result.get("data_url")
    if not data_url:
        return json.dumps({
            "success": False,
            "error": "capture_view_snapshot: frontend returned an empty snapshot.",
        })
    if len(data_url) > _MAX_DATA_URL_BYTES:
        return json.dumps({
            "success": False,
            "error": (
                "capture_view_snapshot: snapshot exceeded the size limit "
                f"({_MAX_DATA_URL_BYTES} bytes)."
            ),
        })

    try:
        blocks = build_snapshot_content_blocks(view_id, data_url)
    except ValueError as ve:
        return json.dumps({"success": False, "error": f"capture_view_snapshot: {ve}"})

    # Structured return: run_agent_loop unwraps ``_content_blocks`` into the
    # tool_result content so the image reaches the model.
    return {"_content_blocks": blocks}
