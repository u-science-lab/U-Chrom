"""Control channel (``control.py``) and the Python client (``uchrom_browser.connect``).

A real server runs in a thread; a fake page subscribes to the SSE stream and answers actions the
way the frontend's ``control.ts`` does, so the whole round trip is exercised without a browser.
"""

import json
import socket
import threading
import time

import pytest

pytest.importorskip("fastapi")
uvicorn = pytest.importorskip("uvicorn")
requests = pytest.importorskip("requests")

from uchrom_browser import client as ubc  # noqa: E402
from uchrom_browser import create_app  # noqa: E402
from uchrom_browser.control import load_tools  # noqa: E402


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server():
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(200):
        try:
            if requests.get(base + "/api/health", timeout=0.2).ok:
                break
        except requests.ConnectionError:
            time.sleep(0.05)
    yield base
    srv.should_exit = True
    th.join(5)


class FakePage(threading.Thread):
    """Subscribes like control.ts and answers each action with ``handler(name, args)``."""

    def __init__(self, base, handler, page="ptest"):
        super().__init__(daemon=True)
        self.base, self.handler, self.page = base, handler, page
        self.seen = []
        self.ready = threading.Event()

    def run(self):
        with requests.get(f"{self.base}/api/control/events", params={"page": self.page}, stream=True,
                          timeout=30) as r:
            event = None
            for line in r.iter_lines(decode_unicode=True):
                if line.startswith("event: "):
                    event = line[7:]
                elif line.startswith("data: ") and event == "hello":
                    self.ready.set()
                elif line.startswith("data: ") and event == "action":
                    msg = json.loads(line[6:])
                    self.seen.append(msg)
                    try:
                        body = {"ok": True, "result": self.handler(msg["name"], msg["args"])}
                    except Exception as exc:  # noqa: BLE001
                        body = {"ok": False, "error": str(exc)}
                    requests.post(f"{self.base}/api/control/results/{msg['id']}", json=body, timeout=5)


def test_tools_file_is_valid():
    tools = load_tools()["tools"]
    names = [t["name"] for t in tools]
    assert len(names) == len(set(names))
    for t in tools:
        assert t["description"] and t["inputSchema"]["type"] == "object"


def test_no_page_is_a_clear_error(server):
    ws = ubc.connect(server, timeout=2)
    with pytest.raises(ubc.BrowserError, match="409"):
        ws.get_selection()


def test_round_trip_through_a_page(server):
    def handler(name, args):
        if name == "get_selection":
            return {"cells": ["c1", "c2"], "group": "g1", "name": None, "source": "lasso"}
        if name == "open_view":
            if args["type"] == "nope":
                raise ValueError("unknown view type: nope")
            return {"pane": "P3"}
        return {"echo": args}

    page = FakePage(server, handler)
    page.start()
    assert page.ready.wait(5)
    ws = ubc.connect(server, timeout=5)
    assert ws.pages()[0]["page"] == "ptest"
    assert ws.selected_cells() == ["c1", "c2"]
    assert ws.open_view("genome", cells="g1", rows=[{"kind": "distance"}]) == {"pane": "P3"}
    assert page.seen[-1]["args"] == {"type": "genome", "cells": "g1", "rows": [{"kind": "distance"}]}
    with pytest.raises(ubc.BrowserError, match="422: unknown view type"):
        ws.open_view("nope")
    with pytest.raises(ubc.BrowserError, match="unknown action"):
        ws.call("rm_rf")
    assert "select_cells" in dir(ws)
    # an action argument called `name` must not clash with the action name
    ws.select_cells(cells=["c1"], name="my group")
    assert page.seen[-1]["args"] == {"cells": ["c1"], "name": "my group"}


def test_timeout_when_the_page_does_not_answer(server):
    page = FakePage(server, lambda n, a: time.sleep(3))
    page.start()
    assert page.ready.wait(5)
    ws = ubc.connect(server, timeout=0.5)
    with pytest.raises(ubc.BrowserError, match="504"):
        ws.describe()


def test_connect_finds_the_last_server(tmp_path, monkeypatch, server):
    monkeypatch.setattr(ubc, "STATE_FILE", tmp_path / "browser.json")
    monkeypatch.delenv("UCHROM_BROWSER_URL", raising=False)
    ubc.write_state(server + "/")
    assert ubc.connect().url == server
    ubc.clear_state(server)
    assert not (tmp_path / "browser.json").exists()


def test_capture_formats_through_a_page(server, tmp_path):
    import base64

    files = {"png": b"\x89PNG\r\n", "svg": b"<svg xmlns='http://www.w3.org/2000/svg'/>", "pdf": b"%PDF-1.3"}

    def handler(name, args):
        assert name == "capture_view"
        fmt = args.get("format") or "png"
        data = base64.b64encode(files[fmt]).decode()
        out = {"data_base64": data, "format": fmt, "width": 10, "height": 8, "filename": f"v.{fmt}",
               "notes": ["tubes as strokes"] if fmt != "png" else []}
        if fmt == "png":
            out["png_base64"] = data
        return out

    page = FakePage(server, handler)
    page.start()
    assert page.ready.wait(5)
    ws = ubc.connect(server, timeout=5)
    # the format follows the suffix of the path
    r = ws.capture(path=str(tmp_path / "fig.svg"))
    assert page.seen[-1]["args"]["format"] == "svg"
    assert r["format"] == "svg" and r["notes"] == ["tubes as strokes"]
    assert (tmp_path / "fig.svg").read_bytes() == files["svg"]
    # an explicit format wins; no path → a temporary file with that suffix
    r = ws.capture(format="pdf")
    assert r["path"].endswith(".pdf") and open(r["path"], "rb").read() == files["pdf"]
    # default: PNG
    r = ws.capture(path=str(tmp_path / "fig"))
    assert page.seen[-1]["args"]["format"] == "png" and r["bytes"] == len(files["png"])
    with pytest.raises(ValueError, match="format must be one of"):
        ws.capture(format="tiff")


def test_capture_tool_declares_formats():
    tool = next(t for t in load_tools()["tools"] if t["name"] == "capture_view")
    assert tool["inputSchema"]["properties"]["format"]["enum"] == ["png", "svg", "pdf"]
