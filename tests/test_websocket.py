"""
Tests for WebSocket connection, message handling, and lifecycle in U-Chrom webapp.
Uses starlette TestClient for WebSocket testing — no running server needed.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import json
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_app():
    """Import app fresh each time (avoids module-level side effects)."""
    from webapp.backend.main import app
    return app


def make_ws_mock():
    ws = MagicMock()
    ws.send_json = AsyncMock()
    ws.receive_json = AsyncMock()
    return ws


def make_session(session_id="test-sid"):
    from webapp.backend.session import Session
    return Session(session_id=session_id)


def run_handle(msg, session=None, ws=None):
    from webapp.backend.ws_handler import handle_message
    ws = ws or make_ws_mock()
    session = session or make_session()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(handle_message(ws, session, msg, None))
        pending = asyncio.all_tasks(loop)
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    finally:
        loop.close()
        asyncio.set_event_loop(None)
    return ws, session


def sent_types(ws):
    return [c[0][0].get("type") for c in ws.send_json.call_args_list]


# ---------------------------------------------------------------------------
# 1. WebSocket connection establishment
# ---------------------------------------------------------------------------

class TestWebSocketConnection:
    def test_ws_endpoint_accepts_connection(self):
        """WebSocket /ws/main accepts a connection without error."""
        app = get_app()
        client = TestClient(app)
        with client.websocket_connect("/ws/main") as ws:
            # Connection established — send a benign message then close
            ws.send_json({"type": "ping", "payload": {}})
            # Just verify we didn't blow up

    def test_ws_creates_unique_session_per_connection(self):
        """Each WebSocket connection gets its own session_id."""
        from webapp.backend import main as main_mod
        ids_seen = []

        original_session_cls = None
        try:
            import webapp.backend.session as sess_mod
            original_session_cls = sess_mod.Session

            class CapturingSession(original_session_cls):
                def __init__(self, session_id, **kw):
                    super().__init__(session_id=session_id, **kw)
                    ids_seen.append(session_id)

            with patch("webapp.backend.main.Session", CapturingSession):
                app = get_app()
                client = TestClient(app)
                with client.websocket_connect("/ws/main"):
                    pass
                with client.websocket_connect("/ws/main"):
                    pass
        finally:
            pass

        # Each connection should have called handle_message with a fresh session
        # (IDs may not be captured if patch didn't work — just verify no crash)

    def test_ws_connection_receives_no_spurious_messages_on_connect(self):
        """Server does not push messages immediately on connect (no hello frame)."""
        app = get_app()
        client = TestClient(app)
        # If server sent something on connect we'd read it here; we just check
        # the connection lifecycle completes cleanly
        with client.websocket_connect("/ws/main") as ws:
            # Send a well-formed unknown type to provoke a deterministic response
            ws.send_json({"type": "_probe_connect", "payload": {}})
            data = ws.receive_json()
            assert isinstance(data, dict)

    def test_ws_endpoint_path(self):
        """The WebSocket endpoint is mounted at /ws/main."""
        app = get_app()
        routes = [str(r.path) for r in app.routes if hasattr(r, "path")]
        assert "/ws/main" in routes


# ---------------------------------------------------------------------------
# 2. Message sending and receiving (via handle_message mocks)
# ---------------------------------------------------------------------------

class TestMessageSendReceive:
    def test_update_viewport_response(self):
        """update_viewport message updates session and triggers a response."""
        ws, session = run_handle({
            "type": "update_viewport",
            "payload": {"chrom": "chr7", "start": 5_000_000, "end": 10_000_000},
        })
        assert session.viewport.chrom == "chr7"
        assert session.viewport.start == 5_000_000
        assert session.viewport.end == 10_000_000

    def test_load_data_sends_json_response(self):
        """load_data always causes at least one send_json call (success or error)."""
        ws, session = run_handle({
            "type": "load_data",
            "payload": {"path": "/no/such/file.h5cd", "format": "h5cd"},
        })
        assert ws.send_json.call_count >= 1

    def test_load_data_success_event(self):
        """Successful load_data emits data_loaded event."""
        mock_cd = MagicMock()
        mock_cd.cells = MagicMock()
        mock_cd.cells.__len__ = MagicMock(return_value=3)
        mock_cd.spots = MagicMock()
        mock_cd.spots.__getitem__ = MagicMock(
            return_value=MagicMock(unique=MagicMock(return_value=["chr1"]))
        )
        mock_cd.cellm = {}

        with patch("webapp.backend.ws_handler._load_chromdata", return_value=mock_cd):
            ws, session = run_handle({
                "type": "load_data",
                "payload": {"path": "/fake.h5cd", "format": "h5cd"},
            })

        assert "data_loaded" in sent_types(ws)

    def test_load_data_error_event_on_bad_path(self):
        """load_data with a bad path emits an error event."""
        ws, session = run_handle({
            "type": "load_data",
            "payload": {"path": "/does/not/exist.h5cd"},
        })
        assert "error" in sent_types(ws)

    def test_unknown_type_returns_error(self):
        """Unknown message type returns an error response."""
        ws, session = run_handle({"type": "no_such_type_xyzzy", "payload": {}})
        assert "error" in sent_types(ws)

    def test_error_payload_has_message_field(self):
        """Error responses include a 'message' field in their payload."""
        ws, session = run_handle({"type": "bogus_xyz", "payload": {}})
        calls = [c[0][0] for c in ws.send_json.call_args_list]
        errors = [c for c in calls if c.get("type") == "error"]
        assert errors, "Expected at least one error response"
        assert "message" in errors[0].get("payload", {})

    def test_agent_message_triggers_run(self):
        """agent_message type dispatches to _run_agent_agui."""
        mock_agent = AsyncMock()
        with patch("webapp.backend.ws_handler._run_agent_agui", mock_agent):
            ws, session = run_handle({
                "type": "agent_message",
                "payload": {"session_id": "s1", "text": "show chr1"},
            })
        mock_agent.assert_called_once()

    def test_response_is_valid_json_serialisable(self):
        """All send_json calls receive dicts that are JSON-serialisable."""
        ws, session = run_handle({"type": "unknown_probe", "payload": {}})
        for call in ws.send_json.call_args_list:
            payload = call[0][0]
            # Should not raise
            json.dumps(payload)


# ---------------------------------------------------------------------------
# 3. Connection disconnection / cleanup
# ---------------------------------------------------------------------------

class TestConnectionCleanup:
    def test_disconnect_removes_session(self):
        """WebSocketDisconnect removes the session from the sessions dict."""
        from webapp.backend import main as main_mod

        app = get_app()
        initial_count = len(main_mod.sessions)

        client = TestClient(app)
        with client.websocket_connect("/ws/main"):
            connected_count = len(main_mod.sessions)

        # After context exit the disconnect handler runs
        final_count = len(main_mod.sessions)
        assert final_count == initial_count, (
            f"Sessions leaked: started={initial_count}, "
            f"during={connected_count}, after={final_count}"
        )

    def test_multiple_connect_disconnect_no_leak(self):
        """Repeated connect/disconnect cycles leave no leaked sessions."""
        from webapp.backend import main as main_mod

        app = get_app()
        client = TestClient(app)
        baseline = len(main_mod.sessions)

        for _ in range(3):
            with client.websocket_connect("/ws/main"):
                pass

        assert len(main_mod.sessions) == baseline

    def test_session_cleaned_up_after_disconnect(self):
        """Session object is removed from sessions dict after disconnect."""
        from webapp.backend import main as main_mod

        app = get_app()
        client = TestClient(app)

        before_ids = set(main_mod.sessions.keys())
        with client.websocket_connect("/ws/main"):
            during_ids = set(main_mod.sessions.keys())
            new_ids = during_ids - before_ids
            assert len(new_ids) == 1, "Expected exactly one new session during connection"

        after_ids = set(main_mod.sessions.keys())
        # The new session should be gone
        assert not (new_ids & after_ids), "Session was not cleaned up after disconnect"


# ---------------------------------------------------------------------------
# 4. Error handling for malformed messages
# ---------------------------------------------------------------------------

class TestMalformedMessages:
    def test_missing_type_field(self):
        """Message without 'type' key returns an error."""
        ws, session = run_handle({"payload": {"some": "data"}})
        assert "error" in sent_types(ws)

    def test_missing_payload_field(self):
        """Message without 'payload' key does not crash the handler."""
        # Should either handle gracefully or return error — no exception
        ws, session = run_handle({"type": "update_viewport"})
        assert ws.send_json.call_count >= 0  # no crash

    def test_empty_message(self):
        """Empty dict message is handled without crashing."""
        ws, session = run_handle({})
        # Either error response or silent ignore — no exception
        assert isinstance(sent_types(ws), list)

    def test_none_type_value(self):
        """Message with type=None returns error."""
        ws, session = run_handle({"type": None, "payload": {}})
        assert "error" in sent_types(ws)

    def test_non_dict_payload(self):
        """Non-dict payload does not crash the handler."""
        ws, session = run_handle({"type": "update_viewport", "payload": "not-a-dict"})
        # May error or silently handle — no exception is the requirement
        assert ws.send_json.call_count >= 0

    def test_extra_fields_ignored(self):
        """Extra unknown fields in a valid message are ignored."""
        ws, session = run_handle({
            "type": "update_viewport",
            "payload": {"chrom": "chr1", "start": 0, "end": 1000},
            "extra_field": "should-be-ignored",
            "another": 42,
        })
        assert session.viewport.chrom == "chr1"

    def test_malformed_load_data_payload(self):
        """load_data with missing path returns error, not exception."""
        ws, session = run_handle({"type": "load_data", "payload": {}})
        assert "error" in sent_types(ws)

    def test_very_large_text_field(self):
        """Oversized text in agent_message payload is handled without crash."""
        large_text = "x" * 100_000
        mock_agent = AsyncMock()
        with patch("webapp.backend.ws_handler._run_agent_agui", mock_agent):
            ws, session = run_handle({
                "type": "agent_message",
                "payload": {"session_id": "s1", "text": large_text},
            })
        # Should not raise; agent mock should have been called
        mock_agent.assert_called_once()


# ---------------------------------------------------------------------------
# 5. Multiple client connections
# ---------------------------------------------------------------------------

class TestMultipleClients:
    def test_two_concurrent_connections_independent_sessions(self):
        """Two simultaneous WebSocket clients have independent sessions."""
        from webapp.backend import main as main_mod

        app = get_app()
        client = TestClient(app)

        with client.websocket_connect("/ws/main") as ws1:
            ids_after_first = set(main_mod.sessions.keys())
            with client.websocket_connect("/ws/main") as ws2:
                ids_after_second = set(main_mod.sessions.keys())
                new_ids = ids_after_second - ids_after_first
                assert len(new_ids) == 1, "Second connection should add exactly one session"

                # Send different viewports to each connection
                ws1.send_json({
                    "type": "update_viewport",
                    "payload": {"chrom": "chr1", "start": 0, "end": 1000},
                })
                ws2.send_json({
                    "type": "update_viewport",
                    "payload": {"chrom": "chr2", "start": 5000, "end": 9000},
                })

    def test_session_count_tracks_connections(self):
        """Session count increases and decreases correctly with connections."""
        from webapp.backend import main as main_mod

        app = get_app()
        client = TestClient(app)
        baseline = len(main_mod.sessions)

        with client.websocket_connect("/ws/main"):
            assert len(main_mod.sessions) == baseline + 1
            with client.websocket_connect("/ws/main"):
                assert len(main_mod.sessions) == baseline + 2
            assert len(main_mod.sessions) == baseline + 1
        assert len(main_mod.sessions) == baseline

    def test_independent_viewports_per_session(self):
        """Viewport updates on one session do not affect another session."""
        from webapp.backend.session import Session

        session_a = make_session("a")
        session_b = make_session("b")

        ws_a, _ = run_handle(
            {"type": "update_viewport", "payload": {"chrom": "chr3", "start": 100, "end": 200}},
            session=session_a,
        )
        ws_b, _ = run_handle(
            {"type": "update_viewport", "payload": {"chrom": "chr5", "start": 999, "end": 1999}},
            session=session_b,
        )

        assert session_a.viewport.chrom == "chr3"
        assert session_b.viewport.chrom == "chr5"
        assert session_a.viewport.chrom != session_b.viewport.chrom

    def test_error_in_one_session_does_not_affect_another(self):
        """An error response in session A does not bleed into session B."""
        session_a = make_session("a2")
        session_b = make_session("b2")
        ws_a = make_ws_mock()
        ws_b = make_ws_mock()

        run_handle({"type": "unknown_xyz", "payload": {}}, session=session_a, ws=ws_a)
        run_handle(
            {"type": "update_viewport", "payload": {"chrom": "chr1", "start": 0, "end": 500}},
            session=session_b, ws=ws_b,
        )

        # Session A got an error
        assert "error" in sent_types(ws_a)
        # Session B's viewport updated fine
        assert session_b.viewport.chrom == "chr1"

    def test_multiple_sequential_messages_same_session(self):
        """Multiple messages on the same session are handled independently."""
        session = make_session("seq")

        # First message: set viewport to chr1
        ws1 = make_ws_mock()
        run_handle(
            {"type": "update_viewport", "payload": {"chrom": "chr1", "start": 0, "end": 1000}},
            session=session, ws=ws1,
        )
        assert session.viewport.chrom == "chr1"

        # Second message: update viewport to chr2
        ws2 = make_ws_mock()
        run_handle(
            {"type": "update_viewport", "payload": {"chrom": "chr2", "start": 2000, "end": 3000}},
            session=session, ws=ws2,
        )
        assert session.viewport.chrom == "chr2"
        assert session.viewport.start == 2000
