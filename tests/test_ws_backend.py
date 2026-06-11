import pytest
from fastapi.testclient import TestClient
from webapp.backend.main import app

client = TestClient(app)


def test_ws_connect_and_ping():
    """Unknown message types get a flat error response over /ws/main."""
    with client.websocket_connect("/ws/main") as ws:
        ws.send_json({"type": "ping"})
        data = ws.receive_json()
        assert data["type"] == "error"
        assert "unknown" in data["message"].lower()


