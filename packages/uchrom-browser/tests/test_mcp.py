"""Tests for the pure-stdlib stdio MCP server (``uchrom_browser.mcp``) and multi-tab client support."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import socket
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
uvicorn = pytest.importorskip("uvicorn")
requests = pytest.importorskip("requests")

from uchrom_browser import client as ubc  # noqa: E402
from uchrom_browser import create_app  # noqa: E402
from uchrom_browser.control import load_tools  # noqa: E402


def _free_port() -> int:
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


class FakeSSEPage(threading.Thread):
    """Subscribes to ``/api/control/events`` and can be cleanly closed to simulate tab close."""

    def __init__(self, base: str, handler, page: str):
        super().__init__(daemon=True)
        self.base = base
        self.handler = handler
        self.page = page
        self.seen = []
        self.ready = threading.Event()
        self._stop = threading.Event()
        self._resp = None

    def run(self):
        try:
            with requests.get(
                f"{self.base}/api/control/events",
                params={"page": self.page},
                stream=True,
                timeout=30,
            ) as r:
                self._resp = r
                event = None
                for line in r.iter_lines(decode_unicode=True):
                    if self._stop.is_set():
                        break
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
        except Exception:  # noqa: BLE001
            if not self._stop.is_set():
                raise

    def close(self):
        self._stop.set()
        resp = self._resp
        if resp is not None:
            try:
                sock = getattr(getattr(getattr(getattr(resp, "raw", None), "_fp", None), "fp", None), "raw", None)
                if sock is not None and getattr(sock, "_sock", None) is not None:
                    sock._sock.shutdown(socket.SHUT_RDWR)
            except Exception:  # noqa: BLE001
                pass
            try:
                resp.close()
            except Exception:  # noqa: BLE001
                pass
        self.join(timeout=3)


def _rpc(srv, msg: dict):
    out = io.StringIO()
    srv.handle_line(json.dumps(msg), out)
    raw = out.getvalue()
    return json.loads(raw) if raw else None


def _call_tool(srv, req_id: int, name: str, arguments=None):
    params = {"name": name}
    if arguments is not None:
        params["arguments"] = arguments
    resp = _rpc(srv, {"jsonrpc": "2.0", "id": req_id, "method": "tools/call", "params": params})
    assert resp["id"] == req_id
    return resp["result"]


def test_jsonrpc_handshake_and_errors():
    from uchrom_browser.mcp import McpServer

    srv = McpServer(url="http://127.0.0.1:1")  # offline is fine for handshake

    # blank lines ignored
    out = io.StringIO()
    srv.handle_line("   \n", out)
    assert out.getvalue() == ""

    # parse error -32700
    out = io.StringIO()
    srv.handle_line("{bad json", out)
    err = json.loads(out.getvalue())
    assert err["error"]["code"] == -32700

    # initialize negotiates supported versions
    for ver in ("2025-11-25", "2025-06-18", "2024-11-05"):
        res = _rpc(srv, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": ver}})
        assert res["result"]["protocolVersion"] == ver
        assert res["result"]["capabilities"] == {
            "tools": {"listChanged": False},
            "resources": {"subscribe": False, "listChanged": False},
            "prompts": {"listChanged": False},
        }
        assert res["result"]["serverInfo"]["name"] == "uchrom-browser"

    # unknown protocol version falls back to newest supported
    res = _rpc(srv, {"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}})
    assert res["result"]["protocolVersion"] == "2025-11-25"

    # notifications/initialized produces no output
    assert _rpc(srv, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None

    # ping
    assert _rpc(srv, {"jsonrpc": "2.0", "id": 3, "method": "ping"})["result"] == {}

    # unknown method -32601
    res = _rpc(srv, {"jsonrpc": "2.0", "id": 4, "method": "no/such_method"})
    assert res["error"]["code"] == -32601

    # invalid params -32602 (missing tool name / unknown tool / non-dict arguments)
    res = _rpc(srv, {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {}})
    assert res["error"]["code"] == -32602
    res = _rpc(srv, {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "uchrom_nope"}})
    assert res["error"]["code"] == -32602
    res = _rpc(srv, {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "uchrom_status", "arguments": []}})
    assert res["error"]["code"] == -32602


def test_tools_list_dynamic_and_offline_fallback(server):
    from uchrom_browser.mcp import McpServer

    expected_ui = load_tools()["tools"]
    expected_names = {f"uchrom_{t['name']}" for t in expected_ui} | {
        "uchrom_status",
        "uchrom_list_pages",
        "uchrom_bind_page",
        "uchrom_wait_for_page",
        "uchrom_batch",
    }

    for url in (server, "http://127.0.0.1:1"):
        srv = McpServer(url=url, timeout=1.0)
        res = _rpc(srv, {"jsonrpc": "2.0", "id": 10, "method": "tools/list"})["result"]
        by_name = {t["name"]: t for t in res["tools"]}
        assert set(by_name) == expected_names
        assert by_name["uchrom_status"]["annotations"]["readOnlyHint"] is True
        assert by_name["uchrom_list_pages"]["annotations"]["readOnlyHint"] is True
        assert by_name["uchrom_wait_for_page"]["annotations"]["readOnlyHint"] is True
        assert "page" in by_name["uchrom_bind_page"]["inputSchema"]["properties"]

        for raw in expected_ui:
            tool = by_name[f"uchrom_{raw['name']}"]
            assert tool["description"] == raw["description"]
            assert "page" in tool["inputSchema"]["properties"]
            if raw["name"] == "capture_view":
                assert tool["annotations"] == {
                    "readOnlyHint": False,
                    "destructiveHint": False,
                    "idempotentHint": False,
                }
            elif "annotations" in raw:
                assert tool["annotations"] == raw["annotations"]
        assert "path" in by_name["uchrom_capture_view"]["inputSchema"]["properties"]


def test_single_page_status_actions_capture_and_schema_validation(server, tmp_path):
    from uchrom_browser.mcp import McpServer

    png_bytes = b"\x89PNG\r\n\x1a\nFAKEPNGDATA"
    svg_bytes = b"<svg xmlns='http://www.w3.org/2000/svg'><rect/></svg>"

    def handler(name, args):
        if name == "open_view":
            return {"pane": "P3"}
        if name == "capture_view":
            fmt = args.get("format") or "png"
            raw = png_bytes if fmt == "png" else svg_bytes
            b64 = base64.b64encode(raw).decode()
            out = {"data_base64": b64, "format": fmt, "width": 320, "height": 240, "notes": ["ok"]}
            if fmt == "png":
                out["png_base64"] = b64
            return out
        return {"echo": args}

    page = FakeSSEPage(server, handler, page="tab1")
    page.start()
    assert page.ready.wait(5)
    try:
        srv = McpServer(url=server, timeout=5.0)

        # status
        st = _call_tool(srv, 1, "uchrom_status")
        assert st["isError"] is False
        st_data = st["structuredContent"]
        assert st_data["url"] == server
        assert st_data["health"]["status"] == "ok"
        assert st_data["datasets"] == []
        assert [p["page"] for p in st_data["pages"]] == ["tab1"]
        assert st_data["bound_page"] is None

        # open_view
        ov = _call_tool(srv, 2, "uchrom_open_view", {"type": "stats", "stats": "rg"})
        assert ov["isError"] is False
        assert ov["structuredContent"] == {"pane": "P3", "page": "tab1"}
        assert json.loads(ov["content"][0]["text"]) == {"pane": "P3", "page": "tab1"}
        assert page.seen[-1]["args"] == {"type": "stats", "stats": "rg"}

        # capture_view to explicit path (PNG)
        png_out = tmp_path / "shot.png"
        cap_png = _call_tool(srv, 3, "uchrom_capture_view", {"pane": "P3", "path": str(png_out)})
        assert cap_png["isError"] is False
        meta_png = cap_png["structuredContent"]
        assert meta_png["path"] == str(png_out)
        assert meta_png["format"] == "png"
        assert meta_png["pane"] == "P3"
        assert meta_png["page"] == "tab1"
        assert meta_png["bytes"] == len(png_bytes)
        assert meta_png["sha256"] == hashlib.sha256(png_bytes).hexdigest()
        assert png_out.read_bytes() == png_bytes
        assert "data_base64" not in cap_png["content"][0]["text"]
        assert "png_base64" not in cap_png["content"][0]["text"]
        assert base64.b64encode(png_bytes).decode() not in cap_png["content"][0]["text"]

        # capture_view to private temp dir (SVG)
        cap_svg = _call_tool(srv, 4, "uchrom_capture_view", {"format": "svg"})
        assert cap_svg["isError"] is False
        meta_svg = cap_svg["structuredContent"]
        svg_path = Path(meta_svg["path"])
        try:
            assert svg_path.suffix == ".svg"
            assert svg_path.read_bytes() == svg_bytes
            assert meta_svg["sha256"] == hashlib.sha256(svg_bytes).hexdigest()
            assert stat.S_IMODE(svg_path.parent.stat().st_mode) == 0o700
            assert "data_base64" not in cap_svg["content"][0]["text"]
            assert base64.b64encode(svg_bytes).decode() not in cap_svg["content"][0]["text"]
        finally:
            svg_path.unlink(missing_ok=True)

        # strict JSON-schema checks never hit the page
        before = len(page.seen)
        bad_missing = _call_tool(srv, 5, "uchrom_open_view", {})
        bad_unknown = _call_tool(srv, 6, "uchrom_open_view", {"type": "stats", "bogus": 1})
        bad_enum = _call_tool(srv, 7, "uchrom_open_view", {"type": "invalid_type"})
        bad_type = _call_tool(srv, 8, "uchrom_set_locus", {"chrom": "chr1", "start": True})
        assert all(r["isError"] is True for r in (bad_missing, bad_unknown, bad_enum, bad_type))
        assert len(page.seen) == before
    finally:
        page.close()

    # offline status returns clear isError
    offline = McpServer(url="http://127.0.0.1:1", timeout=0.5)
    st_off = _call_tool(offline, 9, "uchrom_status")
    assert st_off["isError"] is True
    assert "cannot reach" in st_off["content"][0]["text"].lower()


def test_two_tab_safety(server):
    from uchrom_browser.mcp import McpServer

    tab_a = FakeSSEPage(server, lambda n, a: {"pane": "PA", "got": a}, page="tabA")
    tab_b = FakeSSEPage(server, lambda n, a: {"pane": "PB", "got": a}, page="tabB")
    tab_a.start()
    tab_b.start()
    assert tab_a.ready.wait(5) and tab_b.ready.wait(5)
    try:
        srv = McpServer(url=server, timeout=5.0)

        # 2 tabs connected, no page and no binding -> MUST fail without hitting either tab
        res = _call_tool(srv, 1, "uchrom_open_view", {"type": "stats"})
        assert res["isError"] is True
        err_text = res["content"][0]["text"]
        assert "tabA" in err_text and "tabB" in err_text
        assert len(tab_a.seen) == 0 and len(tab_b.seen) == 0

        # invalid bind does not bind
        bad_bind = _call_tool(srv, 2, "uchrom_bind_page", {"page": "tabZ"})
        assert bad_bind["isError"] is True
        assert srv.bound_page is None

        # explicit page routes only to tabA
        res_a = _call_tool(srv, 3, "uchrom_open_view", {"type": "3d", "page": "tabA"})
        assert res_a["isError"] is False
        assert res_a["structuredContent"]["page"] == "tabA"
        assert len(tab_a.seen) == 1 and len(tab_b.seen) == 0

        # bind tabB and run open_view without explicit page -> routes to tabB, 0 new on tabA
        bound = _call_tool(srv, 4, "uchrom_bind_page", {"page": "tabB"})
        assert bound["isError"] is False
        assert bound["structuredContent"]["bound_page"] == "tabB"

        res_b = _call_tool(srv, 5, "uchrom_open_view", {"type": "genome"})
        assert res_b["isError"] is False
        assert res_b["structuredContent"]["page"] == "tabB"
        assert len(tab_a.seen) == 1 and len(tab_b.seen) == 1

        # close tabB: bound session MUST error and NEVER silently fail over to tabA
        tab_b.close()
        # wait until server sees tabB disconnected
        for _ in range(50):
            pages = [p["page"] for p in requests.get(f"{server}/api/control/pages", timeout=2).json()]
            if "tabB" not in pages:
                break
            time.sleep(0.05)
        assert "tabB" not in pages

        fail = _call_tool(srv, 6, "uchrom_open_view", {"type": "stats"})
        assert fail["isError"] is True
        assert "tabB" in fail["content"][0]["text"]
        assert len(tab_a.seen) == 1  # untouched!

        # unbind clears binding; single remaining tabA now resolves cleanly
        unbind = _call_tool(srv, 7, "uchrom_bind_page", {"page": None})
        assert unbind["isError"] is False
        assert unbind["structuredContent"]["bound_page"] is None
        res_a2 = _call_tool(srv, 8, "uchrom_open_view", {"type": "stats"})
        assert res_a2["isError"] is False
        assert res_a2["structuredContent"]["page"] == "tabA"
        assert len(tab_a.seen) == 2
    finally:
        tab_a.close()
        tab_b.close()


def test_client_workspace_page_routing(server, tmp_path):
    tab_a = FakeSSEPage(server, lambda n, a: {"cells": ["cA"]} if n == "get_selection" else {"from": "A", "args": a}, page="tabA")
    tab_b = FakeSSEPage(
        server,
        lambda n, a: (
            {"data_base64": base64.b64encode(b"<svg/>").decode(), "format": "svg", "width": 5, "height": 5}
            if n == "capture_view"
            else {"from": "B", "args": a}
        ),
        page="tabB",
    )
    tab_a.start()
    tab_b.start()
    assert tab_a.ready.wait(5) and tab_b.ready.wait(5)
    try:
        ws = ubc.connect(server, timeout=5)
        assert ws.selected_cells(page="tabA") == ["cA"]
        assert ws.describe(page="tabB")["from"] == "B"
        assert ws.open_view("stats", page="tabA")["from"] == "A"
        assert tab_a.seen[-1]["args"] == {"type": "stats"}
        cap = ws.capture(path=str(tmp_path / "b.svg"), page="tabB")
        assert cap["format"] == "svg" and (tmp_path / "b.svg").read_bytes() == b"<svg/>"
    finally:
        tab_a.close()
        tab_b.close()


def test_subprocess_stdio_pipe(server):
    page = FakeSSEPage(server, lambda n, a: {"pane": "P9"} if n == "open_view" else {"ok": True}, page="tabSub")
    page.start()
    assert page.ready.wait(5)

    proc = subprocess.Popen(
        [sys.executable, "-m", "uchrom_browser.mcp", "--url", server, "--timeout", "5"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "uchrom_status"}},
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "uchrom_open_view", "arguments": {"type": "3d"}},
            },
        ]
        assert proc.stdin is not None and proc.stdout is not None
        for m in messages:
            proc.stdin.write(json.dumps(m) + "\n")
        proc.stdin.close()

        lines = [json.loads(line) for line in proc.stdout.read().splitlines() if line.strip()]
        rc = proc.wait(timeout=10)
        assert rc == 0, proc.stderr.read() if proc.stderr else ""
        assert [r["id"] for r in lines] == [1, 2, 3, 4]
        assert lines[0]["result"]["protocolVersion"] == "2025-11-25"
        assert any(t["name"] == "uchrom_open_view" for t in lines[1]["result"]["tools"])
        assert lines[2]["result"]["structuredContent"]["pages"][0]["page"] == "tabSub"
        assert lines[3]["result"]["structuredContent"] == {"pane": "P9", "page": "tabSub"}
    finally:
        page.close()
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def test_mcp_uses_no_uchrom_or_third_party_mcp():
    script = (
        "import sys; import uchrom_browser.mcp; "
        "print('uchrom:', any(m == 'uchrom' or m.startswith('uchrom.') for m in sys.modules)); "
        "print('mcp:', 'mcp' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True).stdout
    assert "uchrom: False" in out
    assert "mcp: False" in out


def test_mcp_python_s_stdlib_only_cli():
    pkg_root = str(Path(__file__).resolve().parents[1])
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = pkg_root
    proc = subprocess.run(
        [sys.executable, "-S", "-m", "uchrom_browser.mcp", "--help"],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    assert "uchrom_browser.mcp" in proc.stdout or "--url" in proc.stdout


def test_mcp_jsonrpc_edge_cases_and_validation(server):
    from uchrom_browser.mcp import McpServer

    huge_id = "1" * 5000
    wire_in = (
        f'{{"jsonrpc":"2.0","id":{huge_id},"method":"ping"}}\n'
        '{"jsonrpc":"2.0","id":NaN,"method":"ping"}\n'
        '{"jsonrpc":"2.0","id":"\\ud800","method":"ping"}\n'
        '{"id":1,"method":"ping"}\n'
        '{"jsonrpc":"2.0","id":true,"method":"ping"}\n'
        '{"jsonrpc":"2.0","id":2,"method":"notifications/initialized"}\n'
        '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"uchrom_bind_page","arguments":{"page":"tabX"}}}\n'
        '{"jsonrpc":"2.0","id":3,"method":"initialize","params":null}\n'
        '{"jsonrpc":"2.0","id":4,"method":"ping"}\n'
    )
    proc = subprocess.run(
        [sys.executable, "-m", "uchrom_browser.mcp", "--url", server],
        input=wire_in,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, proc.stderr
    lines = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    # 7 responses expected: 3 parse/surrogate + 3 invalid-request + initialize + ping - notification w/o id drops,
    # Wait: notifications/initialized WITH id=2 produces -32600; tools/call WITHOUT id produces no response -> total 8!
    assert len(lines) == 8
    assert lines[0]["error"]["code"] == -32700
    assert lines[1]["error"]["code"] == -32700
    assert lines[2]["id"] == "\ud800" and lines[2]["result"] == {}
    assert lines[3]["error"]["code"] == -32600
    assert lines[4]["error"]["code"] == -32600
    assert lines[5]["error"]["code"] == -32600
    assert lines[6]["id"] == 3 and "protocolVersion" in lines[6]["result"]
    assert lines[7]["id"] == 4 and lines[7]["result"] == {}

    # ID-less notification must not mutate bound_page, integral float accepted for integer, overflow -> isError
    page = FakeSSEPage(server, lambda n, a: {"ok": True, "args": a}, page="tabJ")
    page.start()
    assert page.ready.wait(5)
    try:
        srv = McpServer(url=server, timeout=5.0)
        out = io.StringIO()
        srv.handle_line(
            '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"uchrom_bind_page","arguments":{"page":"tabJ"}}}',
            out,
        )
        assert out.getvalue() == ""
        assert srv.bound_page is None

        ok_float_int = _call_tool(srv, 10, "uchrom_set_locus", {"chrom": "chr1", "start": 1.0, "end": 5.0})
        assert ok_float_int["isError"] is False
        assert page.seen[-1]["args"] == {"chrom": "chr1", "start": 1, "end": 5}

        huge_num_line = (
            '{"jsonrpc":"2.0","id":11,"method":"tools/call",'
            '"params":{"name":"uchrom_open_view","arguments":{"type":"spatial","image_opacity":' + ("9" * 400) + "}}}"
        )
        out2 = io.StringIO()
        srv.handle_line(huge_num_line, out2)
        resp = json.loads(out2.getvalue().splitlines()[0])
        assert resp["id"] == 11
        assert resp["result"]["isError"] is True
    finally:
        page.close()


def test_mcp_capture_view_safety(server, tmp_path):
    from uchrom_browser.mcp import McpServer

    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    page = FakeSSEPage(
        server,
        lambda n, a: {
            "data_base64": base64.b64encode(png_bytes).decode(),
            "format": a.get("format", "png"),
            "width": 10,
            "height": 10,
        },
        page="tabCap",
    )
    page.start()
    assert page.ready.wait(5)
    try:
        srv = McpServer(url=server, timeout=5.0)

        # Existing file must never be silently overwritten
        existing = tmp_path / "existing.png"
        existing.write_bytes(b"keep-me")
        r_exist = _call_tool(srv, 1, "uchrom_capture_view", {"path": str(existing)})
        assert r_exist["isError"] is True
        assert existing.read_bytes() == b"keep-me"

        # .. traversal rejected before touching browser page
        before = len(page.seen)
        r_trav = _call_tool(srv, 2, "uchrom_capture_view", {"path": str(tmp_path / "sub" / ".." / "out.png")})
        assert r_trav["isError"] is True
        assert len(page.seen) == before

        # Extension vs explicit format mismatch rejected
        r_fmt = _call_tool(srv, 3, "uchrom_capture_view", {"path": str(tmp_path / "shot.png"), "format": "svg"})
        assert r_fmt["isError"] is True
        assert len(page.seen) == before

        # Unwritable parent (parent is a regular file) fails BEFORE sending action to browser page
        before_bad = len(page.seen)
        r_bad_parent = _call_tool(srv, 4, "uchrom_capture_view", {"path": str(existing / "shot.png")})
        assert r_bad_parent["isError"] is True
        assert len(page.seen) == before_bad

        # Symlink intermediate directory is rejected even inside _write_exclusive
        from uchrom_browser.mcp import _write_exclusive

        real_dir = tmp_path / "real_dir"
        real_dir.mkdir()
        link_dir = tmp_path / "link_dir"
        link_dir.symlink_to(real_dir)
        with pytest.raises(OSError):
            _write_exclusive(link_dir / "shot.png", png_bytes)
        r_sym = _call_tool(srv, 5, "uchrom_capture_view", {"path": str(link_dir / "shot.png")})
        assert r_sym["isError"] is True
    finally:
        page.close()


def test_mcp_p2_hardening_overflow_and_intmaxstrdigits(server):
    from uchrom_browser.mcp import McpServer

    # Even with PYTHONINTMAXSTRDIGITS=0, 5000-digit id is rejected with -32700 cleanly
    env = dict(os.environ)
    env["PYTHONINTMAXSTRDIGITS"] = "0"
    huge_id = "1" * 5000
    wire_in = (
        f'{{"jsonrpc":"2.0","id":{huge_id},"method":"ping"}}\n'
        '{"jsonrpc":"2.0","id":2,"method":"ping"}\n'
    )
    proc = subprocess.run(
        [sys.executable, "-m", "uchrom_browser.mcp", "--url", server],
        input=wire_in,
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    assert proc.returncode == 0, proc.stderr
    lines = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    assert len(lines) == 2
    assert lines[0]["error"]["code"] == -32700
    assert lines[1]["id"] == 2 and lines[1]["result"] == {}

    # Overflowing int (>64-bit) and nested Infinity/overflow in object items must return isError
    page = FakeSSEPage(server, lambda n, a: {"ok": True}, page="tabOv")
    page.start()
    assert page.ready.wait(5)
    try:
        srv = McpServer(url=server, timeout=5.0)
        r_big_int = _call_tool(srv, 10, "uchrom_set_locus", {"chrom": "chr1", "start": 10**400, "end": 5})
        assert r_big_int["isError"] is True

        nested_inf_line = (
            '{"jsonrpc":"2.0","id":11,"method":"tools/call",'
            '"params":{"name":"uchrom_open_view","arguments":{"type":"genome","rows":[{"smooth":1e400}]}}}'
        )
        out_inf = io.StringIO()
        srv.handle_line(nested_inf_line, out_inf)
        resp_inf = json.loads(out_inf.getvalue().splitlines()[0])
        assert resp_inf["id"] == 11 and resp_inf["result"]["isError"] is True

        r_nested_big = _call_tool(srv, 12, "uchrom_open_view", {"type": "genome", "rows": [{"smooth": 10**400}]})
        assert r_nested_big["isError"] is True
        r_num_big = _call_tool(srv, 13, "uchrom_open_view", {"type": "spatial", "image_opacity": 2**63})
        assert r_num_big["isError"] is True
        assert len(page.seen) == 0

        # Nested depth > 64 inside object/array arguments is rejected cleanly
        nested_deep = 1
        for _ in range(70):
            nested_deep = {"a": nested_deep}
        r_deep_arg = _call_tool(srv, 14, "uchrom_open_view", {"type": "genome", "rows": [nested_deep]})
        assert r_deep_arg["isError"] is True
        assert len(page.seen) == 0

        # Extremely deep JSON (RecursionError or invalid params) never crashes stdio loop
        deep = "[" * 5000 + "]" * 5000
        out_deep = io.StringIO()
        srv.handle_line(f'{{"jsonrpc":"2.0","id":15,"method":"ping","params":{deep}}}', out_deep)
        resp_deep = json.loads(out_deep.getvalue().splitlines()[0])
        assert resp_deep["error"]["code"] in (-32700, -32602)
        out_after = io.StringIO()
        srv.handle_line('{"jsonrpc":"2.0","id":16,"method":"ping"}', out_after)
        assert json.loads(out_after.getvalue())["result"] == {}
    finally:
        page.close()


def test_mcp_resources_prompts_wait_doctor_and_print_config(server):
    from uchrom_browser.mcp import McpServer

    # initialize advertises tools, resources, and prompts
    srv = McpServer(url=server, timeout=5.0)
    init = _rpc(srv, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})["result"]
    assert set(init["capabilities"]) >= {"tools", "resources", "prompts"}

    res_list = _rpc(srv, {"jsonrpc": "2.0", "id": 2, "method": "resources/list"})["result"]
    uris = {r["uri"] for r in res_list["resources"]}
    assert uris == {"uchrom://status", "uchrom://pages", "uchrom://workspace", "uchrom://selection"}

    st_read = _rpc(srv, {"jsonrpc": "2.0", "id": 3, "method": "resources/read", "params": {"uri": "uchrom://status"}})
    st_json = json.loads(st_read["result"]["contents"][0]["text"])
    assert st_json["health"]["status"] == "ok" and st_json["pages"] == []

    bad_uri = _rpc(srv, {"jsonrpc": "2.0", "id": 4, "method": "resources/read", "params": {"uri": "uchrom://unknown"}})
    assert bad_uri["error"]["code"] == -32602

    # prompts/list and prompts/get
    pr_list = _rpc(srv, {"jsonrpc": "2.0", "id": 5, "method": "prompts/list"})["result"]
    assert {p["name"] for p in pr_list["prompts"]} == {"compare-selection", "inspect-locus"}

    pr_miss = _rpc(srv, {"jsonrpc": "2.0", "id": 6, "method": "prompts/get", "params": {"name": "inspect-locus", "arguments": {}}})
    assert pr_miss["error"]["code"] == -32602

    pr_ok = _rpc(srv, {"jsonrpc": "2.0", "id": 7, "method": "prompts/get", "params": {"name": "compare-selection", "arguments": {"chrom": "chr3"}}})["result"]
    assert "chr3" in pr_ok["messages"][0]["content"]["text"]

    pr_lone = _rpc(srv, {"jsonrpc": "2.0", "id": 71, "method": "prompts/get", "params": {"name": "inspect-locus", "arguments": {"chrom": "chr7", "start": "1000"}}})["result"]
    assert "1000" in pr_lone["messages"][0]["content"]["text"]

    pr_neg = _rpc(srv, {"jsonrpc": "2.0", "id": 72, "method": "prompts/get", "params": {"name": "inspect-locus", "arguments": {"chrom": "chr7", "start": "-5"}}})
    assert pr_neg["error"]["code"] == -32602

    pr_bad = _rpc(srv, {"jsonrpc": "2.0", "id": 8, "method": "prompts/get", "params": {"name": "no-such-prompt"}})
    assert pr_bad["error"]["code"] == -32602

    # wait_for_page timeout when no tab connected (and bounded within wait_seconds)
    t0 = time.monotonic()
    w_to = _call_tool(srv, 9, "uchrom_wait_for_page", {"wait_seconds": 0.1})
    assert w_to["isError"] is True
    assert time.monotonic() - t0 < 2.0

    # wait_for_page succeeds when tab connects asynchronously; resources work; 2-tab safety enforced
    page_a = FakeSSEPage(
        server,
        lambda n, a: {"cells": ["c1"]} if n == "get_selection" else {"panes": [{"pane": "P1"}]},
        page="tabR1",
    )

    def _delayed_start():
        time.sleep(0.25)
        page_a.start()

    th = threading.Thread(target=_delayed_start, daemon=True)
    th.start()
    try:
        w_ok = _call_tool(srv, 10, "uchrom_wait_for_page", {"page": "tabR1", "wait_seconds": 5.0})
        assert w_ok["isError"] is False
        assert w_ok["structuredContent"]["pages"][0]["page"] == "tabR1"

        sel_read = _rpc(srv, {"jsonrpc": "2.0", "id": 11, "method": "resources/read", "params": {"uri": "uchrom://selection"}})
        assert json.loads(sel_read["result"]["contents"][0]["text"])["cells"] == ["c1"]

        page_b = FakeSSEPage(server, lambda n, a: {"cells": ["c2"]}, page="tabR2")
        page_b.start()
        assert page_b.ready.wait(5)
        try:
            amb = _rpc(srv, {"jsonrpc": "2.0", "id": 12, "method": "resources/read", "params": {"uri": "uchrom://workspace"}})
            assert amb["error"]["code"] == -32002
        finally:
            page_b.close()
    finally:
        page_a.close()

    # --print-config keeps venv python (abspath, not resolved symlink) & valid JSON/TOML
    py_abs = os.path.abspath(sys.executable)
    p_claude = subprocess.run(
        [sys.executable, "-m", "uchrom_browser.mcp", "--print-config", "claude", "--url", server],
        capture_output=True,
        text=True,
        check=True,
    )
    cfg_c = json.loads(p_claude.stdout)
    assert cfg_c["mcpServers"]["uchrom-browser"]["command"] == py_abs
    assert cfg_c["mcpServers"]["uchrom-browser"]["args"] == ["-m", "uchrom_browser.mcp", "--url", server]

    p_codex = subprocess.run(
        [sys.executable, "-m", "uchrom_browser.mcp", "--print-config", "codex"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "[mcp_servers.uchrom-browser]" in p_codex.stdout and py_abs in p_codex.stdout

    # --doctor online (0), offline (3), and proxy warning
    no_proxy_env = {k: v for k, v in os.environ.items() if k not in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")}
    d_on = subprocess.run(
        [sys.executable, "-m", "uchrom_browser.mcp", "--doctor", "--url", server],
        capture_output=True,
        text=True,
        env=no_proxy_env,
    )
    assert d_on.returncode == 0
    assert json.loads(d_on.stdout)["server_reachable"] is True

    d_off = subprocess.run(
        [sys.executable, "-m", "uchrom_browser.mcp", "--doctor", "--url", "http://127.0.0.1:1", "--timeout", "0.5"],
        capture_output=True,
        text=True,
        env={**no_proxy_env, "http_proxy": "http://127.0.0.1:7897"},
    )
    assert d_off.returncode == 3
    off_doc = json.loads(d_off.stdout)
    assert off_doc["server_reachable"] is False and len(off_doc["proxy_warnings"]) >= 1


def test_mcp_page_summaries_and_batch(server, tmp_path):
    from uchrom_browser.mcp import McpServer

    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16

    def _mk_handler(ds_name):
        def handler(name, args):
            if name == "describe_workspace":
                return {
                    "dataset": {"id": f"id_{ds_name}", "name": ds_name, "path": f"/tmp/{ds_name}.zarr"},
                    "views": [{"pane": "P1"}],
                    "active_view": "P1",
                    "layout": "tabs",
                    "focus": {"cell": None, "group": None},
                    "selection": None,
                    "locus": {"chrom": "chr1", "start": 0, "end": 1000},
                }
            if name == "open_view":
                return {"pane": "P2"}
            if name == "capture_view":
                return {
                    "data_base64": base64.b64encode(png_bytes).decode(),
                    "format": args.get("format", "png"),
                    "width": 20,
                    "height": 20,
                }
            if name == "show_view" and args.get("pane") == "BOOM":
                raise RuntimeError("pane not found")
            return {"ok": True, "args": args}

        return handler

    tab_a = FakeSSEPage(server, _mk_handler("alpha"), page="tabA")
    tab_b = FakeSSEPage(server, _mk_handler("beta"), page="tabB")
    tab_a.start()
    tab_b.start()
    assert tab_a.ready.wait(5) and tab_b.ready.wait(5)
    try:
        srv = McpServer(url=server, timeout=5.0)

        # list_pages and uchrom://pages attach per-tab summaries
        lp = _call_tool(srv, 1, "uchrom_list_pages")
        assert lp["isError"] is False
        by_id = {p["page"]: p for p in lp["structuredContent"]["pages"]}
        assert by_id["tabA"]["summary"]["dataset"] == "alpha"
        assert by_id["tabB"]["summary"]["dataset"] == "beta"

        pages_res = _rpc(srv, {"jsonrpc": "2.0", "id": 2, "method": "resources/read", "params": {"uri": "uchrom://pages"}})
        pages_json = json.loads(pages_res["result"]["contents"][0]["text"])
        assert {p["summary"]["dataset"] for p in pages_json["pages"]} == {"alpha", "beta"}

        # probe=False skips describe_workspace calls
        before_a, before_b = len(tab_a.seen), len(tab_b.seen)
        lp_noprobe = _call_tool(srv, 3, "uchrom_list_pages", {"probe": False})
        assert lp_noprobe["isError"] is False
        assert "summary" not in lp_noprobe["structuredContent"]["pages"][0]
        assert len(tab_a.seen) == before_a and len(tab_b.seen) == before_b

        # Upfront validation failure dispatches ZERO steps
        cap_path = tmp_path / "batch_ok.png"
        bad_batch = _call_tool(
            srv,
            4,
            "uchrom_batch",
            {
                "page": "tabA",
                "steps": [
                    {"action": "set_locus", "args": {"chrom": "chr1", "start": 0, "end": 500}},
                    {"action": "open_view", "args": {"type": "bogus"}},
                ],
            },
        )
        assert bad_batch["isError"] is True
        assert len(tab_a.seen) == before_a and len(tab_b.seen) == before_b

        # Duplicate capture output path inside one batch fails upfront with ZERO dispatches
        dup_cap = _call_tool(
            srv,
            5,
            "uchrom_batch",
            {
                "page": "tabA",
                "steps": [
                    {"action": "capture_view", "args": {"path": str(cap_path)}},
                    {"action": "capture_view", "args": {"path": str(cap_path)}},
                ],
            },
        )
        assert dup_cap["isError"] is True
        assert len(tab_a.seen) == before_a

        # Valid 3-step batch executes sequentially on tabA only
        ok_batch = _call_tool(
            srv,
            6,
            "uchrom_batch",
            {
                "page": "tabA",
                "steps": [
                    {"action": "set_locus", "args": {"chrom": "chr1", "start": 100, "end": 900}},
                    {"action": "open_view", "args": {"type": "stats", "stats": "rg"}},
                    {"action": "capture_view", "args": {"pane": "P2", "path": str(cap_path)}},
                ],
            },
        )
        assert ok_batch["isError"] is False
        sc = ok_batch["structuredContent"]
        assert sc["page"] == "tabA" and sc["completed"] == 3
        assert len(sc["results"]) == 3
        assert cap_path.read_bytes() == png_bytes
        assert len(tab_b.seen) == before_b

        # Mid-batch runtime error halts before trailing step and reports completed count
        before_a2 = len(tab_a.seen)
        mid_fail = _call_tool(
            srv,
            7,
            "uchrom_batch",
            {
                "page": "tabA",
                "steps": [
                    {"action": "arrange", "args": {"layout": "grid"}},
                    {"action": "show_view", "args": {"pane": "BOOM"}},
                    {"action": "close_view", "args": {"pane": "P2"}},
                ],
            },
        )
        assert mid_fail["isError"] is True
        mf = mid_fail["structuredContent"]
        assert mf["completed"] == 1 and mf["failed_step"] == 1 and mf["failed_action"] == "show_view"
        assert len(tab_a.seen) == before_a2 + 2  # arrange + failing show_view; close_view never sent
    finally:
        tab_a.close()
        tab_b.close()
