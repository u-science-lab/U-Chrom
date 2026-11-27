"""Pure-stdlib JSON-RPC 2.0 stdio MCP server for the U-Chrom web browser.

Exposes browser actions from ``/api/control/tools`` (fallback: ``ui_tools.json``) as
``uchrom_<action>`` tools alongside ``uchrom_status``, ``uchrom_list_pages``,
``uchrom_bind_page``, and ``uchrom_wait_for_page``, with explicit multi-tab safety,
MCP ``resources`` / ``prompts``, file-backed ``uchrom_capture_view``, ``--doctor``,
and ``--print-config``.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import http.client
import json
import math
import os
import secrets
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO

from . import __version__
from .client import BrowserError, STATE_FILE, _capture_format, _default_url
from .control import load_tools

SUPPORTED_PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2024-11-05")
MAX_SAFE_INT = (1 << 63) - 1
MAX_JSON_INT_DIGITS = 1024
MAX_RPC_ID_LEN = 4096


class ServerUnreachableError(BrowserError):
    """The browser HTTP server could not be reached."""


class NoPageConnectedError(BrowserError):
    """Zero browser tabs are connected (or timed out waiting for one)."""


class PageConflictError(BrowserError):
    """Multiple tabs are connected without selection, or the target/bound tab is unavailable."""

    def __init__(self, message: str, connected_pages: Optional[List[str]] = None):
        super().__init__(message)
        self.connected_pages = list(connected_pages or [])


class ActionExecutionError(BrowserError):
    """The HTTP server or browser page rejected or failed the requested action."""


class BatchStepError(BrowserError):
    """A batch execution step failed partway through."""

    def __init__(self, cause: Exception, page: str, step_index: int, action: str, results: List[Dict[str, Any]]):
        super().__init__(str(cause))
        self.cause = cause
        self.page = page
        self.step_index = step_index
        self.action = action
        self.results = list(results)


_SESSION_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "uchrom_status",
        "description": "Check browser server health, loaded datasets, connected pages, and the currently bound page.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "uchrom_list_pages",
        "description": "List connected browser pages (tabs) with optional per-tab workspace summaries, loaded datasets, and the currently bound page.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "probe": {
                    "type": "boolean",
                    "description": "Query up to 8 active tabs' describe_workspace for their active dataset, layout, and selection summary (default: true).",
                }
            },
        },
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
    {
        "name": "uchrom_wait_for_page",
        "description": "Wait for a browser tab (or a specific page id) to connect before dispatching actions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "page": {
                    "type": "string",
                    "description": "Optional specific browser page id to wait for.",
                },
                "wait_seconds": {
                    "type": "number",
                    "description": "Maximum seconds to wait (0-60, default 10).",
                },
            },
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "uchrom_batch",
        "description": "Validate all steps upfront and run 1..20 browser UI actions sequentially on a single resolved tab.",
        "inputSchema": {
            "type": "object",
            "required": ["steps"],
            "properties": {
                "steps": {
                    "type": "array",
                    "description": "Ordered list of {action, args?} objects using ui_tools.json action names.",
                    "items": {"type": "object"},
                },
                "page": {
                    "type": "string",
                    "description": "Target browser page id from uchrom_list_pages",
                },
            },
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
    },
]

_RESOURCES: List[Dict[str, Any]] = [
    {
        "uri": "uchrom://status",
        "name": "browser-status",
        "description": "Browser server health, loaded datasets, connected tabs, and current page binding.",
        "mimeType": "application/json",
    },
    {
        "uri": "uchrom://pages",
        "name": "connected-pages",
        "description": "Connected browser tabs with active dataset/workspace summaries, loaded datasets, and bound page.",
        "mimeType": "application/json",
    },
    {
        "uri": "uchrom://workspace",
        "name": "active-workspace",
        "description": "Active dataset metadata, open panes, focus, and lasso selection of the resolved browser page.",
        "mimeType": "application/json",
    },
    {
        "uri": "uchrom://selection",
        "name": "current-selection",
        "description": "Cell IDs currently lassoed or focused by the researcher in the resolved browser page.",
        "mimeType": "application/json",
    },
]

_PROMPTS: List[Dict[str, Any]] = [
    {
        "name": "compare-selection",
        "description": "Inspect the researcher's browser selection, run quantitative comparison checks, and open matching browser views.",
        "arguments": [
            {"name": "against", "description": "Reference group spec (default: rest)", "required": False},
            {"name": "stat", "description": "Comparison metric (default: rg)", "required": False},
            {"name": "chrom", "description": "Optional chromosome restriction", "required": False},
        ],
    },
    {
        "name": "inspect-locus",
        "description": "Focus the browser on a genomic interval, open Genome/Matrix/Stats views, and optionally export a figure.",
        "arguments": [
            {"name": "chrom", "description": "Chromosome name (e.g. chr15)", "required": True},
            {"name": "start", "description": "Optional 0-based start coordinate in bp", "required": False},
            {"name": "end", "description": "Optional end coordinate in bp", "required": False},
            {"name": "export_path", "description": "Optional PNG/SVG/PDF export path", "required": False},
        ],
    },
]


class _RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _reject_constant(token: str) -> Any:
    raise ValueError(f"non-JSON constant {token!r} is not allowed")


def _parse_json_int(token: str) -> int:
    digits = token.lstrip("+-")
    if len(digits) > MAX_JSON_INT_DIGITS:
        raise ValueError(f"integer literal exceeds {MAX_JSON_INT_DIGITS} digits")
    return int(token)


def _json_loads_strict(text: str) -> Any:
    try:
        return json.loads(text, parse_constant=_reject_constant, parse_int=_parse_json_int)
    except RecursionError:
        raise ValueError("JSON nesting depth exceeded") from None


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    return obj


def _in_safe_int_range(value: int) -> bool:
    return -(MAX_SAFE_INT + 1) <= value <= MAX_SAFE_INT


def _check_nested_finite(path: str, value: Any, depth: int = 0) -> Optional[str]:
    if depth > 64:
        return f"argument {path!r} exceeds maximum nesting depth"
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        if not _in_safe_int_range(value):
            return f"argument {path!r} integer is out of 64-bit range"
        return None
    if isinstance(value, float):
        if not math.isfinite(value):
            return f"argument {path!r} must be a finite number"
        return None
    if isinstance(value, list):
        for idx, item in enumerate(value):
            err = _check_nested_finite(f"{path}[{idx}]", item, depth + 1)
            if err is not None:
                return err
        return None
    if isinstance(value, dict):
        for k, v in value.items():
            err = _check_nested_finite(f"{path}.{k}", v, depth + 1)
            if err is not None:
                return err
        return None
    return None


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return _in_safe_int_range(value)
        if isinstance(value, float) and math.isfinite(value) and value.is_integer():
            try:
                return _in_safe_int_range(int(value))
            except OverflowError:
                return False
        return False
    if expected == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if isinstance(value, int) and not _in_safe_int_range(value):
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


def _validate_value(path: str, value: Any, schema: Dict[str, Any], depth: int = 0) -> Optional[str]:
    if depth > 64:
        return f"argument {path!r} exceeds maximum nesting depth"
    expected = schema.get("type")
    if expected is not None:
        allowed = [expected] if isinstance(expected, str) else list(expected)
        if not any(_matches_type(value, t) for t in allowed):
            return f"argument {path!r} must be {' or '.join(allowed)}"
    if "enum" in schema and value not in schema["enum"]:
        return f"argument {path!r} must be one of {schema['enum']!r}"
    if isinstance(value, list):
        if "items" in schema:
            item_schema = schema["items"]
            for idx, item in enumerate(value):
                err = _validate_value(f"{path}[{idx}]", item, item_schema, depth + 1)
                if err is not None:
                    return err
        else:
            err = _check_nested_finite(path, value, depth)
            if err is not None:
                return err
    elif isinstance(value, dict):
        err = _check_nested_finite(path, value, depth)
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
    clean = _json_safe(payload)
    return {
        "content": [{"type": "text", "text": json.dumps(clean, ensure_ascii=False, allow_nan=False)}],
        "structuredContent": clean,
        "isError": False,
    }


def _tool_err(message: str) -> Dict[str, Any]:
    return {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    }


def _write_private_temp(data: bytes, fmt: str) -> Path:
    o_dir = getattr(os, "O_DIRECTORY", 0)
    o_nofollow = getattr(os, "O_NOFOLLOW", 0)
    temp_root = Path(tempfile.gettempdir())
    base_fd = os.open(str(temp_root), os.O_RDONLY | o_dir)
    sub_fd: Optional[int] = None
    try:
        try:
            sub_fd = os.open("uchrom-browser-mcp", os.O_RDONLY | o_dir | o_nofollow, dir_fd=base_fd)
        except FileNotFoundError:
            try:
                os.mkdir("uchrom-browser-mcp", 0o700, dir_fd=base_fd)
            except FileExistsError:
                pass
            sub_fd = os.open("uchrom-browser-mcp", os.O_RDONLY | o_dir | o_nofollow, dir_fd=base_fd)

        st = os.fstat(sub_fd)
        if not stat.S_ISDIR(st.st_mode):
            raise OSError("temporary capture directory must be a directory")
        if hasattr(os, "getuid") and st.st_uid != os.getuid():
            raise OSError("temporary capture directory is not owned by the current user")
        os.fchmod(sub_fd, 0o700)

        for _ in range(16):
            name = f"uchrom_view_{secrets.token_hex(8)}.{fmt}"
            try:
                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | o_nofollow, 0o600, dir_fd=sub_fd)
            except FileExistsError:
                continue
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(data)
            except BaseException:
                try:
                    os.unlink(name, dir_fd=sub_fd)
                except OSError:
                    pass
                raise
            return temp_root / "uchrom-browser-mcp" / name
        raise OSError("failed to allocate unique temporary capture file")
    finally:
        if sub_fd is not None:
            os.close(sub_fd)
        os.close(base_fd)


def _resolve_capture_dest(out_path: str, explicit_fmt: Optional[str], fmt: str) -> Path:
    if "\x00" in str(out_path):
        raise ValueError("capture path must not contain NUL bytes")
    if not str(out_path).strip():
        raise ValueError("capture path must not be empty")
    raw = Path(out_path)
    if not raw.name or raw.name in (".", ".."):
        raise ValueError(f"capture path must name an output file: {out_path!r}")
    if ".." in raw.parts:
        raise ValueError("capture path must not contain '..'")
    if explicit_fmt is not None and raw.suffix and raw.suffix.lower().lstrip(".") != fmt:
        raise ValueError(f"capture path suffix {raw.suffix!r} conflicts with format {fmt!r}")
    cur = Path("/") if raw.is_absolute() else Path.cwd()
    rel_parts = [p for p in raw.parts if p not in ("", "/")]
    for idx, part in enumerate(rel_parts):
        cur = cur / part
        if cur.is_symlink():
            raise ValueError(f"capture path must not traverse or target symlinks: {cur}")
        if idx < len(rel_parts) - 1 and cur.exists() and not cur.is_dir():
            raise NotADirectoryError(f"capture parent is not a directory: {cur}")
    if raw.exists():
        raise FileExistsError(f"refusing to overwrite existing file: {raw}")
    return raw


def _write_exclusive(dest: Path, data: bytes) -> None:
    o_dir = getattr(os, "O_DIRECTORY", 0)
    o_nofollow = getattr(os, "O_NOFOLLOW", 0)
    if dest.is_absolute():
        start = "/"
        dir_parts = [p for p in dest.parts[1:-1] if p not in ("", "/")]
    else:
        start = "."
        dir_parts = [p for p in dest.parts[:-1] if p not in ("", ".")]

    dfd = os.open(start, os.O_RDONLY | o_dir)
    try:
        for part in dir_parts:
            try:
                next_fd = os.open(part, os.O_RDONLY | o_dir | o_nofollow, dir_fd=dfd)
            except FileNotFoundError:
                try:
                    os.mkdir(part, 0o755, dir_fd=dfd)
                except FileExistsError:
                    pass
                next_fd = os.open(part, os.O_RDONLY | o_dir | o_nofollow, dir_fd=dfd)
            os.close(dfd)
            dfd = next_fd

        fd = os.open(dest.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | o_nofollow, 0o600, dir_fd=dfd)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
        except BaseException:
            try:
                os.unlink(dest.name, dir_fd=dfd)
            except OSError:
                pass
            raise
    finally:
        os.close(dfd)


def run_doctor(url: Optional[str] = None, timeout: float = 5.0) -> Dict[str, Any]:
    """Check browser server reachability, state file, loopback proxy hazards, datasets, and tabs."""
    eff_url = (url or _default_url()).rstrip("/")
    parsed = urllib.parse.urlparse(eff_url)
    host = (parsed.hostname or "").lower()
    proxy_vars = {
        k: os.environ[k]
        for k in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")
        if os.environ.get(k)
    }
    no_proxy_raw = os.environ.get("no_proxy") or os.environ.get("NO_PROXY") or ""
    no_proxy_tokens = {tok.strip().lower() for tok in no_proxy_raw.split(",") if tok.strip()}
    proxy_warnings: List[str] = []
    if host in ("127.0.0.1", "localhost", "::1") and proxy_vars:
        covered = "*" in no_proxy_tokens or host in no_proxy_tokens or ("localhost" in no_proxy_tokens and "127.0.0.1" in no_proxy_tokens)
        if not covered:
            proxy_warnings.append(
                f"proxy environment variable(s) {sorted(proxy_vars)} are set without covering {host!r}; "
                "loopback requests may be intercepted unless NO_PROXY covers localhost,127.0.0.1 or proxy env is unset"
            )

    warnings = list(proxy_warnings)
    srv = McpServer(url=eff_url, timeout=timeout)
    reachable = False
    health = None
    datasets = None
    pages = None
    error = None
    try:
        health = srv._request("GET", "/api/health", timeout=timeout)
        datasets = srv._request("GET", "/api/datasets", timeout=timeout)
        pages = srv._connected_pages()
        reachable = True
        if not pages:
            warnings.append("browser server is running, but 0 browser tabs are connected; open the page URL in a browser")
        elif len(pages) > 1:
            warnings.append(
                f"{len(pages)} browser tabs are connected ({[p['page'] for p in pages]}); "
                "use page=<id> or bind to a tab before mutating or reading selection"
            )
    except BrowserError as exc:
        error = str(exc)

    return _json_safe({
        "ok": reachable,
        "code": "OK" if reachable else "UNREACHABLE",
        "url": eff_url,
        "server_reachable": reachable,
        "state_file": {"path": str(STATE_FILE), "exists": STATE_FILE.exists()},
        "proxy_env_active": sorted(proxy_vars),
        "proxy_warnings": proxy_warnings,
        "warnings": warnings,
        "health": health,
        "datasets": datasets,
        "pages": pages,
        "error": error,
    })


def format_mcp_config(client_name: str, url: Optional[str] = None, timeout: Optional[float] = None) -> str:
    """Render an MCP client configuration snippet pointing to the current Python executable."""
    py_exe = os.path.abspath(sys.executable)
    cmd_args = ["-m", "uchrom_browser.mcp"]
    if url is not None:
        cmd_args.extend(["--url", url])
    if timeout is not None:
        cmd_args.extend(["--timeout", str(timeout)])

    if client_name in ("claude", "claude-code", "cursor"):
        cfg = {
            "mcpServers": {
                "uchrom-browser": {
                    "command": py_exe,
                    "args": cmd_args,
                }
            }
        }
        return json.dumps(cfg, indent=2)
    if client_name == "codex":
        lines = [
            "[mcp_servers.uchrom-browser]",
            f"command = {json.dumps(py_exe)}",
            f"args = {json.dumps(cmd_args)}",
        ]
        return "\n".join(lines)
    raise ValueError(f"unsupported client target: {client_name!r}")


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
        sock_timeout = (float(effective_timeout) + 2.0) if path == "/api/control/actions" else max(0.001, float(effective_timeout))
        try:
            with urllib.request.urlopen(req, timeout=sock_timeout) as resp:
                raw = resp.read()
        except TimeoutError:
            raise NoPageConnectedError(f"request to {path} timed out after {effective_timeout:g}s") from None
        except urllib.error.HTTPError as exc:
            detail: Any = exc.reason
            try:
                err_raw = exc.read()
                parsed_err = json.loads(err_raw) if err_raw else None
                if isinstance(parsed_err, dict):
                    detail = parsed_err.get("detail", exc.reason)
            except (ValueError, http.client.IncompleteRead, OSError):
                pass
            msg = f"{exc.code}: {detail}"
            if exc.code == 504:
                raise NoPageConnectedError(msg) from None
            if exc.code == 409:
                if isinstance(body, dict) and body.get("page") is not None:
                    connected: List[str] = []
                    try:
                        connected = [p["page"] for p in self._connected_pages(timeout=min(float(effective_timeout), 1.0))]
                    except BrowserError:
                        pass
                    listed = ", ".join(connected) if connected else "none"
                    raise PageConflictError(
                        f"browser page {body['page']!r} is no longer connected (connected pages: {listed})",
                        connected,
                    ) from None
                raise NoPageConnectedError(msg) from None
            raise ActionExecutionError(msg) from None
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), TimeoutError):
                raise NoPageConnectedError(f"request to {path} timed out after {effective_timeout:g}s") from None
            raise ServerUnreachableError(
                f"cannot reach the browser server at {self.url} ({exc.reason}); "
                "start it with `python -m uchrom_browser data.chromdata.zarr`"
            ) from None
        except (http.client.HTTPException, OSError) as exc:
            raise ServerUnreachableError(f"connection error reading {path} from {self.url}: {exc}") from None

        try:
            return json.loads(raw or b"null")
        except ValueError as exc:
            raise ActionExecutionError(f"invalid JSON response from {path}: {exc}") from None

    @staticmethod
    def _extract_action_result(resp: Any, action: str) -> Any:
        if not isinstance(resp, dict) or "result" not in resp:
            raise ActionExecutionError(f"malformed response for action {action!r}")
        return resp["result"]

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
    def _connected_pages(self, timeout: Optional[float] = None) -> List[Dict[str, Any]]:
        pages = self._request("GET", "/api/control/pages", timeout=timeout)
        if not isinstance(pages, list):
            raise ActionExecutionError("unexpected response from /api/control/pages")
        return pages

    def _resolve_page(self, explicit_page: Optional[str]) -> str:
        connected = [p["page"] for p in self._connected_pages()]
        listed = ", ".join(connected) if connected else "none"
        if explicit_page is not None:
            if explicit_page not in connected:
                raise PageConflictError(
                    f"browser page {explicit_page!r} is not connected; connected pages: {listed}",
                    connected,
                )
            return explicit_page
        if self.bound_page is not None:
            if self.bound_page not in connected:
                raise PageConflictError(
                    f"bound browser page {self.bound_page!r} is no longer connected "
                    f"(connected pages: {listed}); call uchrom_bind_page to rebind or unbind",
                    connected,
                )
            return self.bound_page
        if not connected:
            raise NoPageConnectedError(
                "no browser page is connected; open the browser (python -m uchrom_browser ...)"
            )
        if len(connected) == 1:
            return connected[0]
        raise PageConflictError(
            f"multiple browser pages are connected ({listed}); pass 'page' or call uchrom_bind_page",
            connected,
        )

    def wait_for_page(self, page: Optional[str] = None, wait_seconds: float = 10.0) -> Dict[str, Any]:
        if isinstance(wait_seconds, bool) or not isinstance(wait_seconds, (int, float)) or not math.isfinite(float(wait_seconds)):
            raise ValueError("wait_seconds must be a finite number")
        secs = float(wait_seconds)
        if secs < 0 or secs > 60:
            raise ValueError("wait_seconds must be between 0 and 60")
        target_id = page if page is not None else self.bound_page
        deadline = time.monotonic() + secs
        attempt = 0
        while True:
            rem = deadline - time.monotonic()
            if attempt > 0 and rem <= 0:
                target_desc = f"page {target_id!r}" if target_id is not None else "any browser page"
                raise NoPageConnectedError(f"timed out after {secs:g}s waiting for {target_desc} to connect")
            poll_timeout = min(2.0, rem) if (secs > 0 and rem > 0) else min(0.05, float(self.timeout))
            attempt += 1
            pages: Optional[List[Dict[str, Any]]] = None
            try:
                pages = self._connected_pages(timeout=poll_timeout)
            except (ServerUnreachableError, NoPageConnectedError):
                pass
            if pages is not None:
                connected = [p["page"] for p in pages]
                if target_id is not None:
                    if target_id in connected:
                        return {"pages": pages, "bound_page": self.bound_page}
                elif connected:
                    return {"pages": pages, "bound_page": self.bound_page}
            rem_sleep = deadline - time.monotonic()
            if rem_sleep <= 0:
                target_desc = f"page {target_id!r}" if target_id is not None else "any browser page"
                raise NoPageConnectedError(f"timed out after {secs:g}s waiting for {target_desc} to connect")
            time.sleep(min(0.2, rem_sleep))

    def _summarize_pages(self, pages: List[Dict[str, Any]], *, probe: bool = True) -> List[Dict[str, Any]]:
        out = [dict(p) for p in pages]
        if not probe:
            return out
        probe_timeout = min(self.timeout, 1.5)
        for idx, p in enumerate(out):
            if idx >= 8:
                p["summary"] = None
                continue
            pid = p.get("page")
            if not isinstance(pid, str):
                p["summary"] = None
                continue
            try:
                resp = self._request(
                    "POST",
                    "/api/control/actions",
                    {"name": "describe_workspace", "args": {}, "timeout": probe_timeout, "page": pid},
                    timeout=probe_timeout,
                )
                res = resp.get("result") if isinstance(resp, dict) else None
                if isinstance(res, dict) and isinstance(res.get("dataset"), dict):
                    ds = res["dataset"]
                    views = res.get("views")
                    p["summary"] = {
                        "dataset": ds.get("name"),
                        "dataset_id": ds.get("id"),
                        "path": ds.get("path"),
                        "layout": res.get("layout"),
                        "active_view": res.get("active_view"),
                        "n_views": len(views) if isinstance(views, list) else None,
                        "selection": res.get("selection"),
                        "focus": res.get("focus"),
                        "locus": res.get("locus"),
                    }
                else:
                    p["summary"] = None
            except ActionExecutionError as exc:
                p["summary"] = {"dataset": None} if "no dataset is open" in str(exc).lower() else None
            except BrowserError:
                p["summary"] = None
        return out

    @staticmethod
    def _capture_path_key(dest: Path) -> tuple[tuple[int, int], tuple[str, ...]]:
        cur = Path(os.path.abspath(str(dest)))
        rel_rev: List[str] = []
        while not cur.exists():
            parent = cur.parent
            if parent == cur:
                break
            rel_rev.append(cur.name)
            cur = parent
        st = os.stat(cur)
        anc_key = (st.st_dev, st.st_ino)
        case_insensitive = False
        probe = cur
        while probe.parent != probe:
            alt_name = probe.name.swapcase()
            if alt_name != probe.name:
                alt = probe.parent / alt_name
                if alt.exists() and os.path.samefile(probe, alt):
                    case_insensitive = True
                break
            probe = probe.parent
        rel_parts = tuple(p.casefold() if case_insensitive else p for p in reversed(rel_rev))
        return anc_key, rel_parts

    def execute_batch(self, steps: List[Any], explicit_page: Optional[str] = None) -> Dict[str, Any]:
        if not isinstance(steps, list) or not (1 <= len(steps) <= 20):
            raise ValueError("batch 'steps' must be an array containing between 1 and 20 steps")

        raw_tools = {t["name"]: t for t in self._load_ui_tools()}
        cap_schema: Optional[Dict[str, Any]] = None
        if "capture_view" in raw_tools:
            cap_schema = copy.deepcopy(raw_tools["capture_view"]["inputSchema"])
            cap_schema.setdefault("properties", {})["path"] = {"type": "string"}

        validated: List[tuple[str, Dict[str, Any]]] = []
        seen_capture_paths: set[tuple[tuple[int, int], tuple[str, ...]]] = set()
        for idx, raw_step in enumerate(steps):
            if not isinstance(raw_step, dict):
                raise ValueError(f"step[{idx}]: must be an object with 'action' and optional 'args'")
            unknown_keys = set(raw_step) - {"action", "args"}
            if unknown_keys:
                raise ValueError(f"step[{idx}]: unknown step key(s): {', '.join(sorted(unknown_keys))}")
            raw_action = raw_step.get("action")
            if not isinstance(raw_action, str) or not raw_action.strip():
                raise ValueError(f"step[{idx}]: must include non-empty string 'action'")
            act = raw_action.removeprefix("uchrom_")
            if act not in raw_tools:
                raise ValueError(f"step[{idx}]: unknown or unsupported batch action {raw_action!r}")

            raw_args = raw_step.get("args")
            if raw_args is None:
                sargs: Dict[str, Any] = {}
            elif isinstance(raw_args, dict):
                sargs = dict(raw_args)
            else:
                raise ValueError(f"step[{idx}]: 'args' must be an object")
            if "page" in sargs:
                raise ValueError(f"step[{idx}]: per-step 'page' is not allowed; pass 'page' on the batch itself")

            schema = cap_schema if (act == "capture_view" and cap_schema is not None) else raw_tools[act]["inputSchema"]
            err = _validate_arguments(schema, sargs)
            if err is not None:
                raise ValueError(f"step[{idx}] ({act}): {err}")

            if act == "capture_view" and sargs.get("path") is not None:
                explicit_fmt = sargs.get("format")
                fmt = _capture_format(explicit_fmt, sargs["path"])
                dest = _resolve_capture_dest(sargs["path"], explicit_fmt, fmt)
                anc_key, rel_parts = self._capture_path_key(dest)
                for prev_anc, prev_parts in seen_capture_paths:
                    n_min = min(len(rel_parts), len(prev_parts))
                    if anc_key == prev_anc and rel_parts[:n_min] == prev_parts[:n_min]:
                        raise ValueError(
                            f"step[{idx}] (capture_view): capture path {sargs['path']!r} conflicts with earlier batch capture path"
                        )
                seen_capture_paths.add((anc_key, rel_parts))

            validated.append((act, sargs))

        target_page = self._resolve_page(explicit_page)
        results: List[Dict[str, Any]] = []
        for idx, (act, sargs) in enumerate(validated):
            try:
                if act == "capture_view":
                    res = self._handle_capture_view({**sargs, "page": target_page}, resolved_page=target_page)
                else:
                    cleaned = {k: v for k, v in sargs.items() if v is not None}
                    resp = self._request(
                        "POST",
                        "/api/control/actions",
                        {"name": act, "args": cleaned, "timeout": self.timeout, "page": target_page},
                    )
                    res = self._extract_action_result(resp, act)
                results.append({"step": idx, "action": act, "result": res})
            except (BrowserError, ValueError, OSError) as exc:
                raise BatchStepError(exc, target_page, idx, act, results) from None
        return {"page": target_page, "completed": len(results), "results": results}

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
                probe = True if arguments.get("probe") is None else bool(arguments["probe"])
                pages = self._summarize_pages(self._connected_pages(), probe=probe)
                datasets = self._request("GET", "/api/datasets")
                return _tool_ok({"pages": pages, "datasets": datasets, "bound_page": self.bound_page})

            if name == "uchrom_bind_page":
                page = arguments.get("page")
                pages = self._connected_pages()
                if page is None or page == "":
                    self.bound_page = None
                    return _tool_ok({"bound_page": None, "pages": pages})
                connected = [p["page"] for p in pages]
                if page not in connected:
                    listed = ", ".join(connected) if connected else "none"
                    raise PageConflictError(
                        f"cannot bind unknown browser page {page!r}; connected pages: {listed}",
                        connected,
                    )
                self.bound_page = page
                return _tool_ok({"bound_page": page, "pages": pages})

            if name == "uchrom_wait_for_page":
                wait_seconds = 10.0 if arguments.get("wait_seconds") is None else arguments["wait_seconds"]
                return _tool_ok(self.wait_for_page(page=arguments.get("page"), wait_seconds=wait_seconds))

            if name == "uchrom_batch":
                return _tool_ok(self.execute_batch(arguments["steps"], explicit_page=arguments.get("page")))

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
            result = self._extract_action_result(resp, action)
            if isinstance(result, dict):
                out = {**result, "page": target_page}
            else:
                out = {"result": result, "page": target_page}
            return _tool_ok(out)
        except BatchStepError as exc:
            err_payload: Dict[str, Any] = {
                "page": exc.page,
                "completed": len(exc.results),
                "results": exc.results,
                "failed_step": exc.step_index,
                "failed_action": exc.action,
                "error": str(exc.cause),
            }
            if isinstance(exc.cause, PageConflictError):
                err_payload["connected_pages"] = exc.cause.connected_pages
                err_payload["bound_page"] = self.bound_page
            payload = _json_safe(err_payload)
            return {
                "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, allow_nan=False)}],
                "structuredContent": payload,
                "isError": True,
            }
        except (BrowserError, ValueError, OSError) as exc:
            return _tool_err(str(exc))

    def _handle_capture_view(self, arguments: Dict[str, Any], *, resolved_page: Optional[str] = None) -> Dict[str, Any]:
        target_page = resolved_page if resolved_page is not None else self._resolve_page(arguments.get("page"))
        pane = arguments.get("pane")
        out_path = arguments.get("path")
        explicit_fmt = arguments.get("format")
        fmt = _capture_format(explicit_fmt, out_path)
        dest: Optional[Path] = _resolve_capture_dest(out_path, explicit_fmt, fmt) if out_path is not None else None
        action_args: Dict[str, Any] = {"format": fmt}
        if pane is not None:
            action_args["pane"] = pane
        resp = self._request(
            "POST",
            "/api/control/actions",
            {"name": "capture_view", "args": action_args, "timeout": self.timeout, "page": target_page},
        )
        result = self._extract_action_result(resp, "capture_view")
        if not isinstance(result, dict):
            raise ActionExecutionError("capture_view returned malformed result")
        b64 = result.get("data_base64") or result.get("png_base64")
        if not isinstance(b64, str) or not b64:
            raise ActionExecutionError("capture_view did not return valid base64 image data")
        try:
            data = base64.b64decode(b64, validate=True)
        except (ValueError, TypeError) as exc:
            raise ActionExecutionError(f"capture_view returned malformed base64 image data: {exc}") from None
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

    # -- resources & prompts ----------------------------------------------
    def _read_resource(self, uri: str, explicit_page: Optional[str] = None) -> Dict[str, Any]:
        if uri == "uchrom://status":
            try:
                payload = {
                    "url": self.url,
                    "health": self._request("GET", "/api/health"),
                    "datasets": self._request("GET", "/api/datasets"),
                    "pages": self._connected_pages(),
                    "bound_page": self.bound_page,
                }
            except BrowserError as exc:
                raise _RpcError(-32002, str(exc)) from None
        elif uri == "uchrom://pages":
            try:
                payload = {
                    "pages": self._summarize_pages(self._connected_pages(), probe=True),
                    "datasets": self._request("GET", "/api/datasets"),
                    "bound_page": self.bound_page,
                }
            except BrowserError as exc:
                raise _RpcError(-32002, str(exc)) from None
        elif uri in ("uchrom://workspace", "uchrom://selection"):
            action = "describe_workspace" if uri == "uchrom://workspace" else "get_selection"
            try:
                target_page = self._resolve_page(explicit_page)
                resp = self._request(
                    "POST",
                    "/api/control/actions",
                    {"name": action, "args": {}, "timeout": self.timeout, "page": target_page},
                )
                result = self._extract_action_result(resp, action)
                payload = {**result, "page": target_page} if isinstance(result, dict) else {"result": result, "page": target_page}
            except BrowserError as exc:
                raise _RpcError(-32002, str(exc)) from None
        else:
            raise _RpcError(-32602, f"Unknown resource URI: {uri}")

        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(_json_safe(payload), ensure_ascii=False, allow_nan=False),
                }
            ]
        }

    def _get_prompt(self, name: str, raw_args: Dict[str, Any]) -> Dict[str, Any]:
        prompts = {p["name"]: p for p in _PROMPTS}
        spec = prompts.get(name)
        if spec is None:
            raise _RpcError(-32602, f"Unknown prompt: {name}")
        args: Dict[str, str] = {}
        for k, v in raw_args.items():
            if v is not None and not isinstance(v, str):
                raise _RpcError(-32602, f"prompt argument {k!r} must be a string")
            if isinstance(v, str):
                args[k] = v
        for arg_spec in spec.get("arguments", []):
            if arg_spec.get("required") and not args.get(arg_spec["name"], "").strip():
                raise _RpcError(-32602, f"missing required prompt argument: {arg_spec['name']}")

        if name == "compare-selection":
            against = args.get("against") or "rest"
            stat = args.get("stat") or "rg"
            chrom = args.get("chrom")
            scope = f" on {chrom}" if chrom else ""
            text = (
                "1. Inspect the researcher's browser selection via `uchrom_get_selection` and workspace via `uchrom_describe_workspace` (check `pages` / `bound_page` first).\n"
                f"2. Run the statistical comparison in Python/skills (`compare-groups`) comparing the selected cells vs `{against}` for `{stat}`{scope}, keeping cell as the statistical unit and checking confounders/depth.\n"
                "3. Show matching views in the browser via `uchrom_select_cells`, `uchrom_set_locus` (if windowed), and `uchrom_open_view(type='stats', ...)` / `uchrom_open_view(type='genome', ...)`, then report pane IDs alongside exact test statistics."
            )
            return {
                "description": spec["description"],
                "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
            }

        chrom = args["chrom"].strip()
        raw_start = args.get("start")
        raw_end = args.get("end")
        start_val: Optional[int] = None
        end_val: Optional[int] = None
        if raw_start is not None and raw_start.strip():
            try:
                start_val = int(raw_start.strip())
            except ValueError:
                raise _RpcError(-32602, f"prompt argument 'start' must be an integer, got {raw_start!r}") from None
            if start_val < 0:
                raise _RpcError(-32602, f"prompt argument 'start' must be >= 0, got {start_val}")
        if raw_end is not None and raw_end.strip():
            try:
                end_val = int(raw_end.strip())
            except ValueError:
                raise _RpcError(-32602, f"prompt argument 'end' must be an integer, got {raw_end!r}") from None
            if end_val < 0:
                raise _RpcError(-32602, f"prompt argument 'end' must be >= 0, got {end_val}")
        if start_val is not None and end_val is not None and end_val <= start_val:
            raise _RpcError(-32602, f"prompt argument 'end' ({end_val}) must be > 'start' ({start_val})")

        export_path = args.get("export_path")
        if start_val is not None and end_val is not None:
            locus_desc = f"{chrom}:{start_val}-{end_val}"
            locus_call = f"uchrom_set_locus(chrom={chrom!r}, start={start_val}, end={end_val})"
        elif start_val is not None:
            locus_desc = f"{chrom} from {start_val}"
            locus_call = f"uchrom_set_locus(chrom={chrom!r}, start={start_val})"
        elif end_val is not None:
            locus_desc = f"{chrom} up to {end_val}"
            locus_call = f"uchrom_set_locus(chrom={chrom!r}, end={end_val})"
        else:
            locus_desc = chrom
            locus_call = f"uchrom_set_locus(chrom={chrom!r})"
        export_step = (
            f"\n4. Export the active figure cleanly with `uchrom_capture_view(path={export_path!r})` (never overwrite an existing file)."
            if export_path
            else "\n4. If the user asks for a figure, capture it with `uchrom_capture_view` (PNG/SVG/PDF)."
        )
        text = (
            f"1. Read `uchrom_describe_workspace` to discover loaded tracks, contact maps, and selected cells.\n"
            f"2. Focus the browser window on `{locus_desc}` with `{locus_call}`.\n"
            f"3. Open aligned Genome (`open_view(type='genome', ...)`), Matrix, or Stats (`chrom_scope='locus'` if chrom-specific) panes and arrange with `uchrom_arrange`."
            + export_step
        )
        return {
            "description": spec["description"],
            "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
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
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                    "prompts": {"listChanged": False},
                },
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

        if method == "resources/list":
            if params is not None and not isinstance(params, dict):
                raise _RpcError(-32602, "resources/list params must be an object")
            return {"resources": copy.deepcopy(_RESOURCES)}

        if method == "resources/read":
            if not isinstance(params, dict) or not isinstance(params.get("uri"), str):
                raise _RpcError(-32602, "resources/read params must include string 'uri'")
            page = params.get("page")
            if page is not None and not isinstance(page, str):
                raise _RpcError(-32602, "resources/read 'page' must be a string")
            return self._read_resource(params["uri"], explicit_page=page)

        if method == "prompts/list":
            if params is not None and not isinstance(params, dict):
                raise _RpcError(-32602, "prompts/list params must be an object")
            return {"prompts": copy.deepcopy(_PROMPTS)}

        if method == "prompts/get":
            if not isinstance(params, dict) or not isinstance(params.get("name"), str):
                raise _RpcError(-32602, "prompts/get params must include string 'name'")
            pargs = params.get("arguments")
            if pargs is None:
                pargs = {}
            elif not isinstance(pargs, dict):
                raise _RpcError(-32602, "prompts/get 'arguments' must be an object")
            return self._get_prompt(params["name"], pargs)

        raise _RpcError(-32601, f"Method not found: {method}")

    def handle_line(self, line: str, out: TextIO) -> None:
        if not line.strip():
            return
        try:
            msg = _json_loads_strict(line)
        except (json.JSONDecodeError, ValueError) as exc:
            self._write(out, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {exc}"}})
            return

        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
            self._write(out, {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}})
            return

        has_id = "id" in msg
        req_id = msg.get("id")
        if has_id and (
            isinstance(req_id, bool)
            or not (req_id is None or isinstance(req_id, (str, int)))
            or (isinstance(req_id, str) and len(req_id) > MAX_RPC_ID_LEN)
            or (isinstance(req_id, int) and not _in_safe_int_range(req_id))
        ):
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


def _cli(argv: Optional[List[str]] = None, *, prog: str = "uchrom-browser-mcp") -> None:
    """Run the stdio MCP server (or print config / run doctor)."""
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Stdio JSON-RPC 2.0 MCP server for a running U-Chrom browser.",
    )
    parser.add_argument("--url", default=None, help="Browser server URL (default: $UCHROM_BROWSER_URL, state file, or http://127.0.0.1:8765)")
    parser.add_argument("--timeout", type=float, default=None, help="Action timeout in seconds (default: 30; doctor default: 5)")
    parser.add_argument(
        "--print-config",
        choices=("claude", "claude-code", "codex", "cursor"),
        default=None,
        help="Print ready-to-paste MCP client configuration using the current Python executable and exit.",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Check browser server reachability, connected tabs, and proxy settings, print JSON, and exit.",
    )
    args = parser.parse_args(argv)
    if args.print_config is not None:
        print(format_mcp_config(args.print_config, url=args.url, timeout=args.timeout))
        return
    if args.doctor:
        report = run_doctor(url=args.url, timeout=5.0 if args.timeout is None else args.timeout)
        print(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False))
        raise SystemExit(0 if report["ok"] else 3)
    McpServer(url=args.url, timeout=30.0 if args.timeout is None else args.timeout).serve_stdio()


if __name__ == "__main__":
    _cli()
