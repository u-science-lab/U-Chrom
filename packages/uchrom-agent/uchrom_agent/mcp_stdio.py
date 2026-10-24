"""A fixed-tool MCP server over newline-delimited JSON-RPC stdio."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Callable, TextIO

from . import __version__
from .lifecycle import attach_handoff, shutdown_started_browser

_PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2024-11-05")
_MAX_SELECTION_CELLS = 100
_EXPORT_DIR = Path(tempfile.gettempdir()) / "uchrom-agent"


def _object_schema(properties=None, required=()):
    return {"type": "object", "properties": properties or {}, **({"required": list(required)} if required else {})}


_TOOLS = [
    {"name": "uchrom_setup_status", "description": "Check the local companion and browser server status.",
     "inputSchema": _object_schema(), "annotations": {"readOnlyHint": True}},
    {"name": "uchrom_attach_handoff", "description": "Optional relay/import tool: open or reuse the local U-Chrom browser from an explicitly enabled handoff JSON file or relay token. The default local-first flow starts the page first and reads canonical state; UI state is proposed for WebUI approval.",
     "inputSchema": _object_schema({"handoff_token": {"type": "string", "description": "A one-time handoff token, or path to a local handoff JSON file containing dataset.path."}}, ("handoff_token",))},
    {"name": "uchrom_workspace_snapshot", "description": "Read canonical state from an explicitly pinned local browser page.",
     "inputSchema": _object_schema({"page_id": {"type": "string"}}), "annotations": {"readOnlyHint": True}},
    {"name": "uchrom_get_selection", "description": "Read the canonical page selection, summarizing large selections.",
     "inputSchema": _object_schema({"page_id": {"type": "string"}, "max_cells": {"type": "integer", "minimum": 0}}), "annotations": {"readOnlyHint": True}},
    {"name": "uchrom_export_selection", "description": "Write canonical selected cell IDs to a private temporary JSON file and return its path and digest.",
     "inputSchema": _object_schema({"page_id": {"type": "string"}}), "annotations": {"readOnlyHint": True}},
    {"name": "uchrom_list_groups", "description": "List groups available in the explicitly pinned local browser page.",
     "inputSchema": _object_schema({"page_id": {"type": "string"}}), "annotations": {"readOnlyHint": True}},
    {"name": "uchrom_capture_view", "description": "Capture a local browser view to a temporary file.",
     "inputSchema": _object_schema({"page_id": {"type": "string"}, "pane": {"type": "string"},
                                     "format": {"type": "string", "enum": ["png", "svg", "pdf"]}}),
     "annotations": {"readOnlyHint": True}},
    {"name": "uchrom_plan_status", "description": "Read the status and canonical result of a pending UI plan.",
     "inputSchema": _object_schema({"plan_id": {"type": "string"}}, ("plan_id",)), "annotations": {"readOnlyHint": True}},
    {"name": "uchrom_export_snapshot", "description": "Export canonical workspace state to a private temporary JSON file.",
     "inputSchema": _object_schema({"page_id": {"type": "string"}}), "annotations": {"readOnlyHint": True}},
    {"name": "uchrom_propose_ui_changes", "description": "Create a pending UI change plan. The user must Apply or Reject it in the local U-Chrom WebUI.",
     "inputSchema": _object_schema({"page_id": {"type": "string"}, "expected_revision": {"type": "string"},
                                     "changes": {"type": "array", "items": {"type": "object",
                                         "required": ["name", "args"], "properties": {
                                             "name": {"type": "string"}, "args": {"type": "object"}}}}},
                                    ("changes",)),
     "annotations": {"readOnlyHint": False, "destructiveHint": False}},
]
_TOOL_BY_NAME = {tool["name"]: tool for tool in _TOOLS}


def _validate_arguments(name: str, arguments: Any) -> dict[str, Any]:
    if name not in _TOOL_BY_NAME:
        raise ValueError(f"unknown tool: {name}")
    if not isinstance(arguments, dict):
        raise ValueError("tool arguments must be an object")
    schema = _TOOL_BY_NAME[name]["inputSchema"]
    missing = [key for key in schema.get("required", []) if key not in arguments]
    if missing:
        raise ValueError(f"missing required argument(s): {', '.join(missing)}")
    for key, value in arguments.items():
        prop = schema["properties"].get(key)
        if prop is None:
            raise ValueError(f"unknown argument: {key}")
        expected = prop.get("type")
        valid = {"string": lambda v: isinstance(v, str),
                 "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
                 "array": lambda v: isinstance(v, list),
                 "object": lambda v: isinstance(v, dict)}.get(expected, lambda _v: True)
        if not valid(value):
            raise ValueError(f"{key} must be {expected}")
        if "enum" in prop and value not in prop["enum"]:
            raise ValueError(f"{key} must be one of {', '.join(prop['enum'])}")
    return arguments


def _write_export(data: Any, suffix: str) -> dict[str, Any]:
    _EXPORT_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(_EXPORT_DIR, 0o700)
    except OSError:
        pass
    encoded = json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    fd, name = tempfile.mkstemp(prefix="uchrom-", suffix=suffix, dir=_EXPORT_DIR)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(encoded)
    except Exception:
        Path(name).unlink(missing_ok=True)
        raise
    return {"path": name, "bytes": len(encoded), "sha256": hashlib.sha256(encoded).hexdigest()}


class _Bridge:
    def __init__(self, workspace=None):
        self.workspace = workspace
        self.page_id: str | None = None

    def _workspace(self):
        if self.workspace is None:
            from uchrom_browser import connect
            self.workspace = connect()
        return self.workspace

    def _pin_page(self, page_id: str | None = None) -> str:
        ws = self._workspace()
        if page_id:
            ws._request("POST", "/api/agent/attach", {"page_id": page_id})
            self.page_id = page_id
            return page_id
        if self.page_id:
            pages = ws.agent_pages()
            if any(p.get("page") == self.page_id for p in pages):
                return self.page_id
            raise RuntimeError(
                f"pinned page {self.page_id!r} is no longer connected; provide an explicit page_id to attach another page"
            )
        pages = ws.agent_pages()
        if len(pages) != 1:
            raise RuntimeError("an explicit page_id is required when zero or multiple browser pages are connected")
        page_id = pages[0].get("page")
        if not page_id:
            raise RuntimeError("browser returned a page without an id")
        ws._request("POST", "/api/agent/attach", {"page_id": page_id})
        self.page_id = page_id
        return page_id

    def _snapshot(self, page_id: str | None = None):
        ws = self._workspace()
        pinned = self._pin_page(page_id)
        return ws.agent_snapshot(pinned)

    def _bind_handoff(self, page_id, workspace):
        self.workspace = workspace
        self.page_id = page_id

    def _page_action(self, name: str, args: dict[str, Any], page_id: str | None = None):
        ws = self._workspace()
        pinned = self._pin_page(page_id)
        if hasattr(ws, "_request"):
            result = ws._request("POST", "/api/control/actions", {
                "name": name, "args": args, "timeout": ws.timeout, "page": pinned,
            })
            return result["result"]
        return ws.call(name, **args)

    def _call(self, name: str, args: dict[str, Any]):
        if name == "uchrom_setup_status":
            try:
                ws = self._workspace()
                health = ws._request("GET", "/api/health")
                pages = ws.agent_pages()
                stage = "page_pinned" if any(page.get("pinned") for page in pages) else (
                    "page_connected" if pages else "browser_ready"
                )
                return {"companion_version": __version__, "mcp_status": "ready",
                        "browser_status": "running", "browser_url": ws.url,
                        "connected_pages": len(pages), "health": health, "stage": stage}
            except Exception as exc:
                return {"companion_version": __version__, "mcp_status": "ready",
                        "browser_status": "not_running", "stage": "not_running", "detail": str(exc)}

        if name == "uchrom_attach_handoff":
            payload = attach_handoff(args["handoff_token"], connect=self._workspace,
                                     pin_page=self._bind_handoff)
            return payload

        if name == "uchrom_workspace_snapshot":
            return self._snapshot(args.get("page_id"))
        if name == "uchrom_get_selection":
            selection = self._page_action("get_selection", {}, args.get("page_id"))
            cells = selection.get("cells", [])
            limit = args.get("max_cells", _MAX_SELECTION_CELLS)
            result = {key: value for key, value in selection.items() if key != "cells"}
            result.update({"n_cells": len(cells), "cells": cells[:limit] if len(cells) <= limit else None,
                           "truncated": len(cells) > limit})
            return result
        if name == "uchrom_export_selection":
            selection = self._page_action("get_selection", {}, args.get("page_id"))
            cells = selection.get("cells", [])
            return {**_write_export({"cells": cells}, ".selection.json"), "n_cells": len(cells)}
        if name == "uchrom_list_groups":
            return self._page_action("list_groups", {}, args.get("page_id"))
        if name == "uchrom_capture_view":
            fmt = args.get("format", "png")
            capture = self._page_action("capture_view", {"pane": args.get("pane"), "format": fmt}, args.get("page_id"))
            encoded = capture.get("data_base64") or capture.get("png_base64")
            if not encoded:
                raise RuntimeError("browser capture did not include image data")
            raw = base64.b64decode(encoded, validate=True)
            _EXPORT_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd, path = tempfile.mkstemp(prefix="uchrom-view-", suffix=f".{fmt}", dir=_EXPORT_DIR)
            with os.fdopen(fd, "wb") as output:
                output.write(raw)
            return {"path": path, "pane": capture.get("pane"), "format": fmt,
                    "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                    "notes": capture.get("notes", [])}
        if name == "uchrom_plan_status":
            return self._workspace().plan_status(args["plan_id"])
        if name == "uchrom_export_snapshot":
            snapshot = self._snapshot(args.get("page_id"))
            return {**_write_export(snapshot, ".snapshot.json"), "state_revision": snapshot.get("state_revision")}
        if name == "uchrom_propose_ui_changes":
            snapshot = self._snapshot(args.get("page_id"))
            page = snapshot["page_id"]
            revision = args.get("expected_revision", snapshot["state_revision"])
            changes = args["changes"]
            if any(not isinstance(change, dict) or not isinstance(change.get("name"), str)
                   or not isinstance(change.get("args"), dict) for change in changes):
                raise ValueError("each change must contain a string name and object args")
            return self._workspace().propose_ui_changes(changes, page, revision)
        raise ValueError(f"unknown tool: {name}")


def _tool_result(data: Any, *, is_error: bool = False):
    text = json.dumps(data, ensure_ascii=True, sort_keys=True)
    return {"content": [{"type": "text", "text": text}], "structuredContent": data,
            **({"isError": True} if is_error else {})}


def _response(message_id: Any, result: Any = None, error: dict[str, Any] | None = None):
    response = {"jsonrpc": "2.0", "id": message_id}
    response["error" if error is not None else "result"] = error if error is not None else result
    return response


def _dispatch(request: Any, bridge: _Bridge):
    if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
        return _response(request.get("id") if isinstance(request, dict) else None,
                         error={"code": -32600, "message": "invalid JSON-RPC request"})
    method = request["method"]
    message_id = request.get("id")
    params = request.get("params") or {}
    if not isinstance(params, dict):
        return _response(message_id, error={"code": -32602, "message": "params must be an object"})
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return _response(message_id, {}) if "id" in request else None
    if method == "initialize":
        requested = params.get("protocolVersion")
        if requested is not None and requested not in _PROTOCOL_VERSIONS:
            return _response(message_id, error={"code": -32602, "message": "unsupported MCP protocol version"})
        return _response(message_id, {"protocolVersion": requested or _PROTOCOL_VERSIONS[0],
                                      "capabilities": {"tools": {}},
                                      "serverInfo": {"name": "uchrom-agent", "version": __version__}})
    if method == "tools/list":
        return _response(message_id, {"tools": _TOOLS}) if "id" in request else None
    if method == "tools/call":
        if "id" not in request:
            return None
        name = params.get("name")
        try:
            arguments = _validate_arguments(name, params.get("arguments", {}))
            result = bridge._call(name, arguments)
            return _response(message_id, _tool_result(result))
        except ValueError as exc:
            return _response(message_id, error={"code": -32602, "message": str(exc)})
        except Exception as exc:
            return _response(message_id, _tool_result({"error": str(exc)}, is_error=True))
    if "id" not in request:
        return None
    return _response(message_id, error={"code": -32601, "message": f"method not found: {method}"})


def serve(in_stream: TextIO | None = None, out_stream: TextIO | None = None, *, workspace=None) -> None:
    """Serve one JSON-RPC request per line. Stdout is reserved for protocol messages."""
    import sys

    incoming = in_stream or sys.stdin
    outgoing = out_stream or sys.stdout
    bridge = _Bridge(workspace)
    for line in incoming:
        try:
            request = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            response = _response(None, error={"code": -32700, "message": "parse error"})
        else:
            response = _dispatch(request, bridge)
        if response is not None:
            outgoing.write(json.dumps(response, ensure_ascii=True) + "\n")
            outgoing.flush()
    shutdown_started_browser()
