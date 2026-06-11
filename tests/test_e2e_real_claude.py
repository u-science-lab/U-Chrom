"""
Real E2E tests — calls the actual Claude API via a real async WebSocket connection.

Uses anyio + httpx to run a real uvicorn server so that asyncio.create_task()
inside ws_handler.py actually executes (unlike TestClient which uses a sync portal).

Requires:
  ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN — Claude API key
  ANTHROPIC_BASE_URL                        — proxy base URL (optional)

Run:
  ANTHROPIC_API_KEY=$ANTHROPIC_AUTH_TOKEN \\
  ANTHROPIC_BASE_URL=$ANTHROPIC_BASE_URL \\
  .test-venv/bin/pytest tests/test_e2e_real_claude.py -v -s --timeout=120
"""
import asyncio
import json
import os
import time

import pytest
import pytest_asyncio
import anyio

# Skip if no API key
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
pytestmark = [
    pytest.mark.skipif(
        not ANTHROPIC_API_KEY,
        reason="No ANTHROPIC_API_KEY set — skipping real Claude E2E tests",
    ),
    pytest.mark.anyio,
]

# ──────────────────────────────────────────────
# Server lifecycle — spin up uvicorn for the duration of the test session
# ──────────────────────────────────────────────

import threading
import uvicorn
from webapp.backend.main import app as _app

_SERVER_HOST = "127.0.0.1"
_SERVER_PORT = 18765
_WS_URL = f"ws://{_SERVER_HOST}:{_SERVER_PORT}/ws/main"


@pytest.fixture(scope="session", autouse=True)
def live_server():
    """Start a real uvicorn server once for all E2E tests."""
    config = uvicorn.Config(
        _app,
        host=_SERVER_HOST,
        port=_SERVER_PORT,
        log_level="error",
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait until server is ready
    import socket
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            s = socket.create_connection((_SERVER_HOST, _SERVER_PORT), timeout=0.5)
            s.close()
            break
        except OSError:
            time.sleep(0.1)
    else:
        pytest.fail("uvicorn server did not start in 10s")

    yield

    server.should_exit = True
    thread.join(timeout=5)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

TIMEOUT = 60  # seconds per test


async def ws_exchange(messages_to_send: list[dict], timeout: float = TIMEOUT) -> list[dict]:
    """
    Connect to the live WebSocket server, send all messages, collect responses
    until the agent's final 'agent_message' arrives or timeout.

    Current protocol: the agent sends tool-call 'agent_artifact' messages during
    the loop and a single final 'agent_message' {type, text} when it finishes a
    turn (no token streaming). We treat the agent_message as the completion
    signal and collect a short tail afterwards for any trailing artifacts.
    """
    import websockets

    received = []
    async with websockets.connect(_WS_URL) as ws:
        for msg in messages_to_send:
            await ws.send(json.dumps(msg))

        done = False
        deadline = time.time() + timeout
        extra_deadline = None  # set after final message to collect trailing msgs

        while True:
            now = time.time()
            limit = extra_deadline if extra_deadline else deadline
            remaining = limit - now
            if remaining <= 0:
                break
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 5.0))
                msg = json.loads(raw)
                received.append(msg)

                # The final assistant turn is a single agent_message with text.
                if msg.get("type") == "agent_message" and not done:
                    extra_deadline = time.time() + 3
                    done = True

                if msg.get("type") in ("run_finished", "run_error"):
                    break
            except asyncio.TimeoutError:
                if done:
                    break
                continue

    return received


def full_text(msgs: list[dict]) -> str:
    """Concatenate all assistant text. Current protocol emits one (or more)
    'agent_message' frames carrying a top-level 'text' field."""
    return "".join(
        m.get("text", "")
        for m in msgs
        if m.get("type") == "agent_message" and isinstance(m.get("text"), str)
    )


def by_type(msgs: list[dict], type_name: str) -> list[dict]:
    return [m for m in msgs if m.get("type") == type_name]


def agent_msg(text: str, session_id: str = "e2e-test") -> dict:
    # Current protocol uses 'user_message' with payload.text.
    return {"type": "user_message", "payload": {"text": text, "session_id": session_id}}


# ──────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────


class TestRealClaudeBasic:
    """Basic connectivity and response format tests."""

    async def test_agent_returns_text_response(self):
        """Claude should respond to a simple greeting with non-empty text."""
        msgs = await ws_exchange([agent_msg("Say exactly: HELLO_UCHROM", "e2e-basic-1")])
        text = full_text(msgs)
        assert len(text) > 0, f"No text response. Messages: {msgs[:5]}"
        assert "HELLO_UCHROM" in text, f"Expected HELLO_UCHROM.\nGot: {text[:300]}"

    async def test_agent_token_stream_structure(self):
        """The assistant turn arrives as agent_message frames with a 'text' field."""
        msgs = await ws_exchange([agent_msg("Reply with one word: OK", "e2e-stream-1")])
        agent_msgs = by_type(msgs, "agent_message")
        assert len(agent_msgs) > 0, f"No agent_message received. Messages: {msgs[:5]}"
        for m in agent_msgs:
            assert "text" in m and isinstance(m["text"], str)

    async def test_done_flag_arrives(self):
        """A final agent_message with non-empty text should arrive to mark turn end."""
        msgs = await ws_exchange([agent_msg("Reply with one word: DONE_TEST", "e2e-done-1")])
        agent_msgs = [m for m in by_type(msgs, "agent_message") if m.get("text")]
        assert len(agent_msgs) > 0, f"No final agent_message received.\nMessages: {msgs}"


class TestRealClaudeNavigation:
    """Test that Claude responds to navigation requests.

    The legacy `<action>` tag + `agent_viewport_update` protocol was removed;
    the current agent navigates by emitting a Gosling spec via the
    render_gosling tool (an 'agent_artifact' message) and/or describing the
    region in its text reply.
    """

    async def test_navigation_request_produces_response(self):
        """Asking to navigate should yield an artifact or a text response."""
        msgs = await ws_exchange([
            agent_msg("Navigate to chr15:30000000-60000000", "e2e-nav-1")
        ])
        text = full_text(msgs)
        artifacts = by_type(msgs, "agent_artifact")

        assert len(artifacts) > 0 or len(text) > 0, (
            f"Expected an artifact or text response.\n"
            f"Full text: {text[:500]}\n"
            f"Messages: {[m.get('type') for m in msgs]}"
        )

    async def test_navigation_mentions_region(self):
        """A navigation reply should reference the requested chromosome."""
        msgs = await ws_exchange([
            agent_msg("Show me the region chr1:1000000-5000000 please", "e2e-nav-2")
        ])
        text = full_text(msgs)
        artifacts = by_type(msgs, "agent_artifact")
        # Either it rendered something, or it acknowledged chr1 in text.
        assert len(artifacts) > 0 or "chr1" in text.lower(), (
            f"Expected chr1 reference or an artifact.\nText: {text[:400]}"
        )


class TestRealClaudeCodeExecution:
    """Test that Claude runs Python via the add_notebook_cell tool.

    The legacy `emit_artifact(...)` worker protocol was removed; code now runs
    through the Jupyter kernel via the add_notebook_cell tool, which emits a
    'notebook_cell' agent_artifact.
    """

    async def test_python_code_executed_via_notebook_cell(self):
        """Asking for a computation should produce a notebook_cell artifact or text."""
        msgs = await ws_exchange([
            agent_msg(
                "Use the notebook to compute 6 * 7 and show me the result.",
                "e2e-code-1",
            )
        ], timeout=90)

        text = full_text(msgs)
        artifacts = by_type(msgs, "agent_artifact")
        notebook_cells = [a for a in artifacts if a.get("artifact_type") == "notebook_cell"]
        all_types = [m.get("type") for m in msgs]

        assert len(notebook_cells) > 0 or len(artifacts) > 0 or "42" in text, (
            f"Expected a notebook_cell artifact, any artifact, or '42' in text.\n"
            f"Text: {text[:400]}\nMessages: {all_types}"
        )

    async def test_notebook_cell_artifact_shape(self):
        """When a notebook_cell artifact is emitted it should carry code/output."""
        msgs = await ws_exchange([
            agent_msg(
                "Run this in the notebook: print('TEST_ARTIFACT_OUTPUT')",
                "e2e-artifact-1",
            )
        ], timeout=90)

        text = full_text(msgs)
        artifacts = by_type(msgs, "agent_artifact")
        notebook_cells = [a for a in artifacts if a.get("artifact_type") == "notebook_cell"]

        # If it used the notebook tool, the artifact carries a content payload.
        if notebook_cells:
            content = notebook_cells[0].get("content", {})
            assert "code" in content or "output" in content, f"Bad cell shape: {content}"
        else:
            # Otherwise it should at least have responded with text or some artifact.
            assert len(artifacts) > 0 or len(text) > 0, (
                f"Expected an artifact or text.\nMessages: {[m.get('type') for m in msgs]}"
            )


class TestRealClaudeConversation:
    """Test multi-turn conversation continuity."""

    async def test_multi_turn_context(self):
        """Claude should remember context across multiple messages in the same session."""
        import websockets

        session_id = "e2e-multi-turn-1"
        received = []

        async with websockets.connect(_WS_URL) as ws:
            # First turn
            await ws.send(json.dumps(agent_msg("Remember the word XYZZY for me.", session_id)))
            await _collect_until_done(ws, received, timeout=30)

            # Second turn
            await ws.send(json.dumps(agent_msg("What word did I ask you to remember?", session_id)))
            await _collect_until_done(ws, received, timeout=30)

        text = full_text(received)
        assert "XYZZY" in text, f"Claude forgot context.\nFull text: {text[:500]}"


async def _collect_until_done(ws, received: list, timeout: float = 30):
    """Collect messages until the final agent_message (turn end) or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 5.0))
            msg = json.loads(raw)
            received.append(msg)
            if msg.get("type") == "agent_message" and msg.get("text"):
                return
        except asyncio.TimeoutError:
            continue


class TestRealClaudeErrorHandling:
    """Test graceful handling of edge cases."""

    async def test_empty_message_handled(self):
        """Empty text should not crash the backend."""
        msgs = await ws_exchange([agent_msg("", "e2e-empty-1")], timeout=30)
        # Should get some response (even if just done=True with empty text)
        assert len(msgs) > 0, "No messages received for empty input"

    async def test_unknown_ws_type_returns_error(self):
        """Unknown message types should return an error, not crash."""
        import websockets
        async with websockets.connect(_WS_URL) as ws:
            await ws.send(json.dumps({"type": "nonexistent_type", "payload": {}}))
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                msg = json.loads(raw)
                assert msg.get("type") == "error", f"Expected error, got: {msg}"
            except asyncio.TimeoutError:
                pytest.fail("No response to unknown message type")
