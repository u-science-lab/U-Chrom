"""Tests for the pure-stdlib Agent-friendly control CLI (``uchrom-browser-ctl`` / ``uchrom_browser.cli``)."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")
pytest.importorskip("requests")

from tests.test_mcp import FakeSSEPage, server  # noqa: F401,E402


def _run_ctl(*args: str, state_file: Path, url: str | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")}
    env["UCHROM_BROWSER_CTL_STATE"] = str(state_file)
    cmd = [sys.executable, "-m", "uchrom_browser.cli"]
    if url is not None:
        cmd.extend(["--url", url])
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(cwd) if cwd else None, timeout=15)


def test_ctl_python_s_stdlib_only_and_script_help():
    pkg_root = str(Path(__file__).resolve().parents[1])
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = pkg_root

    p_stdlib = subprocess.run(
        [sys.executable, "-S", "-m", "uchrom_browser.cli", "--help"],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert p_stdlib.returncode == 0, p_stdlib.stderr
    assert "uchrom-browser-ctl" in p_stdlib.stdout

    ctl_bin = Path(sys.executable).parent / "uchrom-browser-ctl"
    if ctl_bin.exists():
        p_bin = subprocess.run([str(ctl_bin), "--help"], capture_output=True, text=True, timeout=10)
        assert p_bin.returncode == 0, p_bin.stderr
        assert "uchrom-browser-ctl" in p_bin.stdout

    mod_check = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import uchrom_browser.cli; "
            "print(any(m == 'uchrom' or m.startswith('uchrom.') for m in sys.modules))",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert mod_check.stdout.strip() == "False"


def test_ctl_exit_codes_and_strict_json(server, tmp_path):  # noqa: F811
    state = tmp_path / "ctl.json"

    # Exit 2: invalid CLI arguments / bad locus / bad JSON payload / schema violation
    r_bad_locus = _run_ctl("locus", "chr1:500-100", state_file=state, url=server)
    assert r_bad_locus.returncode == 2
    assert json.loads(r_bad_locus.stderr)["code"] == "INVALID_ARGS"

    r_bad_json = _run_ctl("call", "open_view", "--json", '{"type":NaN}', state_file=state, url=server)
    assert r_bad_json.returncode == 2
    assert json.loads(r_bad_json.stderr)["code"] == "INVALID_ARGS"

    r_bad_schema = _run_ctl("call", "open_view", "--json", '{"type":"bogus"}', state_file=state, url=server)
    assert r_bad_schema.returncode == 2
    assert json.loads(r_bad_schema.stderr)["code"] == "INVALID_ARGS"

    # Exit 3: unreachable server or zero connected tabs
    r_off = _run_ctl("status", "--timeout", "0.5", state_file=state, url="http://127.0.0.1:1")
    assert r_off.returncode == 3
    assert json.loads(r_off.stderr)["code"] == "UNREACHABLE"

    r_doc_off = _run_ctl("doctor", "--timeout", "0.5", state_file=state, url="http://127.0.0.1:1")
    assert r_doc_off.returncode == 3
    assert json.loads(r_doc_off.stdout)["server_reachable"] is False

    r_notab = _run_ctl("selection", state_file=state, url=server)
    assert r_notab.returncode == 3
    assert json.loads(r_notab.stderr)["code"] == "UNREACHABLE"

    # Exit 0: tools (compact summary vs --schema) & doctor online
    r_tools = _run_ctl("tools", state_file=state, url=server)
    assert r_tools.returncode == 0
    tools_out = json.loads(r_tools.stdout)
    assert any(t["name"] == "open_view" for t in tools_out["tools"])
    assert "inputSchema" not in tools_out["tools"][0]

    r_schema = _run_ctl("tools", "--schema", "open_view", state_file=state, url=server)
    assert r_schema.returncode == 0
    assert r_schema.stdout and "inputSchema" in json.loads(r_schema.stdout)

    r_doc_ok = _run_ctl("doctor", state_file=state, url=server)
    assert r_doc_ok.returncode == 0
    assert json.loads(r_doc_ok.stdout)["ok"] is True


def test_ctl_multitab_binding_actions_and_capture(server, tmp_path):  # noqa: F811
    state = tmp_path / "ctl.json"
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16

    def _handle(label):
        def fn(name, args):
            if name == "capture_view":
                return {
                    "data_base64": base64.b64encode(png_bytes).decode(),
                    "format": args.get("format", "png"),
                    "width": 12,
                    "height": 12,
                }
            if name == "action_fail":
                raise RuntimeError("boom")
            if name == "get_selection":
                return {"cells": [f"c_{label}"], "group": None, "name": None, "source": "lasso"}
            return {"from": label, "name": name, "args": args}

        return fn

    tab_a = FakeSSEPage(server, _handle("A"), page="tabA")
    tab_b = FakeSSEPage(server, _handle("B"), page="tabB")
    tab_a.start()
    tab_b.start()
    assert tab_a.ready.wait(5) and tab_b.ready.wait(5)
    try:
        # Ambiguous 2 tabs -> exit 4 without hitting either tab
        r_amb = _run_ctl("selection", state_file=state, url=server)
        assert r_amb.returncode == 4
        err_amb = json.loads(r_amb.stderr)
        assert err_amb["code"] == "PAGE_CONFLICT"
        assert set(err_amb["connected_pages"]) == {"tabA", "tabB"}
        assert not tab_a.seen and not tab_b.seen

        # Persistent bind to tabB
        r_bind = _run_ctl("bind", "tabB", state_file=state, url=server)
        assert r_bind.returncode == 0
        assert json.loads(r_bind.stdout)["bound_page"] == "tabB"

        # Subsequent calls route to tabB automatically
        r_loc = _run_ctl("locus", "chr15:3,000,000-33,000,000", state_file=state, url=server)
        assert r_loc.returncode == 0
        assert tab_b.seen[-1]["name"] == "set_locus"
        assert tab_b.seen[-1]["args"] == {"chrom": "chr15", "start": 3_000_000, "end": 33_000_000}

        # --page overrides binding per invocation
        r_sel_a = _run_ctl("--page", "tabA", "selection", state_file=state, url=server)
        assert r_sel_a.returncode == 0
        assert json.loads(r_sel_a.stdout)["cells"] == ["c_A"]

        # select, focus, open, arrange, color-by, call
        cells_txt = tmp_path / "cells.txt"
        cells_txt.write_text("# comment\nc1\nc2\n")
        assert _run_ctl("select", "--cells-file", str(cells_txt), "--name", "grp", state_file=state, url=server).returncode == 0
        assert tab_b.seen[-1]["args"] == {"cells": ["c1", "c2"], "name": "grp"}

        assert _run_ctl("focus", "--group", "g1", state_file=state, url=server).returncode == 0
        assert tab_b.seen[-1]["args"] == {"group": "g1"}

        r_open = _run_ctl(
            "open",
            "stats",
            "--stats",
            "rg",
            "--chrom-scope",
            "locus",
            "--compare",
            "g1,field:cell_type=B",
            state_file=state,
            url=server,
        )
        assert r_open.returncode == 0
        assert tab_b.seen[-1]["args"] == {
            "type": "stats",
            "stats": "rg",
            "chrom_scope": "locus",
            "compare_groups": ["g1", "field:cell_type=B"],
        }

        assert _run_ctl("arrange", "grid", state_file=state, url=server).returncode == 0
        assert _run_ctl("color-by", "cell_type", state_file=state, url=server).returncode == 0

        # Capture relative path + overwrite refusal (exit 5)
        r_cap = _run_ctl("capture", "--out", "rel_out.png", state_file=state, url=server, cwd=tmp_path)
        assert r_cap.returncode == 0, r_cap.stderr
        cap_json = json.loads(r_cap.stdout)
        assert cap_json["format"] == "png" and (tmp_path / "rel_out.png").read_bytes() == png_bytes

        r_overwrite = _run_ctl("capture", "--out", str(tmp_path / "rel_out.png"), state_file=state, url=server)
        assert r_overwrite.returncode == 5
        assert (tmp_path / "rel_out.png").read_bytes() == png_bytes

        # Close tabB -> exit 4 without failing over to tabA
        tab_b.close()
        import requests
        import time

        for _ in range(50):
            if "tabB" not in [p["page"] for p in requests.get(f"{server}/api/control/pages", timeout=2).json()]:
                break
            time.sleep(0.05)

        r_lost = _run_ctl("selection", state_file=state, url=server)
        assert r_lost.returncode == 4
        assert json.loads(r_lost.stderr)["bound_page"] == "tabB"

        # Clear binding -> resolves single remaining tabA cleanly
        assert _run_ctl("bind", "--clear", state_file=state, url=server).returncode == 0
        r_a2 = _run_ctl("selection", state_file=state, url=server)
        assert r_a2.returncode == 0
        assert json.loads(r_a2.stdout)["cells"] == ["c_A"]
    finally:
        tab_a.close()
        tab_b.close()


def test_ctl_concurrent_binds_permissions_and_transport_codes(tmp_path):
    from uchrom_browser.client import BrowserError
    from uchrom_browser.mcp import ActionExecutionError, McpServer, NoPageConnectedError, PageConflictError
    from uchrom_browser.cli import _load_bindings, _update_binding_locked
    import http.server
    import threading
    import stat

    # 1. Parent directory permissions under UCHROM_BROWSER_CTL_STATE are NOT modified
    custom_dir = tmp_path / "custom_state_dir"
    custom_dir.mkdir(mode=0o755)
    os.chmod(custom_dir, 0o755)
    custom_state = custom_dir / "ctl.json"
    old_env = os.environ.get("UCHROM_BROWSER_CTL_STATE")
    os.environ["UCHROM_BROWSER_CTL_STATE"] = str(custom_state)
    try:
        # Interleaved concurrent updates for two distinct server URLs preserve both bindings
        errors = []

        def worker(url, page):
            try:
                for i in range(10):
                    _update_binding_locked(custom_state, url, f"{page}_{i}")
            except BaseException as exc:  # pragma: no cover
                errors.append(exc)

        t1 = threading.Thread(target=worker, args=("http://127.0.0.1:9001", "pA"))
        t2 = threading.Thread(target=worker, args=("http://127.0.0.1:9002", "pB"))
        t1.start()
        t2.start()
        t1.join(5)
        t2.join(5)
        assert not errors
        saved = _load_bindings(custom_state)
        assert saved == {"http://127.0.0.1:9001": "pA_9", "http://127.0.0.1:9002": "pB_9"}
        assert stat.S_IMODE(custom_dir.stat().st_mode) == 0o755
    finally:
        if old_env is None:
            os.environ.pop("UCHROM_BROWSER_CTL_STATE", None)
        else:
            os.environ["UCHROM_BROWSER_CTL_STATE"] = old_env

    # 2. HTTP 409 on targeted page race -> exit 4; HTTP 504 / timeout -> exit 3
    class _MockHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/api/control/pages":
                body = json.dumps([{"page": "tabA", "active": True}]).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(length) or b"{}")
            if req.get("name") == "get_selection":
                body = json.dumps({"detail": "page gone"}).encode()
                self.send_response(409)
            else:
                body = json.dumps({"detail": "timeout"}).encode()
                self.send_response(504)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _MockHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    mock_url = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        r_409 = _run_ctl("--page", "tabA", "selection", state_file=tmp_path / "m.json", url=mock_url)
        assert r_409.returncode == 4
        assert json.loads(r_409.stderr)["code"] == "PAGE_CONFLICT"

        r_504 = _run_ctl("--page", "tabA", "groups", state_file=tmp_path / "m.json", url=mock_url)
        assert r_504.returncode == 3
        assert json.loads(r_504.stderr)["code"] == "UNREACHABLE"
    finally:
        srv.shutdown()


def test_ctl_pages_summary_and_batch(server, tmp_path):  # noqa: F811
    state = tmp_path / "ctl.json"

    def _handle(ds_name):
        def fn(name, args):
            if name == "describe_workspace":
                return {
                    "dataset": {"id": f"d_{ds_name}", "name": ds_name, "path": f"/data/{ds_name}.zarr"},
                    "views": [{"pane": "P1"}],
                    "active_view": "P1",
                    "layout": "tabs",
                    "focus": {"cell": None, "group": None},
                    "selection": None,
                    "locus": {"chrom": "chr1", "start": 0, "end": 1000},
                }
            if name == "show_view" and args.get("pane") == "MISSING":
                raise RuntimeError("no such pane")
            return {"from": ds_name, "name": name, "args": args}

        return fn

    tab_a = FakeSSEPage(server, _handle("alpha"), page="tab1")
    tab_b = FakeSSEPage(server, _handle("beta"), page="tab2")
    tab_a.start()
    tab_b.start()
    assert tab_a.ready.wait(5) and tab_b.ready.wait(5)
    try:
        r_pages = _run_ctl("pages", state_file=state, url=server)
        assert r_pages.returncode == 0
        pages_out = {p["page"]: p for p in json.loads(r_pages.stdout)["pages"]}
        assert pages_out["tab1"]["summary"]["dataset"] == "alpha"
        assert pages_out["tab2"]["summary"]["dataset"] == "beta"

        before_a = len(tab_a.seen)
        r_noprobe = _run_ctl("pages", "--no-probe", state_file=state, url=server)
        assert r_noprobe.returncode == 0
        assert "summary" not in json.loads(r_noprobe.stdout)["pages"][0]
        assert len(tab_a.seen) == before_a

        # Batch upfront schema rejection -> exit 2, zero actions dispatched
        bad_steps = json.dumps([
            {"action": "arrange", "args": {"layout": "grid"}},
            {"action": "open_view", "args": {"type": "invalid"}},
        ])
        r_bad = _run_ctl("--page", "tab1", "batch", "--steps-json", bad_steps, state_file=state, url=server)
        assert r_bad.returncode == 2
        assert json.loads(r_bad.stderr)["code"] == "INVALID_ARGS"
        assert len(tab_a.seen) == before_a

        # Batch success via --steps-file
        steps_file = tmp_path / "steps.json"
        steps_file.write_text(json.dumps([
            {"action": "set_locus", "args": {"chrom": "chr1", "start": 10, "end": 200}},
            {"action": "arrange", "args": {"layout": "grid"}},
        ]))
        r_ok = _run_ctl("--page", "tab1", "batch", "--steps-file", str(steps_file), state_file=state, url=server)
        assert r_ok.returncode == 0
        ok_json = json.loads(r_ok.stdout)
        assert ok_json["page"] == "tab1" and ok_json["completed"] == 2

        # Mid-batch browser failure -> exit 5 with structured step progress
        fail_steps = json.dumps([
            {"action": "arrange", "args": {"layout": "tabs"}},
            {"action": "show_view", "args": {"pane": "MISSING"}},
            {"action": "close_view", "args": {"pane": "P1"}},
        ])
        r_fail = _run_ctl("--page", "tab1", "batch", "--steps-json", fail_steps, state_file=state, url=server)
        assert r_fail.returncode == 5
        err_json = json.loads(r_fail.stderr)
        assert err_json["code"] == "ACTION_ERROR"
        assert err_json["completed"] == 1 and err_json["failed_step"] == 1
    finally:
        tab_a.close()
        tab_b.close()
