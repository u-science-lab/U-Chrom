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

logger = logging.getLogger(__name__)

# An executor: takes the live websocket + the tool_use.input dict, returns the
# tool_result content string (already JSON-encoded where structured).
Executor = Callable[[object, dict], Awaitable[str]]

# Registry, populated by @register below.
TOOL_EXECUTORS: dict[str, Executor] = {}


def register(name: str) -> Callable[[Executor], Executor]:
    def deco(fn: Executor) -> Executor:
        TOOL_EXECUTORS[name] = fn
        return fn
    return deco


def _apply_json_patch_to_view(view, patch: dict) -> None:
    """Apply a single {op, path, value} patch to a view's ``spec``.

    Mirrors the frontend ``applyGoslingPatch`` path walk so the backend
    snapshot stays byte-compatible with what the client renders. The path is
    rooted at the Gosling spec (e.g. ``/views/0/tracks/0/mark``).
    """
    spec = view.state.get("spec")
    if not isinstance(spec, dict):
        return
    path = patch.get("path", "")
    parts = [p for p in path.split("/") if p != ""]
    if not parts:
        return
    obj = spec
    for key in parts[:-1]:
        if isinstance(obj, list):
            try:
                obj = obj[int(key)]
            except (ValueError, IndexError):
                return
        elif isinstance(obj, dict):
            obj = obj.get(key)
        else:
            return
        if obj is None:
            return
    leaf = parts[-1]
    op = patch.get("op", "replace")
    if isinstance(obj, list):
        try:
            idx = int(leaf)
        except ValueError:
            return
        if op in ("replace", "add") and 0 <= idx < len(obj):
            obj[idx] = patch.get("value")
        elif op == "remove" and 0 <= idx < len(obj):
            obj.pop(idx)
    elif isinstance(obj, dict):
        if op in ("replace", "add"):
            obj[leaf] = patch.get("value")
        elif op == "remove":
            obj.pop(leaf, None)
    # Bump revision so a reconnect snapshot reflects the patched spec.
    view.revision += 1


# ---------------------------------------------------------------------------
# Gosling rendering
# ---------------------------------------------------------------------------

@register("render_gosling")
async def _render_gosling(ws, ti: dict) -> str:
    spec = ti.get("spec", {})
    title = ti.get("title", "Genomic Visualization")
    view_id = ti.get("_tool_use_id")
    # Record backend-authoritative view state so the agent can later read it
    # (get_view_state) and the frontend can rebuild it after a reconnect.
    session = ti.get("_session")
    if session is not None and view_id:
        view = session.get_or_create_view(view_id, "gosling", title=title)
        view.replace({"spec": spec, "title": title})
    await ws.send_json({
        "type": "agent_artifact",
        "artifact_type": "gosling_spec",
        "artifact_id": view_id,
        "title": title,
        "spec": spec,
    })
    return json.dumps({
        "success": True,
        "message": f"Gosling spec rendered successfully. Title: {title}",
        "spec_tracks": len(spec.get("tracks", [])),
        "view_id": view_id,
    })


@register("patch_gosling")
async def _patch_gosling(ws, ti: dict) -> str:
    target_id = ti.get("target_id", "")
    patch = ti.get("patch", {})
    # Validate BEFORE emitting — an invalid patch must not reach the frontend.
    if not target_id or not patch.get("path"):
        return json.dumps({
            "success": False,
            "error": "patch_gosling requires 'target_id' and a 'patch' with a 'path'.",
        })
    # Keep the backend-authoritative spec in sync with the patch the frontend
    # will apply, so a reconnect snapshot reflects the patched state.
    session = ti.get("_session")
    if session is not None and target_id in getattr(session, "views", {}):
        _apply_json_patch_to_view(session.views[target_id], patch)
    await ws.send_json({
        "type": "agent_artifact",
        "artifact_type": "gosling_patch",
        "target_id": target_id,
        "patch": patch,
    })
    return json.dumps({
        "success": True,
        "message": f"Applied {patch.get('op', 'replace')} to {patch.get('path')} on spec {target_id}.",
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
        result = {"status": "error", "output": "", "error": f"Execution failed: {e}"}

    await ws.send_json({
        "type": "agent_artifact",
        "artifact_type": "notebook_cell",
        "content": {
            "code": code,
            "output": result.get("output", ""),
            "error": result.get("error"),
            "status": result.get("status", "ok"),
        },
    })

    output_preview = result.get("output", "")[:100]
    error_preview = result.get("error", "")[:100] if result.get("error") else None
    if error_preview:
        return f"Cell added with error. Error: {error_preview}"
    return f"Cell added. Output: {output_preview}"


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


@register("color_embedding")
async def _color_embedding(ws, ti: dict) -> str:
    color_by = ti.get("color_by", "")
    await ws.send_json({
        "type": "agent_artifact",
        "artifact_type": "color_embedding",
        "color_by": color_by,
    })
    return f"Embedding colored by '{color_by}'."


@register("show_structure")
async def _show_structure(ws, ti: dict) -> str:
    cell_id = ti.get("cell_id", "")
    chrom = ti.get("chrom", "")
    await ws.send_json({
        "type": "agent_artifact",
        "artifact_type": "show_structure",
        "cell_id": cell_id,
        "chrom": chrom,
    })
    return (f"Showing 3D structure for cell '{cell_id}'"
            + (f", {chrom}" if chrom else "") + ".")


@register("color_structure")
async def _color_structure(ws, ti: dict) -> str:
    color_by = ti.get("color_by", "")
    await ws.send_json({
        "type": "agent_artifact",
        "artifact_type": "color_structure",
        "color_by": color_by,
    })
    return f"3D structure colored by '{color_by}'."


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
    return json.dumps({
        "success": True,
        "message": f"Composed custom view '{title}'.",
        "view_id": view_id,
    })

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
    # No id → list all views (id, type, revision, last_interaction).
    return json.dumps({
        "success": True,
        "views": [
            {
                "view_id": v.view_id,
                "view_type": v.view_type,
                "revision": v.revision,
                "last_interaction": v.state.get("last_interaction"),
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

    # Blocking mode: wait for the next interaction.
    from .ws_handler import wait_for_interaction
    event = await wait_for_interaction(session, view_id, timeout)
    if event is None:
        return json.dumps({
            "success": True, "interaction": None,
            "message": f"No interaction within {timeout:.0f}s.",
        })
    return json.dumps({"success": True, "interaction": event})
