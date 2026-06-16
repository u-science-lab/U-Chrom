"""Versioned A2UI protocol handshake helpers."""

from __future__ import annotations

from typing import Any

A2UI_PROTOCOL_VERSION = "0.2"
A2UI_CAPABILITIES = (
    "json_patch",
    "view_snapshot",
    "interaction_wait",
    "snapshot_capture",
    "component_tree",
    "component_actions",
    "analysis_projection",
    "session_scoped_rest",
    "conversation_resume",
)


def build_protocol_handshake(session_id: str) -> dict[str, Any]:
    from .agent_tools import TOOLS

    return {
        "type": "a2ui.protocol",
        "protocol_version": A2UI_PROTOCOL_VERSION,
        # Compatibility alias for older frontend tests/clients created before
        # the contract named the protocol field explicitly.
        "version": A2UI_PROTOCOL_VERSION,
        "session_id": session_id,
        "capabilities": list(A2UI_CAPABILITIES),
        "tools": [tool["name"] for tool in TOOLS],
    }


def parse_client_hello(msg: dict[str, Any]) -> dict[str, Any] | None:
    if msg.get("type") != "protocol.hello":
        return None
    payload = msg.get("payload")
    if isinstance(payload, dict):
        source = payload
    else:
        source = msg
    requested = source.get("capabilities", [])
    if not isinstance(requested, list):
        requested = []
    shared = [cap for cap in requested if cap in A2UI_CAPABILITIES]
    return {
        "protocol_version": A2UI_PROTOCOL_VERSION,
        "version": A2UI_PROTOCOL_VERSION,
        "capabilities": shared,
    }
