from webapp.backend.a2ui_protocol import (
    A2UI_PROTOCOL_VERSION,
    A2UI_CAPABILITIES,
    build_protocol_handshake,
    parse_client_hello,
)
from webapp.backend.agent_tools import TOOLS
from fastapi.testclient import TestClient
from webapp.backend.main import app


def test_build_protocol_handshake_includes_version_capabilities_and_session():
    frame = build_protocol_handshake("session-1")

    assert frame["type"] == "a2ui.protocol"
    assert frame["protocol_version"] == "0.2"
    assert frame["version"] == A2UI_PROTOCOL_VERSION
    assert frame["session_id"] == "session-1"
    assert set(A2UI_CAPABILITIES).issubset(set(frame["capabilities"]))
    assert {
        "json_patch",
        "view_snapshot",
        "interaction_wait",
        "snapshot_capture",
        "component_tree",
        "component_actions",
        "analysis_projection",
        "session_scoped_rest",
    }.issubset(set(frame["capabilities"]))
    assert {tool["name"] for tool in TOOLS}.issubset(set(frame["tools"]))


def test_parse_client_hello_selects_shared_capabilities():
    hello = {
        "type": "protocol.hello",
        "protocol_version": A2UI_PROTOCOL_VERSION,
        "capabilities": ["session_scoped_rest", "unknown.future"],
    }

    parsed = parse_client_hello(hello)

    assert parsed["protocol_version"] == A2UI_PROTOCOL_VERSION
    assert parsed["capabilities"] == ["session_scoped_rest"]


def test_parse_client_hello_accepts_wrapped_ws_payload():
    parsed = parse_client_hello({
        "type": "protocol.hello",
        "payload": {
            "protocol_version": A2UI_PROTOCOL_VERSION,
            "capabilities": ["json_patch", "missing.future"],
        },
    })

    assert parsed["protocol_version"] == A2UI_PROTOCOL_VERSION
    assert parsed["capabilities"] == ["json_patch"]


def test_parse_client_hello_rejects_wrong_type():
    assert parse_client_hello({"type": "ping"}) is None


def test_ws_main_emits_protocol_handshake_on_connect():
    client = TestClient(app)
    with client.websocket_connect("/ws/main?session_id=proto-test") as ws:
        frame = ws.receive_json()

    assert frame["type"] == "a2ui.protocol"
    assert frame["protocol_version"] == A2UI_PROTOCOL_VERSION
    assert frame["session_id"] == "proto-test"
    assert "session_scoped_rest" in frame["capabilities"]
    assert "render_gosling" in frame["tools"]


def test_ws_protocol_hello_acknowledges_shared_capabilities():
    client = TestClient(app)
    with client.websocket_connect("/ws/main?session_id=proto-test") as ws:
        assert ws.receive_json()["type"] == "a2ui.protocol"
        ws.send_json({
            "type": "protocol.hello",
            "protocol_version": A2UI_PROTOCOL_VERSION,
            "capabilities": ["session_scoped_rest", "missing.future"],
        })
        data = ws.receive_json()

    assert data["type"] == "protocol.ready"
    assert data["protocol_version"] == A2UI_PROTOCOL_VERSION
    assert data["session_id"] == "proto-test"
    assert data["capabilities"] == ["session_scoped_rest"]
