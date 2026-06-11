"""
Integration tests for the U-Chrom backend pipeline.

Covers:
1. End-to-end flow: HTTP request → WebSocket → Agent pipeline → Response
2. Full message cycle through the system
3. Error handling and recovery across component boundaries
4. Multiple concurrent sessions/connections
5. State persistence across interactions
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import asyncio
import json
import pytest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

def get_app():
    from webapp.backend.main import app
    return app


def make_chromdata(n_spots=50, n_cells=2, chroms=None):
    """Create a minimal ChromData for testing."""
    from uchrom.core import ChromData
    if chroms is None:
        chroms = ["chr1"]
    spots_per_chrom = n_spots // len(chroms)
    rows = []
    for i in range(n_cells):
        for chrom in chroms:
            for j in range(spots_per_chrom):
                rows.append({
                    "chrom": chrom,
                    "start": j * 100_000,
                    "end": j * 100_000 + 100_000,
                    "trace_id": i * len(chroms) + chroms.index(chrom),
                    "cell_id": i,
                })
    spots = pd.DataFrame(rows)
    n_total = len(spots)
    coords = np.random.randn(n_total, 3).astype(np.float32)
    cells = pd.DataFrame(
        {"cell_type": ["TypeA"] * n_cells},
        index=list(range(n_cells)),
    )
    umap = np.random.randn(n_cells, 2).astype(np.float32)
    return ChromData(coords=coords, spots=spots, cells=cells, cellm={"umap": umap})


def make_session(session_id="integration-test-sid"):
    from webapp.backend.session import Session
    return Session(session_id=session_id)


def run_handle(msg, session=None, ws=None):
    """Synchronously drive handle_message."""
    from webapp.backend.ws_handler import handle_message
    if ws is None:
        ws = MagicMock()
        ws.send_json = AsyncMock()
    if session is None:
        session = make_session()
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


def sent_payloads(ws):
    return [c[0][0] for c in ws.send_json.call_args_list]


# ===========================================================================
# 1. End-to-end flow: WebSocket connection → message dispatch → response
# ===========================================================================

class TestEndToEndWebSocketFlow:
    def test_ws_endpoint_reachable(self):
        """WebSocket /ws/main accepts connections."""
        app = get_app()
        client = TestClient(app)
        with client.websocket_connect("/ws/main") as ws:
            ws.send_json({"type": "ping", "payload": {}})

    def test_unknown_message_returns_error(self):
        """Any unknown message type returns an error response over the socket."""
        app = get_app()
        client = TestClient(app)
        with client.websocket_connect("/ws/main") as ws:
            ws.send_json({"type": "__no_such_type__", "payload": {}})
            data = ws.receive_json()
            assert data["type"] == "error"
            # Current protocol: error frames carry a flat top-level "message".
            assert "message" in data

    def test_update_viewport_roundtrip(self):
        """update_viewport travels through the full dispatch path."""
        app = get_app()
        client = TestClient(app)
        with client.websocket_connect("/ws/main") as ws:
            ws.send_json({
                "type": "update_viewport",
                "payload": {"chrom": "chr3", "start": 1_000_000, "end": 5_000_000},
            })
            # update_viewport may or may not emit an ack; connection should stay alive
            ws.send_json({"type": "__probe__", "payload": {}})
            data = ws.receive_json()
            assert isinstance(data, dict)

    def test_load_data_bad_path_returns_error_frame(self):
        """load_data with a nonexistent path emits an error frame immediately."""
        app = get_app()
        client = TestClient(app)
        with client.websocket_connect("/ws/main") as ws:
            ws.send_json({
                "type": "load_data",
                "payload": {"path": "/no/such/file/ever.h5cd", "format": "h5cd"},
            })
            data = ws.receive_json()
            assert data["type"] == "error"

    def test_load_data_success_emits_data_loaded(self):
        """Successful load_data path emits data_loaded with expected fields."""
        cd = make_chromdata(chroms=["chr1", "chr2"])
        # Current impl reads via ChromData.read(abs_path) inline and skips the
        # os.path.exists check only for real files — patch both so a fake path
        # flows through to a successful load.
        with patch("os.path.exists", return_value=True), \
             patch("uchrom.core.ChromData.read", return_value=cd), \
             patch("webapp.backend.notebook_api.start_kernel", lambda: None):
            ws, session = run_handle({
                "type": "load_data",
                "payload": {"path": "/fake.h5cd", "format": "h5cd"},
            })
        types = sent_types(ws)
        assert "data_loaded" in types
        payloads = sent_payloads(ws)
        data_loaded = next(p for p in payloads if p.get("type") == "data_loaded")
        # Current protocol: flat fields n_cells / n_spots / path (no nested payload).
        assert "n_cells" in data_loaded
        assert "n_spots" in data_loaded


# ===========================================================================
# 2. Full message cycle through the system
# ===========================================================================

class TestFullMessageCycle:
    def test_load_then_viewport_then_agent(self):
        """Simulate a real usage sequence: load → viewport → agent query."""
        cd = make_chromdata()
        session = make_session("cycle-test")

        # Step 1: load data
        ws1 = MagicMock(); ws1.send_json = AsyncMock()
        with patch("os.path.exists", return_value=True), \
             patch("uchrom.core.ChromData.read", return_value=cd), \
             patch("webapp.backend.notebook_api.start_kernel", lambda: None):
            run_handle(
                {"type": "load_data", "payload": {"path": "/fake.h5cd", "format": "h5cd"}},
                session=session, ws=ws1,
            )
        assert "data_loaded" in sent_types(ws1)
        assert session.chromdata is not None

        # Step 2: update viewport — session state should update
        ws2 = MagicMock(); ws2.send_json = AsyncMock()
        run_handle(
            {"type": "update_viewport",
             "payload": {"chrom": "chr1", "start": 0, "end": 1_000_000}},
            session=session, ws=ws2,
        )
        assert session.viewport.chrom == "chr1"

        # Step 3: user_message dispatches to run_agent_loop without crashing
        mock_agent = AsyncMock()
        ws3 = MagicMock(); ws3.send_json = AsyncMock()
        with patch("webapp.backend.ws_handler.run_agent_loop", mock_agent):
            run_handle(
                {"type": "user_message",
                 "payload": {"text": "show compartments"}},
                session=session, ws=ws3,
            )
        mock_agent.assert_called_once()

    def test_multiple_messages_same_session(self):
        """Session retains accumulated state across multiple message dispatches."""
        session = make_session("multi-msg")

        for chrom, start, end in [("chr1", 0, 1e6), ("chr2", 5e6, 10e6), ("chrX", 0, 2e6)]:
            ws = MagicMock(); ws.send_json = AsyncMock()
            run_handle(
                {"type": "update_viewport",
                 "payload": {"chrom": chrom, "start": int(start), "end": int(end)}},
                session=session, ws=ws,
            )

        assert session.viewport.chrom == "chrX"
        assert session.viewport.start == 0
        assert session.viewport.end == int(2e6)

    def test_conversation_history_grows_with_agent_messages(self):
        """Each user_message appends user+assistant turns to conversation_history."""
        session = make_session("history-test")
        cd = make_chromdata()
        session.chromdata = cd

        # handle_message appends the user turn before calling run_agent_loop;
        # the agent loop appends the assistant turn. Simulate the latter.
        async def fake_agent(ws, history, session=None):
            history.append({"role": "assistant", "content": "ok"})

        for i in range(3):
            ws = MagicMock(); ws.send_json = AsyncMock()
            with patch("webapp.backend.ws_handler.run_agent_loop", fake_agent):
                run_handle(
                    {"type": "user_message",
                     "payload": {"text": f"query {i}"}},
                    session=session, ws=ws,
                )

        assert len(session.conversation_history) == 6  # 3 user + 3 assistant

    def test_http_and_ws_share_session_state(self):
        """HTTP endpoints see the same ChromData that was loaded via WebSocket."""
        import webapp.backend.data_api as _da
        cd = make_chromdata(n_cells=3, chroms=["chr1"])
        session = make_session("shared-state")
        session.chromdata = cd
        _da.current_session = session

        try:
            app = get_app()
            client = TestClient(app)
            r = client.get("/api/umap")
            assert r.status_code == 200
            body = r.json()
            assert len(body["points"]) == 3
        finally:
            _da.current_session = None


# ===========================================================================
# 3. Error handling and recovery across component boundaries
# ===========================================================================

class TestErrorHandlingAcrossBoundaries:
    def test_load_data_exception_propagates_as_error_frame(self):
        """If ChromData.read raises, the WS gets an error frame, not an unhandled crash."""
        def boom(path):
            raise RuntimeError("disk I/O failure")

        with patch("os.path.exists", return_value=True), \
             patch("uchrom.core.ChromData.read", side_effect=boom):
            ws, session = run_handle({
                "type": "load_data",
                "payload": {"path": "/fake.h5cd", "format": "h5cd"},
            })

        assert "error" in sent_types(ws)

    def test_agent_exception_does_not_kill_session(self):
        """If run_agent_loop raises, subsequent messages still work."""
        session = make_session("recovery-test")

        async def exploding_agent(ws, history, session=None):
            raise ValueError("LLM unavailable")

        ws1 = MagicMock(); ws1.send_json = AsyncMock()
        with patch("webapp.backend.ws_handler.run_agent_loop", exploding_agent):
            # The handler does not swallow agent exceptions itself; the WS loop
            # in main.py does. Emulate that boundary here.
            try:
                run_handle(
                    {"type": "user_message",
                     "payload": {"text": "boom"}},
                    session=session, ws=ws1,
                )
            except ValueError:
                pass

        # Session should still be usable — viewport update must work
        ws2 = MagicMock(); ws2.send_json = AsyncMock()
        run_handle(
            {"type": "update_viewport",
             "payload": {"chrom": "chr5", "start": 0, "end": 1_000_000}},
            session=session, ws=ws2,
        )
        assert session.viewport.chrom == "chr5"

    def test_malformed_payload_does_not_crash_server(self):
        """Payloads missing expected keys return an error, not an exception."""
        # update_viewport with missing keys
        ws, session = run_handle({"type": "update_viewport", "payload": {}})
        # Should not raise; either a no-op or an error frame
        assert isinstance(sent_types(ws), list)

    def test_load_data_missing_path_key(self):
        """load_data with no 'path' in payload returns error."""
        ws, session = run_handle({"type": "load_data", "payload": {}})
        assert "error" in sent_types(ws)

    def test_error_response_is_json_serializable(self):
        """Error frames are always JSON-serializable dicts."""
        ws, session = run_handle({"type": "__bad__", "payload": {}})
        for call in ws.send_json.call_args_list:
            frame = call[0][0]
            json.dumps(frame)  # must not raise

    def test_code_execution_runtime_error_returns_error_artifact(self):
        """Code that crashes returns an error status, not an uncaught exception."""
        from webapp.backend.notebook_api import start_kernel, execute_code
        start_kernel()
        result = execute_code("raise ValueError('oops')")
        assert result["status"] == "error"
        assert "ValueError" in (result.get("error") or "")

    def test_code_execution_sandbox_isolation(self):
        """Kernel state set in one execution is visible in the next (shared kernel).

        The current architecture uses a single persistent Jupyter kernel, so
        executions share a namespace by design (this is what powers multi-cell
        notebooks). Verify that documented behavior rather than the removed
        per-call worker isolation.
        """
        from webapp.backend.notebook_api import start_kernel, execute_code
        start_kernel()
        execute_code("shared_var = 'persists'")
        result = execute_code("print(shared_var)")
        assert result["status"] == "ok"
        assert "persists" in result["output"]

    def test_ws_connection_after_error_still_works(self):
        """After receiving an error, the WebSocket connection stays open."""
        app = get_app()
        client = TestClient(app)
        with client.websocket_connect("/ws/main") as ws:
            # Trigger an error
            ws.send_json({"type": "nonexistent_type_xyz", "payload": {}})
            err = ws.receive_json()
            assert err["type"] == "error"

            # Connection still usable
            ws.send_json({"type": "update_viewport",
                          "payload": {"chrom": "chr1", "start": 0, "end": 1_000_000}})
            # No crash = success; may or may not receive a frame

    def test_http_api_without_session_returns_graceful_error(self):
        """HTTP /api/umap without loaded data returns 404 or empty, not 500."""
        import webapp.backend.data_api as _da
        old = _da.current_session
        _da.current_session = None
        try:
            app = get_app()
            client = TestClient(app)
            r = client.get("/api/umap")
            assert r.status_code in (200, 404, 422)  # any graceful response
        finally:
            _da.current_session = old


# ===========================================================================
# 4. Multiple concurrent sessions / connections
# ===========================================================================

class TestConcurrentSessions:
    def test_two_independent_sessions_dont_share_viewport(self):
        """Two sessions maintain independent viewport state."""
        s1 = make_session("s1")
        s2 = make_session("s2")

        ws_a = MagicMock(); ws_a.send_json = AsyncMock()
        run_handle(
            {"type": "update_viewport",
             "payload": {"chrom": "chr1", "start": 0, "end": 1_000_000}},
            session=s1, ws=ws_a,
        )

        ws_b = MagicMock(); ws_b.send_json = AsyncMock()
        run_handle(
            {"type": "update_viewport",
             "payload": {"chrom": "chr5", "start": 5_000_000, "end": 10_000_000}},
            session=s2, ws=ws_b,
        )

        assert s1.viewport.chrom == "chr1"
        assert s2.viewport.chrom == "chr5"
        assert s1.viewport.start != s2.viewport.start

    def test_two_sessions_independent_chromdata(self):
        """Each session can load a different ChromData without cross-contamination."""
        cd1 = make_chromdata(chroms=["chr1"])
        cd2 = make_chromdata(chroms=["chrX", "chrY"])
        s1 = make_session("s-cd1")
        s2 = make_session("s-cd2")
        s1.chromdata = cd1
        s2.chromdata = cd2

        chroms1 = set(s1.chromdata.spots["chrom"].unique())
        chroms2 = set(s2.chromdata.spots["chrom"].unique())
        assert chroms1 == {"chr1"}
        assert chroms2 == {"chrX", "chrY"}
        assert chroms1.isdisjoint(chroms2)

    def test_two_sessions_independent_conversation_history(self):
        """Conversation history is per-session, not global."""
        s1 = make_session("hist-s1")
        s2 = make_session("hist-s2")

        # run_agent_loop receives the history list; the user turn is already
        # appended by handle_message before the call.
        async def recorder(ws, history, session=None):
            pass

        ws1 = MagicMock(); ws1.send_json = AsyncMock()
        with patch("webapp.backend.ws_handler.run_agent_loop", recorder):
            run_handle(
                {"type": "user_message",
                 "payload": {"text": "session one query"}},
                session=s1, ws=ws1,
            )

        ws2 = MagicMock(); ws2.send_json = AsyncMock()
        with patch("webapp.backend.ws_handler.run_agent_loop", recorder):
            run_handle(
                {"type": "user_message",
                 "payload": {"text": "session two query"}},
                session=s2, ws=ws2,
            )

        assert len(s1.conversation_history) == 1
        assert len(s2.conversation_history) == 1
        assert s1.conversation_history[0]["content"] == "session one query"
        assert s2.conversation_history[0]["content"] == "session two query"

    def test_parallel_agent_calls_complete_independently(self):
        """Two agent calls on different sessions each capture their own text."""
        captured = {}

        def run_one(sid, text):
            from webapp.backend.ws_handler import handle_message
            session = make_session(sid)
            seen = []

            async def fake_agent(ws, history, session=None):
                seen.append(history[-1]["content"])

            async def driver():
                ws = MagicMock(); ws.send_json = AsyncMock()
                with patch("webapp.backend.ws_handler.run_agent_loop", fake_agent):
                    await handle_message(
                        ws, session,
                        {"type": "user_message", "payload": {"text": text}},
                        None,
                    )
                    await asyncio.sleep(0.05)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(driver())
            finally:
                loop.close()
                asyncio.set_event_loop(None)
            return seen

        c1 = run_one("p1", "query alpha")
        c2 = run_one("p2", "query beta")

        assert c1 == ["query alpha"], f"Expected ['query alpha'], got {c1}"
        assert c2 == ["query beta"], f"Expected ['query beta'], got {c2}"

    def test_multiple_ws_connections_each_get_independent_response(self):
        """Each WebSocket connection gets its own error response for bad messages."""
        app = get_app()
        client = TestClient(app)
        responses = []
        for i in range(3):
            with client.websocket_connect("/ws/main") as ws:
                ws.send_json({"type": f"__bad_{i}__", "payload": {}})
                data = ws.receive_json()
                responses.append(data)

        assert all(r["type"] == "error" for r in responses)


# ===========================================================================
# 5. State persistence across interactions
# ===========================================================================

class TestStatePersistenceAcrossInteractions:
    def test_viewport_persists_across_messages(self):
        """Viewport set in one message is visible in subsequent messages."""
        session = make_session("persist-vp")

        run_handle(
            {"type": "update_viewport",
             "payload": {"chrom": "chrM", "start": 1000, "end": 5000}},
            session=session,
        )
        assert session.viewport.chrom == "chrM"

        # Send an unrelated message — viewport must not reset
        run_handle({"type": "__probe__", "payload": {}}, session=session)
        assert session.viewport.chrom == "chrM"
        assert session.viewport.start == 1000

    def test_chromdata_persists_after_load(self):
        """ChromData loaded into a session survives subsequent messages."""
        session = make_session("persist-cd")
        cd = make_chromdata()

        ws = MagicMock(); ws.send_json = AsyncMock()
        with patch("os.path.exists", return_value=True), \
             patch("uchrom.core.ChromData.read", return_value=cd), \
             patch("webapp.backend.notebook_api.start_kernel", lambda: None):
            run_handle(
                {"type": "load_data", "payload": {"path": "/f.h5cd", "format": "h5cd"}},
                session=session, ws=ws,
            )

        assert session.chromdata is not None
        n_spots_before = len(session.chromdata.spots)

        run_handle({"type": "update_viewport",
                    "payload": {"chrom": "chr1", "start": 0, "end": 1_000_000}},
                   session=session)

        assert session.chromdata is not None
        assert len(session.chromdata.spots) == n_spots_before

    def test_session_serializes_and_deserializes_state(self):
        """Session.to_dict / from_dict round-trip preserves viewport and conversation."""
        from webapp.backend.session import Session, Viewport
        session = make_session("roundtrip")
        session.viewport = Viewport(chrom="chr7", start=1_000_000, end=2_000_000)
        session.conversation_history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]

        d = session.to_dict()
        assert json.dumps(d)  # must be serializable

        restored = Session.from_dict(d, session_id="roundtrip")
        assert restored.viewport.chrom == "chr7"
        assert restored.viewport.start == 1_000_000
        assert len(restored.conversation_history) == 2

    def test_analysis_results_stored_in_session(self):
        """Analysis results dict accumulates across interactions."""
        session = make_session("analysis-persist")
        session.analysis_results["tads"] = {"chr1": [[0, 1_000_000]]}
        session.analysis_results["compartments"] = {"chr1": [0.1, -0.2]}

        assert "tads" in session.analysis_results
        assert "compartments" in session.analysis_results
        assert session.analysis_results["tads"]["chr1"] == [[0, 1_000_000]]

    def test_highlight_regions_accumulate(self):
        """Highlight regions persist and accumulate on the session."""
        session = make_session("highlights")
        for i in range(3):
            session.highlight_regions.append({
                "chrom": "chr1",
                "start": i * 1_000_000,
                "end": (i + 1) * 1_000_000,
                "color": "#ff0000",
                "label": f"Region {i}",
            })
        assert len(session.highlight_regions) == 3

    def test_code_execution_emits_artifacts_that_can_be_stored(self):
        """Code execution output can be collected and stored on the session."""
        from webapp.backend.notebook_api import start_kernel, execute_code
        start_kernel()
        result = execute_code("print('step 1 done'); 40 + 2")
        assert result["status"] == "ok"

        # The result dict is JSON-serializable and can be parked on the session.
        session = make_session("artifacts-persist")
        session.pending_artifacts.append({
            "artifact_type": "code_result",
            "payload": result,
        })
        assert len(session.pending_artifacts) == 1
        assert session.pending_artifacts[0]["artifact_type"] == "code_result"
        assert "42" in session.pending_artifacts[0]["payload"]["output"]

    def test_colormap_config_persists(self):
        """Colormap config set on the session is preserved across interactions."""
        session = make_session("colormap")
        session.colormap_config = {"scheme": "viridis", "property": "compartment"}

        # Simulate another message
        run_handle({"type": "__probe__", "payload": {}}, session=session)
        assert session.colormap_config is not None
        assert session.colormap_config["scheme"] == "viridis"

    def test_panels_persist_and_accumulate(self):
        """Panel configurations accumulate in session.panels."""
        session = make_session("panels")
        for i in range(4):
            session.panels.append({"type": "track_plot", "label": f"Panel {i}"})

        run_handle({"type": "update_viewport",
                    "payload": {"chrom": "chr1", "start": 0, "end": 1_000_000}},
                   session=session)

        assert len(session.panels) == 4
        assert session.panels[2]["label"] == "Panel 2"


# ===========================================================================
# 6. AG-UI event protocol integration
# ===========================================================================

class TestAGUIProtocolIntegration:
    def test_run_started_and_finished_events_emitted(self):
        """send_agui emits RUN_STARTED / RUN_FINISHED frames with the right type."""
        from webapp.backend.agui_events import AGUI, send_agui

        ws = MagicMock(); ws.send_json = AsyncMock()

        async def driver():
            await send_agui(ws, AGUI.RUN_STARTED, {"run_id": "r1"})
            await send_agui(ws, AGUI.RUN_FINISHED, {"run_id": "r1"})

        asyncio.run(driver())
        types = sent_types(ws)
        assert AGUI.RUN_STARTED in types
        assert AGUI.RUN_FINISHED in types

    def test_text_message_events_carry_content(self):
        """TEXT_MESSAGE_CONTENT frames carry the token text in their payload."""
        from webapp.backend.agui_events import AGUI, send_agui

        ws = MagicMock(); ws.send_json = AsyncMock()

        async def driver():
            await send_agui(ws, AGUI.TEXT_MESSAGE_START, {"message_id": "m1"})
            for token in ["Hello", " world", "!"]:
                await send_agui(ws, AGUI.TEXT_MESSAGE_CONTENT,
                                {"message_id": "m1", "delta": token})
            await send_agui(ws, AGUI.TEXT_MESSAGE_END, {"message_id": "m1"})

        asyncio.run(driver())
        payloads = sent_payloads(ws)
        content_events = [
            p for p in payloads if p.get("type") == AGUI.TEXT_MESSAGE_CONTENT
        ]
        assert len(content_events) == 3
        deltas = [e["payload"]["delta"] for e in content_events]
        assert "".join(deltas) == "Hello world!"

    def test_tool_call_events_emitted_for_code_execution(self):
        """TOOL_CALL_START / END frames are emitted around a tool call."""
        from webapp.backend.agui_events import AGUI, send_agui

        ws = MagicMock(); ws.send_json = AsyncMock()

        async def driver():
            await send_agui(ws, AGUI.TOOL_CALL_START,
                            {"tool_call_id": "tc1", "tool_name": "python"})
            await send_agui(ws, AGUI.TOOL_CALL_ARGS,
                            {"tool_call_id": "tc1", "delta": '{"code": "1+1"}'})
            await send_agui(ws, AGUI.TOOL_CALL_END, {"tool_call_id": "tc1"})

        asyncio.run(driver())
        types = sent_types(ws)
        assert AGUI.TOOL_CALL_START in types
        assert AGUI.TOOL_CALL_END in types


# ===========================================================================
# 7. HTTP API integration with session state
# ===========================================================================

class TestHTTPAPIIntegration:
    def setup_method(self):
        """Ensure clean session state before each test."""
        import webapp.backend.data_api as _da
        _da.current_session = None

    def teardown_method(self):
        import webapp.backend.data_api as _da
        _da.current_session = None

    def test_umap_endpoint_with_valid_session(self):
        """GET /api/umap returns cell coordinates when session has chromdata."""
        import webapp.backend.data_api as _da
        cd = make_chromdata(n_cells=4, chroms=["chr1"])
        session = make_session("umap-test")
        session.chromdata = cd
        _da.current_session = session

        app = get_app()
        client = TestClient(app)
        r = client.get("/api/umap")
        assert r.status_code == 200
        body = r.json()
        assert "points" in body
        assert len(body["points"]) == 4

    def test_coords_endpoint_returns_float32_binary(self):
        """GET /api/coords/<trace_id> returns binary float32 data."""
        import webapp.backend.data_api as _da
        cd = make_chromdata(n_spots=40, n_cells=1, chroms=["chr1"])
        session = make_session("coords-test")
        session.chromdata = cd
        _da.current_session = session

        app = get_app()
        client = TestClient(app)
        r = client.get("/api/coords/0")
        assert r.status_code == 200
        # Binary float32 triplets
        arr = np.frombuffer(r.content, dtype=np.float32).reshape(-1, 3)
        assert arr.ndim == 2
        assert arr.shape[1] == 3

    def test_umap_cell_types_in_response(self):
        """UMAP response includes cell_type for each point."""
        import webapp.backend.data_api as _da
        cd = make_chromdata(n_cells=2, chroms=["chr1"])
        session = make_session("umap-types")
        session.chromdata = cd
        _da.current_session = session

        app = get_app()
        client = TestClient(app)
        r = client.get("/api/umap")
        assert r.status_code == 200
        body = r.json()
        for pt in body["points"]:
            assert "cell_type" in pt
