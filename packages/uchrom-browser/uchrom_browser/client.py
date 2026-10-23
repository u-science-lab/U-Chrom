"""Drive the open web browser from Python: ``ws = uchrom_browser.connect()``.

The same actions the page's GUI uses (``web/ui_tools.json``) — read the researcher's selection, open
and arrange views, capture a view — sent over the server's control channel to the page the researcher
last used.  Analysis stays in Python: ``ws.dataset()`` returns the ChromData the browser has open.

    import uchrom_browser as ub
    ws = ub.connect()                         # the running `python -m uchrom_browser …`
    cells = ws.get_selection()["cells"]       # what the researcher lassoed
    cd = ws.dataset()
    ...                                       # any uchrom analysis
    ws.open_view(type="genome", rows=[{"kind": "distance", "cells": g}], cells=g)   # -> {"pane": "P3"}
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from urllib.parse import quote
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_URL = "http://127.0.0.1:8765"
#: written by ``uchrom_browser.serve`` so that clients find a server on a non-default port
STATE_FILE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "uchrom" / "browser.json"


class BrowserError(RuntimeError):
    """The server or the page refused an action."""


def _default_url() -> str:
    if os.environ.get("UCHROM_BROWSER_URL"):
        return os.environ["UCHROM_BROWSER_URL"]
    try:
        return json.loads(STATE_FILE.read_text())["url"]
    except (OSError, ValueError, KeyError):
        return DEFAULT_URL


class Workspace:
    """A connection to a running browser server (and, through it, to its open page)."""

    def __init__(self, url: Optional[str] = None, timeout: float = 30.0):
        self.url = (url or _default_url()).rstrip("/")
        self.timeout = timeout
        self._session_proof: Optional[Dict[str, str]] = None
        self._tools = {t["name"]: t for t in self._request("GET", "/api/control/tools")["tools"]}

    # -- transport ---------------------------------------------------------
    def _request(self, method: str, path: str, body: Any = None, timeout: Optional[float] = None) -> Any:
        data = None if body is None else json.dumps(body).encode()
        headers = {"Content-Type": "application/json"}
        if method not in {"GET", "HEAD"} and path != "/api/control/session":
            if self._session_proof is None:
                self._session_proof = self._request("GET", "/api/control/session")
            headers["Authorization"] = f"Bearer {self._session_proof['token']}"
        req = urllib.request.Request(self.url + path, data=data, method=method,
                                     headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=(timeout or self.timeout) + 5) as r:
                return json.loads(r.read() or b"null")
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read()).get("detail", exc.reason)
            except ValueError:
                detail = exc.reason
            raise BrowserError(f"{exc.code}: {detail}") from None
        except urllib.error.URLError as exc:
            raise BrowserError(f"cannot reach the browser server at {self.url} ({exc.reason}); "
                               "start it with `python -m uchrom_browser data.chromdata.zarr`") from None

    def call(self, action: str, /, **args) -> Any:
        """Run one browser action (see :meth:`tools`) on the active page and return its result (a dict)."""
        if action not in self._tools:
            raise BrowserError(f"unknown action {action!r}; available: {', '.join(self._tools)}")
        args = {k: v for k, v in args.items() if v is not None}
        return self._request("POST", "/api/control/actions",
                             {"name": action, "args": args, "timeout": self.timeout})["result"]

    def tools(self) -> List[Dict[str, Any]]:
        """The action definitions (name, description, input schema)."""
        return list(self._tools.values())

    def pages(self) -> List[Dict[str, Any]]:
        """Connected browser pages (the first is the one that receives actions)."""
        return self._request("GET", "/api/control/pages")

    def agent_pages(self) -> List[Dict[str, Any]]:
        """Connected pages visible to the local agent control layer."""
        return self._request("GET", "/api/agent/pages")

    def agent_snapshot(self, page: Optional[str] = None) -> Dict[str, Any]:
        """Read canonical state from an explicitly named page."""
        if not page:
            raise BrowserError("an explicit page is required to read the agent snapshot")
        path = "/api/agent/snapshot"
        path += f"?page={quote(page, safe='')}"
        return self._request("GET", path)

    def propose_ui_changes(self, actions: List[Dict[str, Any]], page: Optional[str],
                           expected_revision: str) -> Dict[str, Any]:
        """Create a pending UI mutation plan for an explicitly pinned page."""
        if not page:
            raise BrowserError("an explicit page is required to propose UI changes")
        if not expected_revision:
            raise BrowserError("an expected_revision is required to propose UI changes")
        return self._request("POST", "/api/agent/plans", {
            "page_id": page,
            "expected_revision": expected_revision,
            "actions": actions,
        })

    def plan_status(self, plan_id: str) -> Dict[str, Any]:
        """Read the status and results of a local agent plan."""
        if not plan_id:
            raise BrowserError("plan_id is required")
        return self._request("GET", f"/api/agent/plans/{quote(plan_id, safe='')}")

    def __getattr__(self, name: str):
        tools = self.__dict__.get("_tools", {})
        if name.startswith("_") or name not in tools:
            raise AttributeError(name)
        required = tools[name]["inputSchema"].get("required", [])

        def action(*pos, **args):
            """Positional arguments fill the schema's required fields in order (open_view("genome", …))."""
            if len(pos) > len(required):
                raise TypeError(f"{name}() takes at most {len(required)} positional argument(s): {required}")
            for k, v in zip(required, pos):
                if k in args:
                    raise TypeError(f"{name}() got {k!r} both positionally and by keyword")
                args[k] = v
            return self.call(name, **args)

        action.__name__ = name
        action.__doc__ = tools[name]["description"]
        return action

    def __dir__(self):
        return sorted(set(super().__dir__()) | set(self._tools))

    # -- conveniences ------------------------------------------------------
    def describe(self) -> Dict[str, Any]:
        return self.call("describe_workspace")

    def selected_cells(self) -> List[str]:
        """Cell ids of the current selection (lasso, focused group or cell); [] when none."""
        return list(self.call("get_selection")["cells"])

    def dataset(self):
        """The ChromData the browser has open (read from the same file, in this process)."""
        from chromdata import ChromData
        path = self.describe()["dataset"]["path"]
        if not path:
            raise BrowserError("the open dataset has no file path")
        return ChromData.read(path)

    def capture(self, pane: Optional[str] = None, path: Optional[str] = None, format: Optional[str] = None) -> Dict[str, Any]:
        """Save a view (default: the active one) to ``path`` (default: a temporary file).

        ``format`` is ``"png"`` (pixels, as on screen), ``"svg"`` or ``"pdf"`` (editable vectors for
        Illustrator / Inkscape); by default it follows the suffix of ``path``, else PNG.  Returns
        ``{"path", "pane", "format", "width", "height", "bytes", "notes"}`` — not the image itself;
        ``notes`` lists what the vector file approximates (e.g. 3-D tubes as strokes)."""
        fmt = _capture_format(format, path)
        r = self.call("capture_view", pane=pane, format=fmt)
        data = base64.b64decode(r.get("data_base64") or r["png_base64"])
        if not path:
            import tempfile
            path = tempfile.NamedTemporaryFile(prefix="uchrom_view_", suffix=f".{fmt}", delete=False).name
        Path(path).write_bytes(data)
        return {"path": str(path), "pane": pane, "format": fmt, "width": r["width"], "height": r["height"],
                "bytes": len(data), "notes": list(r.get("notes") or [])}

    def __repr__(self) -> str:
        return f"Workspace({self.url!r})"


CAPTURE_FORMATS = ("png", "svg", "pdf")


def _capture_format(format: Optional[str], path: Optional[str]) -> str:
    """The file format of a capture: ``format`` if given, else the suffix of ``path``, else PNG."""
    if format is None:
        suffix = Path(path).suffix.lower().lstrip(".") if path else ""
        format = suffix if suffix in CAPTURE_FORMATS else "png"
    format = format.lower()
    if format not in CAPTURE_FORMATS:
        raise ValueError(f"format must be one of {CAPTURE_FORMATS}, not {format!r}")
    return format


def connect(url: Optional[str] = None, timeout: float = 30.0) -> Workspace:
    """Connect to a running browser: ``url`` > $UCHROM_BROWSER_URL > the last server started > :8765."""
    return Workspace(url, timeout=timeout)


def write_state(url: str) -> None:
    """Record the running server's URL for :func:`connect` (best effort)."""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps({"url": url.rstrip("/"), "pid": os.getpid()}))
    except OSError:
        pass


def clear_state(url: str) -> None:
    try:
        if json.loads(STATE_FILE.read_text()).get("url") == url.rstrip("/"):
            STATE_FILE.unlink()
    except (OSError, ValueError):
        pass
