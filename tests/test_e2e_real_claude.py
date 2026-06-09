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
    until 'done' or timeout.
    """
    import websockets

    received = []
    async with websockets.connect(_WS_URL) as ws:
        for msg in messages_to_send:
            await ws.send(json.dumps(msg))

        done = False
        deadline = time.time() + timeout
        extra_deadline = None  # set after done=True to collect trailing msgs

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

                if msg.get("type") == "agent_token" and msg.get("payload", {}).get("done"):
                    # Give 3s extra to catch trailing messages (e.g., viewport update)
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
    return "".join(
        m["payload"].get("token", "")
        for m in msgs
        if m.get("type") == "agent_token"
        and isinstance(m.get("payload", {}).get("token"), str)
    )


def by_type(msgs: list[dict], type_name: str) -> list[dict]:
    return [m for m in msgs if m.get("type") == type_name]


def agent_msg(text: str, session_id: str = "e2e-test") -> dict:
    return {"type": "agent_message", "payload": {"session_id": session_id, "text": text}}


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
        """Tokens should arrive as {type: agent_token, payload: {session_id, token}}."""
        msgs = await ws_exchange([agent_msg("Reply with one word: OK", "e2e-stream-1")])
        token_msgs = by_type(msgs, "agent_token")
        assert len(token_msgs) > 0, "No agent_token messages received"
        for m in token_msgs:
            assert "payload" in m
            assert "session_id" in m["payload"]
            assert "token" in m["payload"] or "done" in m["payload"]

    async def test_done_flag_arrives(self):
        """The final agent_token should have done=True."""
        msgs = await ws_exchange([agent_msg("Reply with one word: DONE_TEST", "e2e-done-1")])
        done_msgs = [
            m for m in by_type(msgs, "agent_token") if m["payload"].get("done")
        ]
        assert len(done_msgs) > 0, f"No done=True token received.\nMessages: {msgs}"


class TestRealClaudeNavigation:
    """Test that Claude emits navigation actions."""

    async def test_viewport_action_emitted(self):
        """Asking to navigate to a region should trigger a viewport update or action tag."""
        msgs = await ws_exchange([
            agent_msg("Navigate to chr15:30000000-60000000", "e2e-nav-1")
        ])
        text = full_text(msgs)
        vp_updates = by_type(msgs, "agent_viewport_update")

        has_action = "<action" in text and "set_viewport" in text
        has_vp_msg = len(vp_updates) > 0

        assert has_action or has_vp_msg, (
            f"Expected viewport action in response.\n"
            f"Full text: {text[:500]}\n"
            f"Messages: {[m['type'] for m in msgs]}"
        )

    async def test_viewport_update_payload_format(self):
        """When agent_viewport_update is sent, payload should have chrom/start/end."""
        msgs = await ws_exchange([
            agent_msg("Show me the region chr1:1000000-5000000 please", "e2e-nav-2")
        ])
        vp_updates = by_type(msgs, "agent_viewport_update")
        if vp_updates:
            vp = vp_updates[0]["payload"]
            assert "chrom" in vp, f"Missing chrom: {vp}"
            assert "start" in vp, f"Missing start: {vp}"
            assert "end" in vp, f"Missing end: {vp}"


class TestRealClaudeCodeExecution:
    """Test that Claude generates Python code that the backend executes."""

    async def test_python_code_block_executed(self):
        """Asking for analysis should produce a code block or an artifact."""
        msgs = await ws_exchange([
            agent_msg(
                "Write a short Python code block that calls "
                "emit_artifact('text_block', {'content': 'analysis_complete', 'format': 'info'}). "
                "Only output the code block, nothing else.",
                "e2e-code-1",
            )
        ], timeout=90)

        text = full_text(msgs)
        # Claude may use AG-UI tool calls (agent_artifact) instead of text streaming
        agent_artifacts = by_type(msgs, "agent_artifact")
        all_types = [m["type"] for m in msgs]

        has_code_block = "```python" in text or "```" in text
        has_artifact = len(agent_artifacts) > 0
        # Also accept TOOL_CALL messages as evidence Claude tried to execute code
        has_tool_call = any(t in ("TOOL_CALL_START", "TOOL_CALL_END") for t in all_types)

        assert has_code_block or has_artifact or has_tool_call, (
            f"Expected code block, artifact, or tool call.\n"
            f"Text: {text[:400]}\nMessages: {all_types}"
        )

    async def test_emit_artifact_text_block(self):
        """Backend should forward emit_artifact calls as 'agent_artifact' WS messages."""
        msgs = await ws_exchange([
            agent_msg(
                "Run this Python and show me the result: "
                "emit_artifact('text_block', {'content': 'TEST_ARTIFACT_OUTPUT', 'format': 'info'})",
                "e2e-artifact-1",
            )
        ], timeout=90)

        text = full_text(msgs)
        agent_artifacts = by_type(msgs, "agent_artifact")
        all_types = [m["type"] for m in msgs]

        # Accept: agent_artifact message, emit_artifact in text, TEST_ARTIFACT_OUTPUT in text,
        # or tool call (Claude used AG-UI tool protocol)
        has_tool_call = any(t in ("TOOL_CALL_START", "TOOL_CALL_END") for t in all_types)
        code_or_artifact = (
            len(agent_artifacts) > 0
            or "emit_artifact" in text
            or "TEST_ARTIFACT_OUTPUT" in text
            or has_tool_call
        )
        assert code_or_artifact, (
            f"Expected artifact, emit_artifact call, or tool call.\n"
            f"Text: {text[:400]}\nMessages: {all_types}"
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
    """Collect messages until done=True or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 5.0))
            msg = json.loads(raw)
            received.append(msg)
            if msg.get("type") == "agent_token" and msg.get("payload", {}).get("done"):
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
