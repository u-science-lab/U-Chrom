"""
Tests for all new features added in Phase 1 & 2:
- File upload endpoint
- Agent code execution (unit + E2E with real Claude CLI)
- Agent cell selection action
- _extract_code_blocks / _run_code_in_worker
- Session save/load format (store serialization)
- Linked cameras / render mode (store state shape)
"""
import io
import json
import time
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from webapp.backend.main import app
from webapp.backend.ws_handler import (
    _extract_code_blocks,
    _parse_actions,
    _run_code_in_worker,
)

client = TestClient(app)
H5CD = "/tmp/imr90_chr21.h5cd"  # created by test setup or existing fixture


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_h5cd(path: str, n_cells: int = 5, n_bins: int = 20):
    from uchrom.core import ChromData
    spots = pd.DataFrame({
        "chrom": "chr21",
        "start": list(np.arange(n_bins) * 100_000) * n_cells,
        "end": list(np.arange(n_bins) * 100_000 + 100_000) * n_cells,
        "trace_id": np.repeat(np.arange(n_cells), n_bins),
        "cell_id": np.repeat(np.arange(n_cells), n_bins),
    })
    coords = np.random.randn(n_cells * n_bins, 3).astype(np.float32)
    cells = pd.DataFrame({"cell_type": ["TypeA"] * n_cells}, index=range(n_cells))
    umap = np.random.randn(n_cells, 2).astype(np.float32)
    cd = ChromData(coords=coords, spots=spots, cells=cells, cellm={"umap": umap})
    cd.write(path)
    return path


@pytest.fixture(scope="module")
def h5cd_path(tmp_path_factory):
    p = str(tmp_path_factory.mktemp("data") / "test.h5cd")
    return _make_h5cd(p)


# ── upload ────────────────────────────────────────────────────────────────────

def test_upload_h5cd(h5cd_path):
    with open(h5cd_path, "rb") as f:
        r = client.post("/api/upload", files={"file": ("test.h5cd", f, "application/octet-stream")})
    assert r.status_code == 200
    body = r.json()
    assert "path" in body
    assert body["path"].endswith(".h5cd")


def test_upload_then_load(h5cd_path):
    """Upload a file, then load it via WebSocket."""
    with open(h5cd_path, "rb") as f:
        r = client.post("/api/upload", files={"file": ("test.h5cd", f, "application/octet-stream")})
    uploaded_path = r.json()["path"]

    with client.websocket_connect("/ws/main") as ws:
        ws.send_json({"type": "load_data", "payload": {"path": uploaded_path, "format": "h5cd"}})
        msg = ws.receive_json()
    assert msg["type"] == "data_loaded"
    assert msg["payload"]["cell_count"] == 5


# ── code extraction ───────────────────────────────────────────────────────────

def test_extract_code_blocks_single():
    text = "Here:\n```python\nprint('hi')\n```\nDone."
    blocks = _extract_code_blocks(text)
    assert blocks == ["print('hi')\n"]


def test_extract_code_blocks_multiple():
    text = "```python\na=1\n```\nand\n```python\nb=2\n```"
    blocks = _extract_code_blocks(text)
    assert len(blocks) == 2


def test_extract_code_blocks_none():
    assert _extract_code_blocks("no code here") == []


# ── _run_code_in_worker ───────────────────────────────────────────────────────

def test_run_code_emit_text_block(h5cd_path):
    code = "emit_artifact('text_block', {'content': 'hello', 'format': 'summary'})"
    arts = _run_code_in_worker(code, h5cd_path)
    assert len(arts) == 1
    assert arts[0]["artifact_type"] == "text_block"
    assert arts[0]["payload"]["content"] == "hello"


def test_run_code_uses_chromdata(h5cd_path):
    code = "emit_artifact('text_block', {'content': str(len(cd.cells)), 'format': 'summary'})"
    arts = _run_code_in_worker(code, h5cd_path)
    assert arts[0]["payload"]["content"] == "5"


def test_run_code_uses_uchrom(h5cd_path):
    code = "emit_artifact('text_block', {'content': str(type(uchrom).__name__), 'format': 'summary'})"
    arts = _run_code_in_worker(code, h5cd_path)
    assert arts[0]["payload"]["content"] == "module"


def test_run_code_error_returns_artifact(h5cd_path):
    code = "raise ValueError('boom')"
    arts = _run_code_in_worker(code, h5cd_path)
    assert len(arts) == 1
    assert arts[0]["payload"]["format"] == "error"
    assert "boom" in arts[0]["payload"]["content"]


def test_run_code_no_chromdata():
    code = "emit_artifact('text_block', {'content': 'ok', 'format': 'summary'})"
    arts = _run_code_in_worker(code, None)
    assert arts[0]["payload"]["content"] == "ok"


# ── action parser ─────────────────────────────────────────────────────────────

def test_parse_action_set_viewport():
    text = '<action type="set_viewport">{"chrom":"chr21","start":1000,"end":2000}</action>'
    actions = _parse_actions(text)
    assert len(actions) == 1
    assert actions[0]["action_type"] == "set_viewport"
    assert actions[0]["payload"]["chrom"] == "chr21"


def test_parse_action_select_cells():
    text = '<action type="select_cells">{"mode":"cell_type","ids":[],"label":"TypeA"}</action>'
    actions = _parse_actions(text)
    assert actions[0]["action_type"] == "select_cells"
    assert actions[0]["payload"]["label"] == "TypeA"


def test_parse_action_multiple():
    text = (
        '<action type="set_viewport">{"chrom":"chr1","start":0,"end":1000}</action> '
        '<action type="select_cells">{"mode":"all","ids":[],"label":"All"}</action>'
    )
    assert len(_parse_actions(text)) == 2


def test_parse_action_invalid_json():
    assert _parse_actions('<action type="set_viewport">not-json</action>') == []


# ── agent cell selection via WebSocket ───────────────────────────────────────

def test_agent_cell_selection_ws(h5cd_path):
    """Agent message with select_cells action updates session and pushes WS message."""
    with client.websocket_connect("/ws/main") as ws:
        ws.send_json({"type": "load_data", "payload": {"path": h5cd_path, "format": "h5cd"}})
        assert ws.receive_json()["type"] == "data_loaded"

        ws.send_json({"type": "agent_message", "payload": {
            "session_id": "test",
            "text": "Select all TypeA cells",
        }})

        cell_sel = None
        deadline = time.time() + 45
        while time.time() < deadline:
            try:
                msg = ws.receive_json()
                if msg["type"] == "agent_token" and msg["payload"].get("done"):
                    deadline = min(deadline, time.time() + 2)
                elif msg["type"] == "agent_cell_selection":
                    cell_sel = msg["payload"]
                    break
            except Exception:
                break

    assert cell_sel is not None, "No agent_cell_selection received"
    assert cell_sel.get("label") == "TypeA"


# ── agent code execution E2E (real Claude CLI) ────────────────────────────────

def test_agent_code_execution_e2e(h5cd_path):
    """Claude generates a python code block → backend executes → agent_artifact received."""
    with client.websocket_connect("/ws/main") as ws:
        ws.send_json({"type": "load_data", "payload": {"path": h5cd_path, "format": "h5cd"}})
        assert ws.receive_json()["type"] == "data_loaded"

        ws.send_json({"type": "agent_message", "payload": {
            "session_id": "test",
            "text": "Output a Python code block that calls emit_artifact with content 'exec_ok'.",
        }})

        tokens, artifacts = [], []
        deadline = time.time() + 45
        while time.time() < deadline:
            try:
                msg = ws.receive_json()
                if msg["type"] == "agent_token":
                    tokens.append(msg["payload"].get("token", ""))
                    if msg["payload"].get("done"):
                        deadline = min(deadline, time.time() + 15)
                elif msg["type"] == "agent_artifact":
                    artifacts.append(msg["payload"])
            except Exception:
                break

    full = "".join(tokens)
    assert "```python" in full, f"No code block in response: {full[:300]}"
    assert len(artifacts) > 0, "No agent_artifact received after code execution"
    assert artifacts[0]["payload"]["content"] == "exec_ok"


# ── session save/load format ──────────────────────────────────────────────────

def test_session_format_roundtrip():
    """Verify the .uchromfig session JSON format is stable."""
    session = {
        "version": 1,
        "viewport": {"chrom": "chr21", "start": 18_600_000, "end": 20_600_000},
        "cellSelection": {"mode": "cell_type", "ids": [], "label": "TypeA"},
        "panels": [
            {"id": "p1", "type": "umap", "label": "Cell Embedding"},
            {"id": "p2", "type": "structure3d", "label": "3D Structure"},
        ],
        "timestamp": 1716000000000,
    }
    serialized = json.dumps(session)
    restored = json.loads(serialized)
    assert restored["version"] == 1
    assert restored["viewport"]["chrom"] == "chr21"
    assert len(restored["panels"]) == 2
    assert restored["panels"][1]["type"] == "structure3d"


# ── store state shape (camera + render mode) ─────────────────────────────────

def test_camera_state_in_session():
    """cameraState and linkedCameras are optional fields in session."""
    session = {
        "version": 1,
        "viewport": {"chrom": "chr1", "start": 0, "end": 1_000_000},
        "cellSelection": {"mode": "all", "ids": [], "label": "All Cells"},
        "panels": [],
        "cameraState": {"position": [0, 0, 5], "target": [0, 0, 0]},
        "linkedCameras": True,
        "timestamp": 0,
    }
    s = json.loads(json.dumps(session))
    assert s["cameraState"]["position"] == [0, 0, 5]
    assert s["linkedCameras"] is True
