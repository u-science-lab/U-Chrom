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


from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_send_agui_formats_envelope():
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


import json as _json
from unittest.mock import AsyncMock, MagicMock, patch


def _make_stream_events(text_chunks, tool_calls=None):
    """Build fake Anthropic streaming events."""
    events = []
    ms = MagicMock(); ms.type = "message_start"
    events.append(ms)
    # text block
    cbs = MagicMock(); cbs.type = "content_block_start"
    cbs.index = 0; cbs.content_block = MagicMock(); cbs.content_block.type = "text"
    events.append(cbs)
    for chunk in text_chunks:
        d = MagicMock(); d.type = "content_block_delta"
        d.index = 0; d.delta = MagicMock(); d.delta.type = "text_delta"; d.delta.text = chunk
        events.append(d)
    cbe = MagicMock(); cbe.type = "content_block_stop"; cbe.index = 0
    events.append(cbe)
    # optional tool_use blocks
    if tool_calls:
        for idx, tc in enumerate(tool_calls, start=1):
            tbs = MagicMock(); tbs.type = "content_block_start"
            tbs.index = idx
            tbs.content_block = MagicMock(); tbs.content_block.type = "tool_use"
            tbs.content_block.id = tc["id"]; tbs.content_block.name = tc["name"]
            events.append(tbs)
            td = MagicMock(); td.type = "content_block_delta"
            td.index = idx; td.delta = MagicMock()
            td.delta.type = "input_json_delta"
            td.delta.partial_json = _json.dumps(tc["input"])
            events.append(td)
            tbe = MagicMock(); tbe.type = "content_block_stop"; tbe.index = idx
            events.append(tbe)
    md = MagicMock(); md.type = "message_delta"
    md.delta = MagicMock()
    md.delta.stop_reason = "tool_use" if tool_calls else "end_turn"
    events.append(md)
    return events


@pytest.mark.asyncio
async def test_agui_text_streaming():
    """TEXT_MESSAGE_* events are emitted for a plain text response."""
    from webapp.backend.ws_handler import _run_agent_agui
    from webapp.backend.session import Session

    ws = AsyncMock()
    session = Session(session_id="test-session")
    fake_events = _make_stream_events(["Hello", " world"])
    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__enter__ = MagicMock(return_value=iter(fake_events))
    mock_stream_ctx.__exit__ = MagicMock(return_value=False)
    mock_client = MagicMock()
    mock_client.messages.stream.return_value = mock_stream_ctx

    with patch("webapp.backend.ws_handler.anthropic") as mock_anthropic:
        mock_anthropic.Anthropic.return_value = mock_client
        await _run_agent_agui(ws, session, "Hi", "test-session", executor=None)

    sent_types = [c.args[0]["type"] for c in ws.send_json.call_args_list]
    assert "RUN_STARTED" in sent_types
    assert "TEXT_MESSAGE_START" in sent_types
    assert "TEXT_MESSAGE_CONTENT" in sent_types
    assert "TEXT_MESSAGE_END" in sent_types
    assert "RUN_FINISHED" in sent_types
    content_calls = [c.args[0] for c in ws.send_json.call_args_list
                     if c.args[0]["type"] == "TEXT_MESSAGE_CONTENT"]
    tokens = [c["payload"]["delta"] for c in content_calls]
    assert "Hello" in tokens and " world" in tokens


@pytest.mark.asyncio
async def test_agui_tool_call_set_viewport():
    """TOOL_CALL_* events are emitted and viewport state is updated."""
    from webapp.backend.ws_handler import _run_agent_agui
    from webapp.backend.session import Session

    ws = AsyncMock()
    session = Session(session_id="test-session")
    tool_payload = {"chrom": "chr1", "start": 1000000, "end": 2000000}
    fake_events = _make_stream_events(
        ["Navigating."],
        tool_calls=[{"id": "tc_1", "name": "set_viewport", "input": tool_payload}],
    )
    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__enter__ = MagicMock(return_value=iter(fake_events))
    mock_stream_ctx.__exit__ = MagicMock(return_value=False)
    mock_client = MagicMock()
    mock_client.messages.stream.return_value = mock_stream_ctx

    with patch("webapp.backend.ws_handler.anthropic") as mock_anthropic:
        mock_anthropic.Anthropic.return_value = mock_client
        await _run_agent_agui(ws, session, "Go to chr1 1M-2M", "test-session", executor=None)

    sent = [c.args[0] for c in ws.send_json.call_args_list]
    sent_types = [e["type"] for e in sent]
    assert "TOOL_CALL_START" in sent_types
    assert "TOOL_CALL_ARGS" in sent_types
    assert "TOOL_CALL_END" in sent_types
    assert "agent_viewport_update" in sent_types
    assert session.viewport.chrom == "chr1"
    assert session.viewport.start == 1000000
    assert session.viewport.end == 2000000
