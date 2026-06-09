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

        asyncio.get_event_loop().run_until_complete(
            send_agui(ws, AGUI.RUN_STARTED, {"run_id": "abc"})
        )

        ws.send_json.assert_called_once_with({
            "type": AGUI.RUN_STARTED,
            "payload": {"run_id": "abc"},
        })

    def test_send_agui_empty_payload(self):
        """send_agui works with empty payload dict."""
        from webapp.backend.agui_events import AGUI, send_agui

        ws = AsyncMock()
        ws.send_json = AsyncMock()

        asyncio.get_event_loop().run_until_complete(
            send_agui(ws, AGUI.RUN_FINISHED, {})
        )

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
    def test_agent_message_triggers_handler(self):
        """agent_message type triggers _run_agent_agui (via asyncio.create_task)."""
        mock_agent = AsyncMock()
        with patch("webapp.backend.ws_handler._run_agent_agui", mock_agent):
            ws = make_ws()
            session = make_session()
            msg = {
                "type": "agent_message",
                "payload": {"session_id": "s1", "text": "hello"},
            }
            # run_until_complete drives the coroutine but create_task needs event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from webapp.backend.ws_handler import handle_message
                loop.run_until_complete(handle_message(ws, session, msg, None))
                # Allow pending tasks to run
                pending = asyncio.all_tasks(loop)
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            finally:
                loop.close()
                asyncio.set_event_loop(None)

        mock_agent.assert_called_once()
        call_args = mock_agent.call_args
        # third positional arg is the text
        assert call_args[0][2] == "hello"


class TestLoadData:
    def test_load_data_success(self):
        """load_data with valid mock ChromData returns data_loaded event."""
        mock_cd = MagicMock()
        mock_cd.cells = MagicMock()
        mock_cd.cells.__len__ = MagicMock(return_value=5)
        mock_cd.spots = MagicMock()
        mock_cd.spots.__getitem__ = MagicMock(return_value=MagicMock(
            unique=MagicMock(return_value=["chr1", "chr2"])
        ))
        mock_cd.cellm = {}

        with patch("webapp.backend.ws_handler._load_chromdata", return_value=mock_cd):
            ws = make_ws()
            session = make_session()

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from webapp.backend.ws_handler import handle_message
                loop.run_until_complete(handle_message(
                    ws, session,
                    {"type": "load_data", "payload": {"path": "/fake/data.h5cd", "format": "h5cd"}},
                    None,
                ))
            finally:
                loop.close()
                asyncio.set_event_loop(None)

        # Check that a data_loaded message was sent
        calls = [c[0][0] for c in ws.send_json.call_args_list]
        types = [c.get("type") for c in calls]
        assert "data_loaded" in types

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
        """update_viewport message updates session.viewport."""
        ws, session = run_handle({
            "type": "update_viewport",
            "payload": {"chrom": "chr1", "start": 1000, "end": 5000},
        })
        assert session.viewport.chrom == "chr1"
        assert session.viewport.start == 1000
        assert session.viewport.end == 5000


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
        """Error payload for unknown type contains a message field."""
        ws, session = run_handle({
            "type": "no_such_handler",
            "payload": {},
        })
        calls = [c[0][0] for c in ws.send_json.call_args_list]
        error_calls = [c for c in calls if c.get("type") == "error"]
        assert len(error_calls) >= 1
        assert "message" in error_calls[0].get("payload", {})
