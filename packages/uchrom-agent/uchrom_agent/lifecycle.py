"""Local handoff validation and browser process lifecycle."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

_HANDOFF_REDEEM_URL = os.environ.get(
    "UCHROM_HANDOFF_REDEEM_URL",
    "https://uchrom-browser.u-science.org/api/agent/handoffs/redeem",
)
_MAX_HANDOFF_BYTES = 1_048_576
_started: subprocess.Popen | None = None


def _state_file() -> Path:
    from uchrom_browser.client import STATE_FILE
    return STATE_FILE


def _read_handoff(value: str) -> dict[str, Any]:
    if value.lstrip().startswith("{"):
        if len(value.encode("utf-8")) > _MAX_HANDOFF_BYTES:
            raise ValueError("handoff payload exceeds 1 MiB")
        payload = json.loads(value)
    else:
        if len(value) > 4096:
            raise ValueError("handoff token is empty or too long")
        candidate = Path(value).expanduser()
        if candidate.is_file():
            raw = candidate.read_bytes()
            if len(raw) > _MAX_HANDOFF_BYTES:
                raise ValueError("handoff file exceeds 1 MiB")
            payload = json.loads(raw)
        else:
            payload = _redeem(value)
    if not isinstance(payload, dict):
        raise ValueError("handoff payload must be a JSON object")
    dataset = payload.get("dataset")
    reference = dataset.get("path") or dataset.get("url") if isinstance(dataset, dict) else None
    if not isinstance(reference, str) or not reference:
        raise ValueError("handoff must include dataset.url or dataset.path")
    return payload


def _redeem(token: str) -> dict[str, Any]:
    if not token or len(token) > 4096:
        raise ValueError("handoff token is empty or too long")
    request = urllib.request.Request(_HANDOFF_REDEEM_URL,
                                    data=json.dumps({"token": token}).encode("utf-8"),
                                    headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read(_MAX_HANDOFF_BYTES + 1)
            if len(raw) > _MAX_HANDOFF_BYTES:
                raise ValueError("redeemed handoff payload exceeds 1 MiB")
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"handoff redemption failed ({exc.code})") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"handoff redemption failed ({exc.reason})") from None


def _same_dataset(summary: dict[str, Any], reference: str) -> bool:
    path = summary.get("path")
    if path and path.rstrip("/") == reference.rstrip("/"):
        return True
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
    state = payload.get("page_state")
    if state is None:
        return [], []
    if not isinstance(state, dict):
        raise ValueError("handoff page_state must be an object")
    actions: list[dict[str, Any]] = []
    warnings: list[str] = []
    selection = state.get("selection") or {}
    cells = selection.get("cells") if isinstance(selection, dict) else None
    if cells:
        actions.append({"name": "select_cells", "args": {"cells": cells}})
    locus = state.get("locus")
    if isinstance(locus, dict) and locus.get("chrom"):
        actions.append({"name": "set_locus", "args": {key: locus[key] for key in ("chrom", "start", "end") if key in locus}})
    for view in state.get("views", []):
        if not isinstance(view, dict) or not isinstance(view.get("type"), str):
            warnings.append("A handoff view was skipped because its shape was invalid.")
            continue
        args = dict(view)
        if "stats_kind" in args:
            args["stats"] = args.pop("stats_kind")
        args.pop("pane", None)
        actions.append({"name": "open_view", "args": args})
    if state.get("layout"):
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
    pin_page(page_id)
    snapshot = ws.agent_snapshot(page_id)
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
