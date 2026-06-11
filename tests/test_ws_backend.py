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


from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_send_agui_formats_envelope():
    """agui_events.send_agui still emits the {type, payload} envelope."""
    from webapp.backend.agui_events import AGUI, send_agui
    ws = AsyncMock()
    await send_agui(ws, AGUI.TEXT_MESSAGE_START, {"message_id": "m1", "role": "assistant"})
    ws.send_json.assert_called_once_with({
        "type": "TEXT_MESSAGE_START",
        "payload": {"message_id": "m1", "role": "assistant"},
    })


def test_agui_constants():
    from webapp.backend.agui_events import AGUI
    assert AGUI.RUN_STARTED == "RUN_STARTED"
    assert AGUI.TEXT_MESSAGE_START == "TEXT_MESSAGE_START"
    assert AGUI.TEXT_MESSAGE_CONTENT == "TEXT_MESSAGE_CONTENT"
    assert AGUI.TEXT_MESSAGE_END == "TEXT_MESSAGE_END"
    assert AGUI.TOOL_CALL_START == "TOOL_CALL_START"
    assert AGUI.TOOL_CALL_ARGS == "TOOL_CALL_ARGS"
    assert AGUI.TOOL_CALL_END == "TOOL_CALL_END"
    assert AGUI.RUN_FINISHED == "RUN_FINISHED"
    assert AGUI.RUN_ERROR == "RUN_ERROR"
