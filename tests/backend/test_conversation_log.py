import json
from pathlib import Path

import pytest
from unittest.mock import patch

from webapp.backend.session import Session
from tests._agent_loop_harness import drive_loop, single_tool_then_done


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_append_conversation_event_writes_jsonl(tmp_path, monkeypatch):
    from webapp.backend.conversation_log import append_conversation_event

    monkeypatch.setenv("UCHROM_CONVERSATION_LOG", "1")
    monkeypatch.setenv("UCHROM_CONVERSATION_LOG_DIR", str(tmp_path))
    session = Session(session_id="session-abc")

    append_conversation_event(
        session,
        "user_message",
        {"text": "加载 chr1 数据"},
    )

    log_file = tmp_path / "session-abc.jsonl"
    assert log_file.exists()
    events = _read_jsonl(log_file)
    assert len(events) == 1
    assert events[0]["event"] == "user_message"
    assert events[0]["session_id"] == "session-abc"
    assert events[0]["payload"] == {"text": "加载 chr1 数据"}
    assert events[0]["timestamp"].endswith("Z")


def test_append_conversation_event_respects_disable_flag(tmp_path, monkeypatch):
    from webapp.backend.conversation_log import append_conversation_event

    monkeypatch.setenv("UCHROM_CONVERSATION_LOG", "0")
    monkeypatch.setenv("UCHROM_CONVERSATION_LOG_DIR", str(tmp_path))

    append_conversation_event(Session(session_id="disabled"), "user_message", {"text": "hi"})

    assert not list(tmp_path.glob("*.jsonl"))


def test_sanitize_for_log_summarizes_image_data_urls():
    from webapp.backend.conversation_log import sanitize_for_log

    raw = "data:image/png;base64," + ("a" * 5000)

    sanitized = sanitize_for_log({"content": [{"type": "image", "source": raw}]})

    image_source = sanitized["content"][0]["source"]
    assert image_source["kind"] == "data_url"
    assert image_source["media_type"] == "image/png"
    assert image_source["length"] == len(raw)
    assert "aaaa" not in json.dumps(sanitized)


def test_sanitize_for_log_truncates_large_tool_payloads():
    from webapp.backend.conversation_log import sanitize_for_log

    payload = {
        "tool": "render_gosling",
        "input": {
            "spec": {
                "tracks": [{"id": i, "values": list(range(50))} for i in range(25)],
                "description": "x" * 5000,
            }
        },
    }

    sanitized = sanitize_for_log(payload, max_string=80, max_items=3, max_depth=4)
    dumped = json.dumps(sanitized)

    assert len(dumped) < 1500
    assert "truncated" in dumped
    assert "x" * 500 not in dumped


@pytest.mark.asyncio
async def test_agent_loop_logs_tool_call_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("UCHROM_CONVERSATION_LOG", "1")
    monkeypatch.setenv("UCHROM_CONVERSATION_LOG_DIR", str(tmp_path))
    session = Session(session_id="agent-log")

    with patch(
        "webapp.backend.notebook_api.execute_code",
        return_value={"status": "ok", "output": "2", "error": None},
    ):
        await drive_loop(
            single_tool_then_done("add_notebook_cell", {"code": "1+1"}, tool_id="tool-1"),
            history=[{"role": "user", "content": "Run 1+1"}],
            session=session,
        )

    events = _read_jsonl(tmp_path / "agent-log.jsonl")
    event_names = [event["event"] for event in events]

    assert "agent_request" in event_names
    assert "assistant_message" in event_names
    assert "tool_call_start" in event_names
    assert "tool_call_result" in event_names

    tool_start = next(event for event in events if event["event"] == "tool_call_start")
    assert tool_start["payload"]["tool_use_id"] == "tool-1"
    assert tool_start["payload"]["tool_name"] == "add_notebook_cell"
    assert tool_start["payload"]["input"]["code"] == "1+1"

    tool_result = next(event for event in events if event["event"] == "tool_call_result")
    assert tool_result["payload"]["status"] == "ok"
    assert tool_result["payload"]["tool_use_id"] == "tool-1"
