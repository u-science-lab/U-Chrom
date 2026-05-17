"""End-to-end test: agent message → viewport update via <action> tag."""
import json
import re
import time
import pytest
from fastapi.testclient import TestClient
from webapp.backend.main import app

client = TestClient(app)


def test_action_parser():
    """Unit test for _parse_actions."""
    from webapp.backend.ws_handler import _parse_actions
    text = 'Sure! <action type="set_viewport">{"chrom":"chr15","start":30000000,"end":60000000}</action> Done.'
    actions = _parse_actions(text)
    assert len(actions) == 1
    assert actions[0]["action_type"] == "set_viewport"
    assert actions[0]["payload"]["chrom"] == "chr15"
    assert actions[0]["payload"]["start"] == 30_000_000


def test_action_parser_invalid_json():
    from webapp.backend.ws_handler import _parse_actions
    text = '<action type="set_viewport">not-json</action>'
    assert _parse_actions(text) == []


def test_agent_viewport_update_e2e():
    """
    Full flow: send agent_message asking to navigate to chr15 →
    Claude responds with <action type="set_viewport"> →
    backend pushes agent_viewport_update WebSocket message.
    """
    tokens = []
    viewport_updates = []

    with client.websocket_connect("/ws/main") as ws:
        ws.send_json({
            "type": "agent_message",
            "payload": {
                "session_id": "e2e-test",
                "text": "Navigate to chr15:30000000-60000000"
            }
        })

        deadline = time.time() + 45
        while time.time() < deadline:
            try:
                msg = ws.receive_json()
            except Exception:
                break

            if msg["type"] == "agent_token":
                tokens.append(msg["payload"].get("token", ""))
                if msg["payload"].get("done"):
                    break
            elif msg["type"] == "agent_viewport_update":
                viewport_updates.append(msg["payload"])

    full_text = "".join(tokens)
    assert len(full_text) > 0, "No response from agent"

    # Either Claude emitted the action (viewport_updates populated)
    # or the response contains the action tag (backend parses after stream ends)
    # The viewport update is sent after proc.wait(), so it arrives after done=True.
    # Re-check: collect one more message after done.
    assert len(viewport_updates) > 0 or "<action" in full_text, (
        f"Expected viewport update or action tag in response.\nResponse: {full_text[:500]}"
    )

    if viewport_updates:
        vp = viewport_updates[0]
        assert vp["chrom"] == "chr15"
        assert vp["start"] == 30_000_000
        assert vp["end"] == 60_000_000


def test_agent_viewport_update_collects_after_done():
    """
    Variant: collect messages including after done=True to catch
    agent_viewport_update which arrives after proc.wait().
    """
    viewport_updates = []
    done_seen = False

    with client.websocket_connect("/ws/main") as ws:
        ws.send_json({
            "type": "agent_message",
            "payload": {
                "session_id": "e2e-test-2",
                "text": "Show me chr15:30000000-60000000"
            }
        })

        deadline = time.time() + 45
        while time.time() < deadline:
            try:
                msg = ws.receive_json()
            except Exception:
                break

            if msg["type"] == "agent_token" and msg["payload"].get("done"):
                done_seen = True
                # Keep collecting for 2s after done to catch viewport update
                deadline = min(deadline, time.time() + 2)
            elif msg["type"] == "agent_viewport_update":
                viewport_updates.append(msg["payload"])
                break

    assert done_seen, "Agent never finished"
    assert len(viewport_updates) > 0, "No agent_viewport_update received after agent finished"
    vp = viewport_updates[0]
    assert vp["chrom"] == "chr15"
