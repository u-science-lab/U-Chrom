"""Integration tests: load_data + agent_message full flow."""
import asyncio
import json
import pytest
from fastapi.testclient import TestClient
from webapp.backend.main import app

client = TestClient(app)
H5CD = "/tmp/test.h5cd"


def test_load_data_h5cd():
    with client.websocket_connect("/ws/main") as ws:
        ws.send_json({"type": "load_data", "payload": {"path": H5CD, "format": "h5cd"}})
        data = ws.receive_json()
        assert data["type"] == "data_loaded"
        assert data["payload"]["cell_count"] == 1
        assert "chr1" in data["payload"]["chroms"]
        assert data["payload"]["umap_url"] == "/api/umap"


def test_load_data_bad_path():
    with client.websocket_connect("/ws/main") as ws:
        ws.send_json({"type": "load_data", "payload": {"path": "/nonexistent.h5cd", "format": "h5cd"}})
        data = ws.receive_json()
        assert data["type"] == "error"


def test_data_api_after_load():
    """After load_data, HTTP endpoints should return real data."""
    import webapp.backend.data_api as _da
    import numpy as np
    from uchrom.core import ChromData

    # Directly set current_session for HTTP endpoint test
    from webapp.backend.session import Session
    s = Session(session_id="test")
    n = 50
    import pandas as pd
    spots = pd.DataFrame({
        'chrom': ['chr1']*n, 'start': np.arange(n)*100000,
        'end': np.arange(n)*100000+100000, 'trace_id': [0]*n, 'cell_id': [0]*n,
    })
    coords = np.random.randn(n, 3).astype(np.float32)
    cells = pd.DataFrame({'cell_type': ['TypeA']}, index=[0])
    umap = np.random.randn(1, 2).astype(np.float32)
    s.chromdata = ChromData(coords=coords, spots=spots, cells=cells, cellm={'umap': umap})
    _da.current_session = s

    r = client.get("/api/umap")
    assert r.status_code == 200
    body = r.json()
    assert len(body["points"]) == 1
    assert body["points"][0]["cell_type"] == "TypeA"

    r = client.get("/api/coords/0")
    assert r.status_code == 200
    arr = np.frombuffer(r.content, dtype=np.float32).reshape(-1, 3)
    assert arr.shape == (n, 3)

    _da.current_session = None


def test_agent_message_streams_tokens():
    """Agent message should stream tokens from claude CLI (real subprocess)."""
    tokens = []
    with client.websocket_connect("/ws/main") as ws:
        ws.send_json({"type": "agent_message",
                      "payload": {"session_id": "s1", "text": "Reply with exactly: PONG"}})
        # TestClient WebSocket is synchronous; collect until done or 30s
        import time
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                msg = ws.receive_json()
            except Exception:
                break
            if msg["type"] == "agent_token":
                tokens.append(msg["payload"]["token"])
                if msg["payload"].get("done"):
                    break

    assert len(tokens) > 0, "No tokens received from agent"
    full = "".join(tokens)
    assert len(full) > 0
