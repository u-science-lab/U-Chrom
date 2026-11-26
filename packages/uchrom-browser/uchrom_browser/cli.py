"""Pure-stdlib Agent-friendly CLI (``uchrom-browser-ctl``) for controlling a running U-Chrom browser.

Shares URL discovery, JSON-schema validation, multi-tab page safety, and exclusive
(non-overwriting) capture file writes with :mod:`uchrom_browser.mcp`, outputting strict
JSON on ``stdout``/``stderr`` with semantic exit codes (0 ok, 2 invalid args/schema,
3 server/page unreachable, 4 tab conflict, 5 browser action or file write error).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None  # type: ignore[assignment]

from .client import BrowserError
from .mcp import (
    ActionExecutionError,
    BatchStepError,
    McpServer,
    NoPageConnectedError,
    PageConflictError,
    ServerUnreachableError,
    _json_loads_strict,
    _json_safe,
    _validate_arguments,
    run_doctor,
)

EXIT_OK = 0
EXIT_INVALID = 2
EXIT_UNREACHABLE = 3
EXIT_TAB_CONFLICT = 4
EXIT_ACTION_ERROR = 5

_LOCUS_RANGE_RE = re.compile(r"^([0-9][0-9,_]*)(?:-|\.\.)([0-9][0-9,_]*)$")


class _CliUsageError(Exception):
    """Raised on CLI argument / input validation failures (exit code 2)."""


class _JsonArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors cleanly to our structured JSON handler."""

    def error(self, message: str) -> None:  # noqa: D401
        raise _CliUsageError(message)


def _ctl_state_path() -> Path:
    override = os.environ.get("UCHROM_BROWSER_CTL_STATE")
    if override:
        return Path(override)
    cache_root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return cache_root / "uchrom" / "browser_ctl.json"


def _load_bindings(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    if path.is_symlink():
        raise OSError(f"control state file must not be a symlink: {path}")
    data = _json_loads_strict(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("bindings"), dict):
        return {str(k): str(v) for k, v in data["bindings"].items() if isinstance(v, str)}
    return {}


def _update_binding_locked(state_path: Path, url: str, target_page: Optional[str]) -> Dict[str, str]:
    if state_path.parent.is_symlink() or state_path.is_symlink():
        raise OSError(f"control state path must not be a symlink: {state_path}")
    if os.environ.get("UCHROM_BROWSER_CTL_STATE"):
        state_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        state_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    o_nofollow = getattr(os, "O_NOFOLLOW", 0)
    lock_path = state_path.with_name(f".{state_path.name}.lock")
    if lock_path.is_symlink():
        raise OSError(f"control state lock path must not be a symlink: {lock_path}")
    lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR | o_nofollow, 0o600)
    try:
        if fcntl is not None:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
        bindings = _load_bindings(state_path)
        if target_page is None:
            bindings.pop(url, None)
        else:
            bindings[url] = target_page
        payload = json.dumps({"bindings": bindings}, indent=2, ensure_ascii=False, allow_nan=False).encode("utf-8")
        tmp_path = state_path.with_name(f".{state_path.name}.tmp.{os.getpid()}")
        fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | o_nofollow, 0o600)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(payload)
            os.replace(tmp_path, state_path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
        return bindings
    finally:
        if fcntl is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(lock_fd)


def _emit_json(stream: Any, payload: Any, *, pretty: bool = False) -> None:
    clean = _json_safe(payload)
    indent = 2 if pretty else None
    stream.write(json.dumps(clean, indent=indent, ensure_ascii=False, allow_nan=False) + "\n")
    stream.flush()


def _fail(
    code_name: str,
    message: str,
    exit_code: int,
    *,
    pretty: bool = False,
    extra: Optional[Dict[str, Any]] = None,
) -> int:
    body: Dict[str, Any] = {"ok": False, "code": code_name, "error": message}
    if extra:
        body.update(extra)
    _emit_json(sys.stderr, body, pretty=pretty)
    return exit_code


def _parse_int_token(raw: str, label: str) -> int:
    cleaned = raw.replace(",", "").replace("_", "").strip()
    if not cleaned or not cleaned.isdigit():
        raise _CliUsageError(f"invalid {label} coordinate: {raw!r}")
    return int(cleaned)


def _parse_locus(target: str, start: Optional[int], end: Optional[int]) -> Dict[str, Any]:
    raw = target.strip()
    if not raw or raw == "*":
        raise _CliUsageError("chrom must be non-empty and not '*'")
    if ":" in raw:
        if start is not None or end is not None:
            raise _CliUsageError("pass either chrom:start-end or --start/--end, not both")
        chrom, span = raw.split(":", 1)
        chrom = chrom.strip()
        if not chrom or chrom == "*":
            raise _CliUsageError("chrom must be non-empty and not '*'")
        m = _LOCUS_RANGE_RE.match(span.strip())
        if not m:
            raise _CliUsageError(f"invalid locus interval {span!r}; expected start-end or start..end")
        s_val = _parse_int_token(m.group(1), "start")
        e_val = _parse_int_token(m.group(2), "end")
        if e_val <= s_val:
            raise _CliUsageError(f"locus end ({e_val}) must be > start ({s_val})")
        return {"chrom": chrom, "start": s_val, "end": e_val}

    out: Dict[str, Any] = {"chrom": raw}
    if start is not None:
        if start < 0:
            raise _CliUsageError(f"start ({start}) must be >= 0")
        out["start"] = start
    if end is not None:
        if end < 0:
            raise _CliUsageError(f"end ({end}) must be >= 0")
        if start is not None and end <= start:
            raise _CliUsageError(f"end ({end}) must be > start ({start})")
        out["end"] = end
    return out


def _read_cells(cells_csv: Optional[str], cells_file: Optional[str]) -> List[str]:
    out: List[str] = []
    if cells_csv is not None:
        out.extend(part.strip() for part in cells_csv.split(",") if part.strip())
    if cells_file is not None:
        lines = Path(cells_file).read_text(encoding="utf-8").splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                out.append(stripped)
    if not out:
        raise _CliUsageError("at least one cell id must be provided via --cells or --cells-file")
    return out


def _build_parser() -> _JsonArgumentParser:
    common = _JsonArgumentParser(add_help=False)
    common.add_argument("--url", default=argparse.SUPPRESS, help="Browser server URL (default: $UCHROM_BROWSER_URL, state file, or http://127.0.0.1:8765)")
    common.add_argument("--page", default=argparse.SUPPRESS, help="Target connected browser page id (overrides persisted binding for this command)")
    common.add_argument("--timeout", type=float, default=argparse.SUPPRESS, help="Action timeout in seconds (default: 30)")
    common.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS, help="Pretty-print JSON output")

    parser = _JsonArgumentParser(
        prog="uchrom-browser-ctl",
        parents=[common],
        description="Control a running U-Chrom browser from the shell using structured JSON.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", parents=[common], help="Check server health, loaded datasets, connected tabs, and bound tab")
    sub.add_parser("doctor", parents=[common], help="Diagnose server reachability, proxy hazards, state files, and connected tabs")
    p_pages = sub.add_parser("pages", parents=[common], help="List connected browser tabs, workspace summaries, and current binding")
    p_pages.add_argument("--no-probe", action="store_true", help="Skip querying describe_workspace on each connected tab")

    p_bind = sub.add_parser("bind", parents=[common], help="Bind this CLI session for the current URL to a tab (or clear binding)")
    p_bind.add_argument("target_page", nargs="?", default=None, help="Connected page id to bind")
    p_bind.add_argument("--clear", action="store_true", help="Clear persisted page binding")

    p_wait = sub.add_parser("wait", parents=[common], help="Wait for a browser tab (or specific --page) to connect")
    p_wait.add_argument("--wait-seconds", type=float, default=10.0, help="Maximum seconds to wait (0-60, default: 10)")

    p_tools = sub.add_parser("tools", parents=[common], help="List available browser actions (or show full JSON schema with --schema)")
    p_tools.add_argument("--schema", default=None, help="Action name to inspect full inputSchema (e.g. open_view)")

    sub.add_parser("describe", parents=[common], help="Describe active dataset, open panes, focus, and selection")
    sub.add_parser("selection", parents=[common], help="Get currently lassoed or focused cell IDs")
    sub.add_parser("groups", parents=[common], help="List automatic and saved cell groups")

    p_sel = sub.add_parser("select", parents=[common], help="Select/focus cells and optionally save them as a named group")
    p_sel.add_argument("--cells", default=None, help="Comma-separated cell IDs")
    p_sel.add_argument("--cells-file", default=None, help="File with one cell ID per line")
    p_sel.add_argument("--name", default=None, help="Optional group name to save")

    p_focus = sub.add_parser("focus", parents=[common], help="Focus one cell or group (or --clear to release focus)")
    p_focus.add_argument("--cell", default=None, help="Cell ID to focus")
    p_focus.add_argument("--group", default=None, help="Group reference to focus")
    p_focus.add_argument("--clear", action="store_true", help="Clear focus (return to all cells)")

    p_locus = sub.add_parser("locus", parents=[common], help="Set shared genomic locus (chrom or chrom:start-end)")
    p_locus.add_argument("target", help="Chromosome or interval such as chr15:3000000-33000000")
    p_locus.add_argument("--start", type=int, default=None, help="Optional start coordinate in bp")
    p_locus.add_argument("--end", type=int, default=None, help="Optional end coordinate in bp")

    p_open = sub.add_parser("open", parents=[common], help="Open a new view pane")
    p_open.add_argument("view_type", choices=("3d", "spatial", "embedding", "genome", "matrix", "stats"), help="View type")
    p_open.add_argument("--cells", default=None, help="Cell scope ('focus', 'all', cell id, or group ref)")
    p_open.add_argument("--stats", choices=("rg", "scaling", "hist", "scatter"), default=None, help="Stats view sub-type")
    p_open.add_argument("--chrom-scope", choices=("all", "locus"), default=None, help="Stats chromosome scope")
    p_open.add_argument("--compare", default=None, help="Comma-separated group refs for stats compare_groups")
    p_open.add_argument("--field-x", default=None, help="X cell field for hist/scatter stats")
    p_open.add_argument("--field-y", default=None, help="Y cell field for scatter stats")
    p_open.add_argument("--embedding", default=None, help="Embedding key for embedding view")
    p_open.add_argument("--source", default=None, help="Contact map key or 'distance' for matrix view")
    p_open.add_argument("--spatial", default=None, help="Cell-position set key for spatial view")
    p_open.add_argument("--region", default=None, help="Spatial section/region")
    p_open.add_argument("--image-opacity", type=float, default=None, help="Spatial background image opacity (0-1)")
    p_open.add_argument("--rows-json", default=None, help="JSON array of row specs for genome view")

    p_show = sub.add_parser("show", parents=[common], help="Make a pane active")
    p_show.add_argument("pane", help="Pane id")

    p_close = sub.add_parser("close", parents=[common], help="Close a pane")
    p_close.add_argument("pane", help="Pane id")

    p_arr = sub.add_parser("arrange", parents=[common], help="Arrange open panes as grid or tabs")
    p_arr.add_argument("layout", choices=("grid", "tabs"), help="Workspace layout")

    p_col = sub.add_parser("color-by", parents=[common], help="Color all cells by a cell field")
    p_col.add_argument("field", help="Cell column name (e.g. cell_type, rna.Nanog, if.H3K9me3)")

    p_cap = sub.add_parser("capture", parents=[common], help="Render a pane to PNG, SVG, or PDF and return its file path")
    p_cap.add_argument("--pane", default=None, help="Pane id (default: active pane)")
    p_cap.add_argument("--out", default=None, help="Non-existing output file path (PNG/SVG/PDF; default: private temp file)")
    p_cap.add_argument("--format", choices=("png", "svg", "pdf"), default=None, help="Output format override")

    p_call = sub.add_parser("call", parents=[common], help="Invoke any action from ui_tools.json by name")
    p_call.add_argument("action", help="Action name (e.g. open_view or uchrom_open_view)")
    p_call.add_argument("--json", dest="json_args", default="{}", help="JSON object of action arguments")

    p_batch = sub.add_parser("batch", parents=[common], help="Validate and run 1..20 browser UI actions sequentially on one tab")
    g_batch = p_batch.add_mutually_exclusive_group(required=True)
    g_batch.add_argument("--steps-json", default=None, help="JSON array of {action, args?} step objects")
    g_batch.add_argument("--steps-file", default=None, help="Path to a JSON file containing an array of {action, args?} step objects")

    return parser


def _execute_action(srv: McpServer, action: str, arguments: Dict[str, Any], explicit_page: Optional[str]) -> Dict[str, Any]:
    raw_tools = {t["name"]: t for t in srv._load_ui_tools()}
    if action not in raw_tools:
        raise _CliUsageError(f"unknown action {action!r}; run `tools` to list available actions")
    err = _validate_arguments(raw_tools[action]["inputSchema"], arguments)
    if err is not None:
        raise _CliUsageError(err)

    target_page = srv._resolve_page(explicit_page)
    cleaned = {k: v for k, v in arguments.items() if v is not None}
    resp = srv._request(
        "POST",
        "/api/control/actions",
        {"name": action, "args": cleaned, "timeout": srv.timeout, "page": target_page},
    )
    result = resp["result"]
    if isinstance(result, dict):
        return {**result, "page": target_page}
    return {"result": result, "page": target_page}


def _dispatch(args: argparse.Namespace, srv: McpServer, state_path: Path, bindings: Dict[str, str]) -> Tuple[Dict[str, Any], int]:
    cmd = args.command
    explicit_page = getattr(args, "page", None)

    if cmd == "doctor":
        rep = run_doctor(url=srv.url, timeout=min(srv.timeout, 5.0))
        rep["ctl_state_file"] = {"path": str(state_path), "exists": state_path.exists()}
        rep["bound_page"] = srv.bound_page
        return rep, (EXIT_OK if rep["ok"] else EXIT_UNREACHABLE)

    if cmd == "status":
        health = srv._request("GET", "/api/health")
        datasets = srv._request("GET", "/api/datasets")
        pages = srv._connected_pages()
        return {
            "url": srv.url,
            "health": health,
            "datasets": datasets,
            "pages": pages,
            "bound_page": srv.bound_page,
        }, EXIT_OK

    if cmd == "pages":
        pages = srv._summarize_pages(srv._connected_pages(), probe=not args.no_probe)
        datasets = srv._request("GET", "/api/datasets")
        return {"pages": pages, "datasets": datasets, "bound_page": srv.bound_page}, EXIT_OK

    if cmd == "bind":
        if args.clear and args.target_page is not None:
            raise _CliUsageError("pass either a page id or --clear, not both")
        pages = srv._connected_pages()
        if args.clear or args.target_page in (None, ""):
            _update_binding_locked(state_path, srv.url, None)
            srv.bound_page = None
            return {"bound_page": None, "pages": pages, "state_file": str(state_path)}, EXIT_OK
        connected = [p["page"] for p in pages]
        if args.target_page not in connected:
            listed = ", ".join(connected) if connected else "none"
            raise PageConflictError(
                f"cannot bind unknown browser page {args.target_page!r}; connected pages: {listed}",
                connected,
            )
        _update_binding_locked(state_path, srv.url, args.target_page)
        srv.bound_page = args.target_page
        return {"bound_page": args.target_page, "pages": pages, "state_file": str(state_path)}, EXIT_OK

    if cmd == "wait":
        return srv.wait_for_page(page=explicit_page, wait_seconds=args.wait_seconds), EXIT_OK

    if cmd == "tools":
        raw_tools = srv._load_ui_tools()
        if args.schema is not None:
            target = args.schema.removeprefix("uchrom_")
            by_name = {t["name"]: t for t in raw_tools}
            if target not in by_name:
                raise _CliUsageError(f"unknown action schema {args.schema!r}")
            return by_name[target], EXIT_OK
        summary = [
            {
                "name": t["name"],
                "required": list(t["inputSchema"].get("required") or []),
                "description": t["description"],
            }
            for t in raw_tools
        ]
        return {"tools": summary}, EXIT_OK

    if cmd == "describe":
        return _execute_action(srv, "describe_workspace", {}, explicit_page), EXIT_OK
    if cmd == "selection":
        return _execute_action(srv, "get_selection", {}, explicit_page), EXIT_OK
    if cmd == "groups":
        return _execute_action(srv, "list_groups", {}, explicit_page), EXIT_OK

    if cmd == "select":
        cells = _read_cells(args.cells, args.cells_file)
        act_args: Dict[str, Any] = {"cells": cells}
        if args.name is not None:
            act_args["name"] = args.name
        return _execute_action(srv, "select_cells", act_args, explicit_page), EXIT_OK

    if cmd == "focus":
        if args.clear and (args.cell is not None or args.group is not None):
            raise _CliUsageError("--clear cannot be combined with --cell or --group")
        if args.cell is not None and args.group is not None:
            raise _CliUsageError("pass at most one of --cell or --group")
        act_args = {}
        if args.cell is not None:
            act_args["cell"] = args.cell
        if args.group is not None:
            act_args["group"] = args.group
        return _execute_action(srv, "focus", act_args, explicit_page), EXIT_OK

    if cmd == "locus":
        loc = _parse_locus(args.target, args.start, args.end)
        return _execute_action(srv, "set_locus", loc, explicit_page), EXIT_OK

    if cmd == "open":
        act_args: Dict[str, Any] = {"type": args.view_type}
        mapping = (
            ("cells", args.cells),
            ("stats", args.stats),
            ("chrom_scope", args.chrom_scope),
            ("field_x", args.field_x),
            ("field_y", args.field_y),
            ("embedding", args.embedding),
            ("source", args.source),
            ("spatial", args.spatial),
            ("region", args.region),
            ("image_opacity", args.image_opacity),
        )
        for key, val in mapping:
            if val is not None:
                act_args[key] = val
        if args.compare is not None:
            groups = [g.strip() for g in args.compare.split(",") if g.strip()]
            if not groups:
                raise _CliUsageError("--compare must contain at least one group reference")
            act_args["compare_groups"] = groups
        if args.rows_json is not None:
            try:
                rows = _json_loads_strict(args.rows_json)
            except (json.JSONDecodeError, ValueError) as exc:
                raise _CliUsageError(f"invalid --rows-json: {exc}") from None
            if not isinstance(rows, list):
                raise _CliUsageError("--rows-json must decode to a JSON array")
            act_args["rows"] = rows
        return _execute_action(srv, "open_view", act_args, explicit_page), EXIT_OK

    if cmd == "show":
        return _execute_action(srv, "show_view", {"pane": args.pane}, explicit_page), EXIT_OK
    if cmd == "close":
        return _execute_action(srv, "close_view", {"pane": args.pane}, explicit_page), EXIT_OK
    if cmd == "arrange":
        return _execute_action(srv, "arrange", {"layout": args.layout}, explicit_page), EXIT_OK
    if cmd == "color-by":
        return _execute_action(srv, "color_by", {"field": args.field}, explicit_page), EXIT_OK

    if cmd == "capture":
        cap_args: Dict[str, Any] = {}
        if explicit_page is not None:
            cap_args["page"] = explicit_page
        if args.pane is not None:
            cap_args["pane"] = args.pane
        if args.out is not None:
            cap_args["path"] = args.out
        if args.format is not None:
            cap_args["format"] = args.format
        return srv._handle_capture_view(cap_args), EXIT_OK

    if cmd == "call":
        action_name = args.action.removeprefix("uchrom_")
        try:
            raw_obj = _json_loads_strict(args.json_args)
        except (json.JSONDecodeError, ValueError) as exc:
            raise _CliUsageError(f"invalid --json payload: {exc}") from None
        if not isinstance(raw_obj, dict):
            raise _CliUsageError("--json must decode to a JSON object")
        call_page = raw_obj.pop("page", None)
        if call_page is not None and not isinstance(call_page, str):
            raise _CliUsageError("'page' inside --json must be a string")
        eff_page = explicit_page if explicit_page is not None else call_page
        if action_name == "capture_view":
            if eff_page is not None:
                raw_obj["page"] = eff_page
            raw_tools = {t["name"]: t for t in srv._load_ui_tools()}
            cap_schema = dict(raw_tools["capture_view"]["inputSchema"])
            cap_props = dict(cap_schema.get("properties") or {})
            cap_props["page"] = {"type": "string"}
            cap_props["path"] = {"type": "string"}
            cap_schema["properties"] = cap_props
            err = _validate_arguments(cap_schema, raw_obj)
            if err is not None:
                raise _CliUsageError(err)
            return srv._handle_capture_view(raw_obj), EXIT_OK
        return _execute_action(srv, action_name, raw_obj, eff_page), EXIT_OK

    if cmd == "batch":
        raw_text = args.steps_json if args.steps_json is not None else Path(args.steps_file).read_text(encoding="utf-8")
        try:
            steps = _json_loads_strict(raw_text)
        except (json.JSONDecodeError, ValueError) as exc:
            raise _CliUsageError(f"invalid batch JSON: {exc}") from None
        return srv.execute_batch(steps, explicit_page=explicit_page), EXIT_OK

    raise _CliUsageError(f"unknown command: {cmd}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    pretty = "--pretty" in (sys.argv[1:] if argv is None else argv)
    try:
        args = parser.parse_args(argv)
    except _CliUsageError as exc:
        return _fail("INVALID_ARGS", str(exc), EXIT_INVALID, pretty=pretty)

    pretty = bool(getattr(args, "pretty", False))
    timeout_val = float(getattr(args, "timeout", 30.0))
    import math
    if not math.isfinite(timeout_val) or timeout_val <= 0:
        return _fail("INVALID_ARGS", "--timeout must be a positive finite number", EXIT_INVALID, pretty=pretty)
    state_path = _ctl_state_path()
    try:
        bindings = _load_bindings(state_path)
    except (OSError, ValueError) as exc:
        return _fail("STATE_ERROR", str(exc), EXIT_ACTION_ERROR, pretty=pretty)

    srv = McpServer(url=getattr(args, "url", None), timeout=timeout_val)
    srv.bound_page = bindings.get(srv.url)

    try:
        payload, code = _dispatch(args, srv, state_path, bindings)
    except _CliUsageError as exc:
        return _fail("INVALID_ARGS", str(exc), EXIT_INVALID, pretty=pretty)
    except (ServerUnreachableError, NoPageConnectedError) as exc:
        return _fail("UNREACHABLE", str(exc), EXIT_UNREACHABLE, pretty=pretty)
    except PageConflictError as exc:
        return _fail(
            "PAGE_CONFLICT",
            str(exc),
            EXIT_TAB_CONFLICT,
            pretty=pretty,
            extra={"connected_pages": exc.connected_pages, "bound_page": srv.bound_page},
        )
    except BatchStepError as exc:
        if isinstance(exc.cause, (ServerUnreachableError, NoPageConnectedError)):
            code_name, code = "UNREACHABLE", EXIT_UNREACHABLE
        elif isinstance(exc.cause, PageConflictError):
            code_name, code = "PAGE_CONFLICT", EXIT_TAB_CONFLICT
        else:
            code_name, code = "ACTION_ERROR", EXIT_ACTION_ERROR
        return _fail(
            code_name,
            str(exc.cause),
            code,
            pretty=pretty,
            extra={
                "page": exc.page,
                "completed": len(exc.results),
                "results": exc.results,
                "failed_step": exc.step_index,
                "failed_action": exc.action,
            },
        )
    except (ActionExecutionError, BrowserError, OSError) as exc:
        return _fail("ACTION_ERROR", str(exc), EXIT_ACTION_ERROR, pretty=pretty)
    except ValueError as exc:
        return _fail("INVALID_ARGS", str(exc), EXIT_INVALID, pretty=pretty)

    _emit_json(sys.stdout, payload, pretty=pretty)
    return code


def _cli() -> None:
    """Entrypoint for ``uchrom-browser-ctl``."""
    raise SystemExit(main())


if __name__ == "__main__":
    _cli()
