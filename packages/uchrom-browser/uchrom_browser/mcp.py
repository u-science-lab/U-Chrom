"""Pure-stdlib JSON-RPC 2.0 stdio MCP server for the U-Chrom web browser.

Exposes browser actions from ``/api/control/tools`` (fallback: ``ui_tools.json``) as
``uchrom_<action>`` tools alongside ``uchrom_status``, ``uchrom_list_pages``, and
``uchrom_bind_page``, with explicit multi-tab safety and file-backed ``uchrom_capture_view``.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import math
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO

from . import __version__
from .client import BrowserError, _capture_format, _default_url
from .control import load_tools

SUPPORTED_PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2024-11-05")
_SESSION_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "uchrom_status",
        "description": "Check browser server health, loaded datasets, connected pages, and the currently bound page.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "uchrom_list_pages",
        "description": "List connected browser pages (tabs) and the currently bound page.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "uchrom_bind_page",
        "description": "Bind this MCP session to a connected browser page id, or pass null/empty string to clear.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "page": {
                    "type": ["string", "null"],
                    "description": "Browser page id from uchrom_list_pages, or null to unbind.",
                }
            },
        },
    },
]


class _RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _reject_constant(token: str) -> Any:
    raise ValueError(f"non-JSON constant {token!r} is not allowed")


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return (
            (isinstance(value, int) and not isinstance(value, bool))
            or (isinstance(value, float) and math.isfinite(value) and value.is_integer())
        )
    if expected == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        try:
            return math.isfinite(float(value))
        except OverflowError:
            return False
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "null":
        return value is None
    return True


def _validate_value(path: str, value: Any, schema: Dict[str, Any]) -> Optional[str]:
    expected = schema.get("type")
    if expected is not None:
        allowed = [expected] if isinstance(expected, str) else list(expected)
        if not any(_matches_type(value, t) for t in allowed):
            return f"argument {path!r} must be {' or '.join(allowed)}"
    if "enum" in schema and value not in schema["enum"]:
        return f"argument {path!r} must be one of {schema['enum']!r}"
    if isinstance(value, list) and "items" in schema:
        item_schema = schema["items"]
        for idx, item in enumerate(value):
            err = _validate_value(f"{path}[{idx}]", item, item_schema)
            if err is not None:
                return err
    return None


def _validate_arguments(schema: Dict[str, Any], arguments: Dict[str, Any]) -> Optional[str]:
    props = schema.get("properties") or {}
    required = schema.get("required") or []
    missing = [k for k in required if k not in arguments]
    if missing:
        return f"missing required argument(s): {', '.join(missing)}"
    unknown = [k for k in arguments if k not in props]
    if unknown:
        return f"unknown argument(s): {', '.join(unknown)}"
    for key, val in arguments.items():
        err = _validate_value(key, val, props[key])
        if err is not None:
            return err
    return None


def _tool_ok(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "structuredContent": payload,
        "isError": False,
    }


def _tool_err(message: str) -> Dict[str, Any]:
    return {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    }


def _write_private_temp(data: bytes, fmt: str) -> Path:
    temp_dir = Path(tempfile.gettempdir()) / "uchrom-browser-mcp"
    if temp_dir.is_symlink():
        raise OSError(f"temporary capture directory {temp_dir} must not be a symlink")
    temp_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(temp_dir, 0o700)
    fd, tmp_name = tempfile.mkstemp(prefix="uchrom_view_", suffix=f".{fmt}", dir=str(temp_dir))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return tmp_path


def _resolve_capture_dest(out_path: str, explicit_fmt: Optional[str], fmt: str) -> Path:
    raw = Path(out_path)
    if ".." in raw.parts:
        raise ValueError("capture path must not contain '..'")
    if explicit_fmt is not None and raw.suffix and raw.suffix.lower().lstrip(".") != fmt:
        raise ValueError(f"capture path suffix {raw.suffix!r} conflicts with format {fmt!r}")
    cur = Path("/") if raw.is_absolute() else Path.cwd()
    for part in raw.parts:
        if part in ("", "/"):
            continue
        cur = cur / part
        if cur.is_symlink():
            raise ValueError(f"capture path must not traverse or target symlinks: {cur}")
    if raw.exists():
        raise FileExistsError(f"refusing to overwrite existing file: {raw}")
    return raw


def _write_exclusive(dest: Path, data: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(dest), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
    except BaseException:
        dest.unlink(missing_ok=True)
        raise


class McpServer:
    """Stdio JSON-RPC 2.0 MCP server bridging to a running ``uchrom_browser`` HTTP server."""

    def __init__(self, url: Optional[str] = None, timeout: float = 30.0):
        self.url = (url or _default_url()).rstrip("/")
        self.timeout = float(timeout)
        self.bound_page: Optional[str] = None

    # -- HTTP transport ---------------------------------------------------
    def _request(self, method: str, path: str, body: Any = None, timeout: Optional[float] = None) -> Any:
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self.url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        effective_timeout = self.timeout if timeout is None else timeout
        try:
            with urllib.request.urlopen(req, timeout=effective_timeout + 5) as resp:
                return json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read()).get("detail", exc.reason)
            except ValueError:
                detail = exc.reason
            raise BrowserError(f"{exc.code}: {detail}") from None
        except urllib.error.URLError as exc:
            raise BrowserError(
                f"cannot reach the browser server at {self.url} ({exc.reason}); "
                "start it with `python -m uchrom_browser data.chromdata.zarr`"
            ) from None

    # -- tool catalog -----------------------------------------------------
    def _load_ui_tools(self) -> List[Dict[str, Any]]:
        try:
            payload = self._request("GET", "/api/control/tools", timeout=min(self.timeout, 5.0))
            tools = payload["tools"]
            if isinstance(tools, list):
                return tools
        except (BrowserError, KeyError, TypeError, ValueError):
            pass
        return load_tools()["tools"]

    def _build_tools(self) -> List[Dict[str, Any]]:
        tools: List[Dict[str, Any]] = [copy.deepcopy(t) for t in _SESSION_TOOLS]
        for raw in self._load_ui_tools():
            schema = copy.deepcopy(raw["inputSchema"])
            props = schema.setdefault("properties", {})
            props["page"] = {
                "type": "string",
                "description": "Target browser page id from uchrom_list_pages",
            }
            if raw["name"] == "capture_view":
                props["path"] = {
                    "type": "string",
                    "description": "Optional non-existing output file path (PNG, SVG, or PDF; no '..' or symlinks). Defaults to a private temporary file.",
                }
            entry: Dict[str, Any] = {
                "name": f"uchrom_{raw['name']}",
                "description": raw["description"],
                "inputSchema": schema,
            }
            if raw["name"] == "capture_view":
                entry["annotations"] = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False}
            elif "annotations" in raw:
                entry["annotations"] = copy.deepcopy(raw["annotations"])
            tools.append(entry)
        return tools

    # -- page safety ------------------------------------------------------
    def _connected_pages(self) -> List[Dict[str, Any]]:
        pages = self._request("GET", "/api/control/pages")
        if not isinstance(pages, list):
            raise BrowserError("unexpected response from /api/control/pages")
        return pages

    def _resolve_page(self, explicit_page: Optional[str]) -> str:
        connected = [p["page"] for p in self._connected_pages()]
        listed = ", ".join(connected) if connected else "none"
        if explicit_page is not None:
            if explicit_page not in connected:
                raise BrowserError(
                    f"browser page {explicit_page!r} is not connected; connected pages: {listed}"
                )
            return explicit_page
        if self.bound_page is not None:
            if self.bound_page not in connected:
                raise BrowserError(
                    f"bound browser page {self.bound_page!r} is no longer connected "
                    f"(connected pages: {listed}); call uchrom_bind_page to rebind or unbind"
                )
            return self.bound_page
        if not connected:
            raise BrowserError("no browser page is connected; open the browser (python -m uchrom_browser ...)")
        if len(connected) == 1:
            return connected[0]
        raise BrowserError(
            f"multiple browser pages are connected ({listed}); pass 'page' or call uchrom_bind_page"
        )

    # -- tool execution ---------------------------------------------------
    def _call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        tools_by_name = {t["name"]: t for t in self._build_tools()}
        tool = tools_by_name.get(name)
        if tool is None:
            raise _RpcError(-32602, f"Unknown tool: {name}")

        err = _validate_arguments(tool["inputSchema"], arguments)
        if err is not None:
            return _tool_err(err)

        try:
            if name == "uchrom_status":
                health = self._request("GET", "/api/health")
                datasets = self._request("GET", "/api/datasets")
                pages = self._connected_pages()
                return _tool_ok({
                    "url": self.url,
                    "health": health,
                    "datasets": datasets,
                    "pages": pages,
                    "bound_page": self.bound_page,
                })

            if name == "uchrom_list_pages":
                pages = self._connected_pages()
                return _tool_ok({"pages": pages, "bound_page": self.bound_page})

            if name == "uchrom_bind_page":
                page = arguments.get("page")
                pages = self._connected_pages()
                if page is None or page == "":
                    self.bound_page = None
                    return _tool_ok({"bound_page": None, "pages": pages})
                connected = [p["page"] for p in pages]
                if page not in connected:
                    listed = ", ".join(connected) if connected else "none"
                    return _tool_err(
                        f"cannot bind unknown browser page {page!r}; connected pages: {listed}"
                    )
                self.bound_page = page
                return _tool_ok({"bound_page": page, "pages": pages})

            action = name.removeprefix("uchrom_")
            if action == "capture_view":
                return _tool_ok(self._handle_capture_view(arguments))

            target_page = self._resolve_page(arguments.get("page"))
            action_args = {k: v for k, v in arguments.items() if k != "page" and v is not None}
            resp = self._request(
                "POST",
                "/api/control/actions",
                {"name": action, "args": action_args, "timeout": self.timeout, "page": target_page},
            )
            result = resp["result"]
            if isinstance(result, dict):
                out = {**result, "page": target_page}
            else:
                out = {"result": result, "page": target_page}
            return _tool_ok(out)
        except (BrowserError, ValueError, OSError) as exc:
            return _tool_err(str(exc))

    def _handle_capture_view(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        target_page = self._resolve_page(arguments.get("page"))
        pane = arguments.get("pane")
        out_path = arguments.get("path")
        explicit_fmt = arguments.get("format")
        fmt = _capture_format(explicit_fmt, out_path)
        dest: Optional[Path] = _resolve_capture_dest(out_path, explicit_fmt, fmt) if out_path else None
        action_args: Dict[str, Any] = {"format": fmt}
        if pane is not None:
            action_args["pane"] = pane
        resp = self._request(
            "POST",
            "/api/control/actions",
            {"name": "capture_view", "args": action_args, "timeout": self.timeout, "page": target_page},
        )
        result = resp["result"]
        b64 = result.get("data_base64") or result.get("png_base64")
        if not b64:
            raise BrowserError("capture_view did not return image data")
        data = base64.b64decode(b64)
        if dest is not None:
            _write_exclusive(dest, data)
        else:
            dest = _write_private_temp(data, fmt)
        return {
            "path": str(dest),
            "pane": pane if pane is not None else result.get("pane"),
            "format": fmt,
            "width": result.get("width"),
            "height": result.get("height"),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "notes": list(result.get("notes") or []),
            "page": target_page,
        }

    # -- JSON-RPC dispatch ------------------------------------------------
    def _dispatch(self, method: str, params: Any, *, has_id: bool) -> Any:
        if method.startswith("notifications/"):
            if has_id:
                raise _RpcError(-32600, "notifications must not include 'id'")
            return None

        if not has_id:
            return None

        if method == "initialize":
            if params is None:
                params = {}
            elif not isinstance(params, dict):
                raise _RpcError(-32602, "initialize params must be an object")
            requested = params.get("protocolVersion")
            version = (
                requested
                if requested in SUPPORTED_PROTOCOL_VERSIONS
                else SUPPORTED_PROTOCOL_VERSIONS[0]
            )
            return {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "uchrom-browser", "version": __version__},
            }

        if method == "ping":
            if params is not None and not isinstance(params, dict):
                raise _RpcError(-32602, "ping params must be an object")
            return {}

        if method == "tools/list":
            if params is not None and not isinstance(params, dict):
                raise _RpcError(-32602, "tools/list params must be an object")
            return {"tools": self._build_tools()}

        if method == "tools/call":
            if not isinstance(params, dict) or not isinstance(params.get("name"), str):
                raise _RpcError(-32602, "tools/call params must include string 'name'")
            arguments = params.get("arguments")
            if arguments is None:
                arguments = {}
            elif not isinstance(arguments, dict):
                raise _RpcError(-32602, "tools/call 'arguments' must be an object")
            return self._call_tool(params["name"], arguments)

        raise _RpcError(-32601, f"Method not found: {method}")

    def handle_line(self, line: str, out: TextIO) -> None:
        if not line.strip():
            return
        try:
            msg = json.loads(line, parse_constant=_reject_constant)
        except (json.JSONDecodeError, ValueError) as exc:
            self._write(out, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {exc}"}})
            return

        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
            self._write(out, {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}})
            return

        has_id = "id" in msg
        req_id = msg.get("id")
        if has_id and (isinstance(req_id, bool) or not (req_id is None or isinstance(req_id, (str, int)))):
            self._write(out, {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request: invalid id"}})
            return

        try:
            result = self._dispatch(msg["method"], msg.get("params"), has_id=has_id)
        except _RpcError as exc:
            if has_id:
                self._write(out, {"jsonrpc": "2.0", "id": req_id, "error": {"code": exc.code, "message": exc.message}})
            return
        except Exception as exc:  # noqa: BLE001
            if has_id:
                self._write(out, {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32603, "message": f"Internal error: {exc}"}})
            return

        if has_id:
            self._write(out, {"jsonrpc": "2.0", "id": req_id, "result": result})

    @staticmethod
    def _write(out: TextIO, payload: Dict[str, Any]) -> None:
        out.write(json.dumps(payload, ensure_ascii=True, allow_nan=False) + "\n")
        out.flush()

    def serve_stdio(self, stdin: Optional[TextIO] = None, stdout: Optional[TextIO] = None) -> None:
        inp = sys.stdin if stdin is None else stdin
        out = sys.stdout if stdout is None else stdout
        for line in inp:
            self.handle_line(line, out)


def _cli(argv: Optional[List[str]] = None) -> None:
    """Run the ``uchrom-browser-mcp`` stdio MCP server."""
    parser = argparse.ArgumentParser(
        prog="uchrom-browser-mcp",
        description="Stdio JSON-RPC 2.0 MCP server for a running U-Chrom browser.",
    )
    parser.add_argument("--url", default=None, help="Browser server URL (default: $UCHROM_BROWSER_URL, state file, or http://127.0.0.1:8765)")
    parser.add_argument("--timeout", type=float, default=30.0, help="Action timeout in seconds (default: 30)")
    args = parser.parse_args(argv)
    McpServer(url=args.url, timeout=args.timeout).serve_stdio()


if __name__ == "__main__":
    _cli()
