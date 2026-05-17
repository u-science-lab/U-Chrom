import pytest
from fastapi.testclient import TestClient
from webapp.backend.main import app

client = TestClient(app)


def test_ws_connect_and_ping():
    with client.websocket_connect("/ws/main") as ws:
        ws.send_json({"type": "ping"})
        data = ws.receive_json()
        assert data["type"] == "error"
        assert "unknown type" in data["payload"]["message"]
