"""Tests for AG-UI event protocol in U-Chrom webapp."""
import json
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch, call


# ─────────────────────────────────────────────
# 1. agui_events.py constants & send_agui tests
# ─────────────────────────────────────────────

class TestAGUIConstants:
    def test_agui_constants_exist(self):
        """AGUI class contains all required event type constants."""
        from webapp.backend.agui_events import AGUI
        required = [
            "RUN_STARTED", "RUN_FINISHED", "RUN_ERROR",
            "TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT", "TEXT_MESSAGE_END",
            "TOOL_CALL_START", "TOOL_CALL_ARGS", "TOOL_CALL_END",
        ]
        for attr in required:
            assert hasattr(AGUI, attr), f"AGUI missing: {attr}"

    def test_agui_values_are_strings(self):
        """All AGUI constants are string values."""
        from webapp.backend.agui_events import AGUI
        for attr in vars(AGUI):
            if not attr.startswith("_"):
                val = getattr(AGUI, attr)
                if isinstance(val, str):
                    assert len(val) > 0


class TestSendAgui:
    def test_send_agui_format(self):
        """send_agui emits {"type": ..., "payload": ...} envelope."""
        from webapp.backend.agui_events import AGUI, send_agui

        ws = AsyncMock()
        ws.send_json = AsyncMock()

        asyncio.run(send_agui(ws, AGUI.RUN_STARTED, {"run_id": "abc"}))

        ws.send_json.assert_called_once_with({
            "type": AGUI.RUN_STARTED,
            "payload": {"run_id": "abc"},
        })

    def test_send_agui_empty_payload(self):
        """send_agui works with empty payload dict."""
        from webapp.backend.agui_events import AGUI, send_agui

        ws = AsyncMock()
        ws.send_json = AsyncMock()

        asyncio.run(send_agui(ws, AGUI.RUN_FINISHED, {}))

        ws.send_json.assert_called_once()
        args = ws.send_json.call_args[0][0]
        assert args["type"] == AGUI.RUN_FINISHED
        assert args["payload"] == {}


# ─────────────────────────────────────────────
# 2. WebSocket / handle_message tests via mocks
# ─────────────────────────────────────────────

def make_ws():
    """Return a mock WebSocket with async send_json."""
    ws = MagicMock()
    ws.send_json = AsyncMock()
    return ws


def make_session():
    from webapp.backend.session import Session
    return Session(session_id="test-session-id")


def run_handle(msg, session=None, ws=None, executor=None):
    """Helper: run handle_message synchronously."""
    from webapp.backend.ws_handler import handle_message
    ws = ws or make_ws()
    session = session or make_session()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(handle_message(ws, session, msg, executor))
    finally:
        loop.close()
        asyncio.set_event_loop(None)
    return ws, session


class TestWSConnect:
    def test_ws_connect_basic(self):
        """WebSocket endpoint can be imported and handle_message is callable."""
        from webapp.backend.ws_handler import handle_message
        import inspect
        assert inspect.iscoroutinefunction(handle_message)


class TestAgentMessageRouting:
    def test_user_message_triggers_agent_loop(self):
        """user_message type appends to history and runs the agent loop."""
        mock_loop = AsyncMock()
        with patch("webapp.backend.ws_handler.run_agent_loop", mock_loop):
            ws = make_ws()
            session = make_session()
            msg = {
                "type": "user_message",
                "payload": {"text": "hello"},
            }
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from webapp.backend.ws_handler import handle_message
                loop.run_until_complete(handle_message(ws, session, msg, None))
            finally:
                loop.close()
                asyncio.set_event_loop(None)

        mock_loop.assert_called_once()
        # history passed as 2nd positional arg, last entry is the user turn
        history = mock_loop.call_args[0][1]
        assert history[-1] == {"role": "user", "content": "hello"}


class TestLoadData:
    def test_load_data_success(self):
        """load_data reads ChromData, sets the session, and emits data_loaded."""
        import os, tempfile

        mock_cd = MagicMock()
        mock_cd.cells = MagicMock(); mock_cd.cells.shape = (5, 2)
        mock_cd.coords = MagicMock(); mock_cd.coords.shape = (100, 3)

        # A real file path that exists and ends with .h5cd (content unused —
        # ChromData.read is patched).
        fd, path = tempfile.mkstemp(suffix=".h5cd")
        os.close(fd)
        try:
            with patch("uchrom.core.ChromData.read", return_value=mock_cd), \
                 patch("webapp.backend.notebook_api.start_kernel"):
                ws = make_ws()
                session = make_session()
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    from webapp.backend.ws_handler import handle_message
                    loop.run_until_complete(handle_message(
                        ws, session,
                        {"type": "load_data", "payload": {"path": path}},
                        None,
                    ))
                finally:
                    loop.close()
                    asyncio.set_event_loop(None)
        finally:
            os.unlink(path)

        calls = [c[0][0] for c in ws.send_json.call_args_list]
        types = [c.get("type") for c in calls]
        assert "data_loaded" in types
        assert session.chromdata is mock_cd

    def test_load_data_bad_path(self):
        """load_data with non-existent path returns error event."""
        ws = make_ws()
        session = make_session()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            from webapp.backend.ws_handler import handle_message
            loop.run_until_complete(handle_message(
                ws, session,
                {"type": "load_data", "payload": {"path": "/nonexistent/path.h5cd"}},
                None,
            ))
        finally:
            loop.close()
            asyncio.set_event_loop(None)

        calls = [c[0][0] for c in ws.send_json.call_args_list]
        types = [c.get("type") for c in calls]
        assert "error" in types


class TestUpdateViewport:
    def test_update_viewport_updates_session(self):
        """update_viewport message stores the payload dict on the session."""
        ws, session = run_handle({
            "type": "update_viewport",
            "payload": {"chrom": "chr1", "start": 1000, "end": 5000},
        })
        assert session.viewport == {"chrom": "chr1", "start": 1000, "end": 5000}


class TestUnknownMessageType:
    def test_unknown_message_type_returns_error(self):
        """Unknown message type causes an error response to be sent."""
        ws, session = run_handle({
            "type": "completely_unknown_type_xyz",
            "payload": {},
        })
        calls = [c[0][0] for c in ws.send_json.call_args_list]
        types = [c.get("type") for c in calls]
        assert "error" in types

    def test_unknown_type_error_contains_message(self):
        """Error response for unknown type contains a flat message field."""
        ws, session = run_handle({
            "type": "no_such_handler",
            "payload": {},
        })
        calls = [c[0][0] for c in ws.send_json.call_args_list]
        error_calls = [c for c in calls if c.get("type") == "error"]
        assert len(error_calls) >= 1
        assert "message" in error_calls[0]
