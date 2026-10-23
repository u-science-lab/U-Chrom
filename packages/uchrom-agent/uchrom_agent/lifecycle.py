"""Local handoff validation and browser process lifecycle."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

_HANDOFF_REDEEM_URL = "https://uchrom-browser.u-science.org/api/agent/handoffs/redeem"
_ATLAS_ROOT = "https://uchrom-atlas-r2.u-science.org"
_CATALOG_URL = _ATLAS_ROOT + "/catalog.json"
_MAX_HANDOFF_BYTES = 1_048_576
_started: subprocess.Popen | None = None


def _state_file() -> Path:
    from uchrom_browser.client import STATE_FILE
    return STATE_FILE


def _read_handoff(value: str) -> dict[str, Any]:
    if not value or len(value) > 4096 or value.lstrip().startswith("{"):
        raise ValueError("provide a handoff token or a local handoff file path")
    candidate = Path(value).expanduser()
    try:
        local_file = candidate.is_file()
    except OSError:
        raise ValueError("provide a valid handoff token or local handoff file path") from None
    if local_file:
        with candidate.open("rb") as source:
            raw = source.read(_MAX_HANDOFF_BYTES + 1)
        if len(raw) > _MAX_HANDOFF_BYTES:
            raise ValueError("handoff file exceeds 1 MiB")
        payload = _object(json.loads(raw), {"dataset", "question", "page_state"}, "local handoff")
        dataset = _object(payload.get("dataset"), {"path"}, "local dataset")
        reference = _string(dataset.get("path"), "local dataset.path")
        if urlsplit(reference).scheme or reference.startswith("-"):
            raise ValueError("local dataset.path must be a local filesystem path")
        path = Path(reference).expanduser()
        if not path.is_absolute():
            path = candidate.parent / path
        payload["dataset"] = {"path": str(path.resolve())}
    else:
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", value):
            raise ValueError("a valid handoff token or local handoff file path is required")
        payload = _validate_redeemed(_redeem(value))
    if "question" in payload and (not isinstance(payload["question"], str) or len(payload["question"]) > 4000):
        raise ValueError("handoff question must be a string of at most 4000 characters")
    _handoff_actions(payload)
    return payload


def _object(value: Any, allowed: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError(f"{name} must be an object with only supported fields")
    return value


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or any(ord(char) < 32 for char in value):
        raise ValueError(f"{name} must be a non-empty string without control characters")
    return value


def _timestamp(value: Any, name: str) -> float:
    try:
        parsed = datetime.fromisoformat(_string(value, name).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.timestamp()
    except ValueError:
        raise ValueError(f"handoff {name} must be a timestamp with a timezone") from None


def _validate_redeemed(payload: Any) -> dict[str, Any]:
    payload = _object(payload, {"version", "issued_at", "expires_at", "dataset", "question", "page_state"}, "handoff")
    if type(payload.get("version")) is not int or payload["version"] != 1:
        raise ValueError("handoff version must be 1")
    issued = _timestamp(payload.get("issued_at"), "issued_at")
    expires = _timestamp(payload.get("expires_at"), "expires_at")
    if not issued <= time.time() < expires or not 0 < expires - issued <= 600:
        raise ValueError("handoff is expired or outside its ten-minute validity window")
    dataset = _object(payload.get("dataset"), {"id", "url", "version"}, "dataset")
    for field in ("id", "url", "version"):
        _string(dataset.get(field), f"dataset.{field}")
    request = urllib.request.Request(_CATALOG_URL, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.geturl() != _CATALOG_URL:
            raise ValueError("Atlas catalog redirected to an unsupported source")
        raw = response.read(_MAX_HANDOFF_BYTES + 1)
        if len(raw) > _MAX_HANDOFF_BYTES:
            raise ValueError("Atlas catalog exceeds 1 MiB")
        catalog = json.loads(raw)
        etag = response.headers.get("ETag", "")
    if not isinstance(catalog, dict) or not isinstance(catalog.get("datasets"), list):
        raise ValueError("Atlas catalog must contain datasets")
    version = catalog.get("updated") or etag.removeprefix("W/").strip('"') or str(catalog.get("version", "unknown"))
    entry = next((item for item in catalog["datasets"]
                  if isinstance(item, dict) and item.get("id") == dataset["id"]), {})
    path = entry.get("path")
    if (not isinstance(path, str) or re.search(r"%(?![0-9a-fA-F]{2})", path)
            or any(part in ("", ".", "..") for part in unquote(path).split("/"))
            or any(char in unquote(path) for char in "\\?#:")):
        raise ValueError("dataset ID is missing from the catalog or has an unsafe path")
    if dataset["url"] != _ATLAS_ROOT + "/" + path or dataset["version"] != version:
        raise ValueError("handoff dataset URL/version does not match the current Atlas catalog")
    return payload


def _redeem(token: str) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        raise ValueError("a valid handoff token is required")
    request = urllib.request.Request(_HANDOFF_REDEEM_URL,
                                    data=json.dumps({"token": token}).encode("utf-8"),
                                    headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.geturl() != _HANDOFF_REDEEM_URL:
                raise ValueError("handoff redemption redirected to an unsupported source")
            raw = response.read(_MAX_HANDOFF_BYTES + 1)
            if len(raw) > _MAX_HANDOFF_BYTES:
                raise ValueError("redeemed handoff payload exceeds 1 MiB")
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"handoff redemption failed ({exc.code})") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"handoff redemption failed ({exc.reason})") from None


def _same_dataset(summary: dict[str, Any], reference: str) -> bool:
    path = summary.get("path") if isinstance(summary, dict) else None
    if not isinstance(path, str):
        return False
    if path and path.rstrip("/") == reference.rstrip("/"):
        return True
    if urlsplit(path).scheme or urlsplit(reference).scheme:
        return False
    try:
        return bool(path and Path(path).expanduser().resolve() == Path(reference).expanduser().resolve())
    except (OSError, ValueError):
        return False


def _existing_workspace(connect):
    try:
        ws = connect()
        return ws, ws._request("GET", "/api/datasets")
    except Exception:
        return None, []


def _wait_for_server(process: subprocess.Popen, timeout: float = 45.0):
    from uchrom_browser import connect

    state_file = _state_file()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"local browser exited before becoming ready (exit {process.returncode})")
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            if state.get("pid") == process.pid:
                ws = connect(state["url"])
                health = ws._request("GET", "/api/health")
                if health.get("status") == "ok":
                    return ws
        except (OSError, ValueError, KeyError, RuntimeError):
            pass
        time.sleep(0.2)
    raise TimeoutError("local U-Chrom browser server did not become ready")


def _wait_for_page(ws, timeout: float = 60.0):
    deadline = time.monotonic() + timeout
    last_pages = []
    while time.monotonic() < deadline:
        last_pages = ws.agent_pages()
        if last_pages:
            return last_pages
        time.sleep(0.25)
    raise TimeoutError("local browser opened, but no WebUI page connected to the agent API")


def _handoff_actions(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    if "page_state" not in payload:
        return [], []
    state = payload["page_state"]
    state = _object(state, {"selection", "locus", "views", "layout", "focus", "workspace"}, "handoff page_state")
    actions: list[dict[str, Any]] = []
    warnings: list[str] = []
    selection = state.get("selection")
    cells = None
    if selection is not None:
        selection = _object(selection, {"cells", "source"}, "handoff selection")
        cells = selection.get("cells")
        if not isinstance(cells, list):
            raise ValueError("handoff selection.cells must be a list of non-empty cell IDs")
        for cell in cells:
            _string(cell, "selection cell ID")
        if "source" in selection:
            _string(selection["source"], "selection.source")
    if cells:
        actions.append({"name": "select_cells", "args": {"cells": cells}})
    if "focus" in state:
        focus = _object(state["focus"], {"cell", "group"}, "handoff focus")
        if set(focus) != {"cell", "group"}:
            raise ValueError("handoff focus must contain cell and group")
        focus_cell = focus.get("cell")
        focus_group = focus.get("group")
        if focus_cell is not None:
            _string(focus_cell, "focus.cell")
        if focus_group is not None:
            _string(focus_group, "focus.group")
        if focus_cell is not None and focus_group is not None:
            raise ValueError("handoff focus may contain a cell or group, not both")
        focus_args: dict[str, str] = {}
        if focus_cell is not None:
            focus_args["cell"] = focus_cell
        elif focus_group is not None:
            focus_args["group"] = focus_group
        actions.append({"name": "focus", "args": focus_args})
    locus = state.get("locus")
    if locus is not None:
        locus = _object(locus, {"chrom", "start", "end"}, "handoff locus")
        _string(locus.get("chrom"), "locus.chrom")
        for key in ("start", "end"):
            if key in locus and (type(locus[key]) is not int or locus[key] < 0):
                raise ValueError(f"locus.{key} must be a non-negative integer")
        if "start" in locus and "end" in locus and locus["end"] <= locus["start"]:
            raise ValueError("locus.end must be greater than locus.start")
        actions.append({"name": "set_locus", "args": {key: locus[key] for key in ("chrom", "start", "end") if key in locus}})
    views = state.get("views", [])
    if not isinstance(views, list):
        raise ValueError("handoff views must be a list")
    view_ids: set[str] = set()
    for view in views:
        view = _object(view, {"id", "type", "scope", "stats_kind", "chrom_scope"}, "handoff view")
        if "id" in view:
            view_id = _string(view["id"], "view.id")
            if view_id in view_ids:
                raise ValueError("handoff view IDs must be unique")
            view_ids.add(view_id)
        if view.get("type") not in ("3d", "spatial", "embedding", "genome", "matrix", "stats"):
            raise ValueError("unsupported handoff view type")
        if view["type"] != "stats" and ("stats_kind" in view or "chrom_scope" in view):
            raise ValueError("stats_kind and chrom_scope require a stats view")
        if "stats_kind" in view and view["stats_kind"] not in ("rg", "scaling", "hist", "scatter"):
            raise ValueError("unsupported handoff stats_kind")
        if "chrom_scope" in view and view["chrom_scope"] not in ("all", "locus"):
            raise ValueError("unsupported handoff chrom_scope")
        args = {"type": view["type"]}
        scope = view.get("scope")
        if scope is not None:
            scope = _object(scope, {"kind", "cell", "group"}, "handoff view scope")
            kind = scope.get("kind")
            if kind == "focus":
                if set(scope) != {"kind"}:
                    raise ValueError("focus view scope cannot contain a cell or group")
            elif kind == "all":
                if set(scope) != {"kind"}:
                    raise ValueError("all view scope cannot contain a cell or group")
                args["cells"] = "all"
            elif kind == "cell":
                if set(scope) != {"kind", "cell"}:
                    raise ValueError("cell view scope must contain only cell")
                args["cells"] = _string(scope.get("cell"), "view scope.cell")
            elif kind == "group":
                if set(scope) != {"kind", "group"}:
                    raise ValueError("group view scope must contain only group")
                args["cells"] = _string(scope.get("group"), "view scope.group")
            else:
                raise ValueError("unsupported handoff view scope")
        if "stats_kind" in view:
            args["stats"] = view["stats_kind"]
        if "chrom_scope" in view:
            args["chrom_scope"] = view["chrom_scope"]
        actions.append({"name": "open_view", "args": args})
    if "workspace" in state:
        workspace = _object(state["workspace"], {"active_pane"}, "handoff workspace")
        active_pane = _string(workspace.get("active_pane"), "workspace.active_pane")
        if active_pane not in view_ids:
            raise ValueError("workspace.active_pane must refer to a handoff view")
        actions.append({"name": "show_view", "args": {"pane": active_pane}})
    if "layout" in state:
        if state["layout"] not in ("tabs", "grid"):
            raise ValueError("handoff layout must be tabs or grid")
        actions.append({"name": "arrange", "args": {"layout": state["layout"]}})
    if state.get("selection") and not cells:
        warnings.append("Selection was not imported because the handoff contains no canonical cell IDs.")
    return actions, warnings


def attach_handoff(value: str, *, connect, pin_page):
    """Redeem/read a handoff, open the dataset, and bind a canonical page."""
    global _started
    payload = _read_handoff(value)
    dataset = payload["dataset"]
    reference = dataset.get("path") or dataset.get("url")
    ws, loaded = _existing_workspace(connect)
    reused = False
    if ws and any(_same_dataset(item, reference) for item in loaded):
        reused = True
        pages = ws.agent_pages()
        if not pages:
            webbrowser.open(ws.url + "/")
    else:
        _started = subprocess.Popen(
            [sys.executable, "-m", "uchrom_browser", reference, "--host=127.0.0.1", "--port=8765"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        ws = _wait_for_server(_started)
    pages = _wait_for_page(ws)
    if len(pages) == 1:
        page_id = pages[0]["page"]
    else:
        active = [page for page in pages if page.get("active")]
        if len(active) != 1:
            raise RuntimeError("multiple local browser pages are connected; close tabs or select one explicitly")
        page_id = active[0]["page"]
    ws._request("POST", "/api/agent/attach", {"page_id": page_id})
    snapshot = ws.agent_snapshot(page_id)
    if snapshot.get("source") != "page_canonical" or not _same_dataset(snapshot.get("dataset"), reference):
        raise RuntimeError("local page canonical dataset does not match the handoff dataset; select the matching dataset and obtain a new handoff")
    pin_page(page_id, ws)
    actions, warnings = _handoff_actions(payload)
    plan = None
    if actions:
        plan = ws.propose_ui_changes(actions, page_id, snapshot["state_revision"])
        warnings.append("Transferred page state is a pending proposal; Apply or Reject it in the local WebUI.")
    return {"attached": True, "page_id": page_id, "local_url": ws.url,
            "browser_reused": reused, "dataset": snapshot.get("dataset"),
            "page_state_status": "pending_review" if plan else "dataset_opened",
            "plan": plan, "warnings": warnings}


def shutdown_started_browser():
    global _started
    process, _started = _started, None
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)
