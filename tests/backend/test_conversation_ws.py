import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from webapp.backend.conversation_store import ConversationStore
from webapp.backend.session import Session
from webapp.backend.ws_handler import handle_message


def _store(tmp_path: Path) -> ConversationStore:
    return ConversationStore(tmp_path / "history.sqlite3")


@pytest.mark.asyncio
async def test_conversation_request_snapshot_sends_transcript_and_views(tmp_path: Path):
    store = _store(tmp_path)
    conversation_id = store.create_conversation(title="Existing", data_path="/data/a.h5cd")
    user = store.append_message(conversation_id, "user", "hello")
    assistant = store.append_message(conversation_id, "assistant", "hi")
    store.append_event(
        conversation_id,
        assistant["id"],
        "tool_call_result",
        {
            "tool_use_id": "tool-1",
            "tool_name": "render_gosling",
            "status": "ok",
            "summary": "Rendered",
        },
    )
    store.save_view_snapshot(
        conversation_id,
        [{"view_id": "v1", "view_type": "gosling", "state": {"spec": {}}, "revision": 1}],
    )

    ws = AsyncMock()
    session = Session(session_id=conversation_id)
    session.conversation_store = store
    session.conversation_id = conversation_id

    await handle_message(
        ws,
        session,
        {"type": "conversation.request_snapshot", "payload": {}},
        MagicMock(),
    )

    sent = ws.send_json.call_args[0][0]
    assert sent["type"] == "conversation.snapshot"
    assert sent["conversation"]["id"] == conversation_id
    assert [m["id"] for m in sent["messages"]] == [user["id"], assistant["id"]]
    assert sent["messages"][1]["events"][0]["payload"]["tool_name"] == "render_gosling"
    assert sent["views"][0]["view_id"] == "v1"


@pytest.mark.asyncio
async def test_conversation_load_replaces_session_context_and_views(tmp_path: Path):
    store = _store(tmp_path)
    conversation_id = store.create_conversation(title="Load me", data_path="/data/b.h5cd")
    store.append_message(conversation_id, "user", "first")
    store.append_message(conversation_id, "assistant", "second")
    store.save_view_snapshot(
        conversation_id,
        [{"view_id": "loaded-view", "view_type": "gosling", "state": {"spec": {"x": 1}}}],
    )

    ws = AsyncMock()
    session = Session(session_id="old")
    session.conversation_store = store
    session.conversation_id = "old"
    session.conversation_history = [{"role": "user", "content": "old"}]

    await handle_message(
        ws,
        session,
        {"type": "conversation.load", "payload": {"conversation_id": conversation_id}},
        MagicMock(),
    )

    sent = ws.send_json.call_args[0][0]
    assert sent["type"] == "conversation.snapshot"
    assert session.conversation_id == conversation_id
    assert session.session_id == conversation_id
    assert session.h5cd_path == "/data/b.h5cd"
    assert session.conversation_history == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "second"},
    ]
    assert list(session.views) == ["loaded-view"]
    assert sent["views"][0]["view_id"] == "loaded-view"


@pytest.mark.asyncio
async def test_user_message_persists_transcript_before_agent_loop(tmp_path: Path):
    store = _store(tmp_path)
    conversation_id = store.create_conversation(title="Live")
    ws = AsyncMock()
    session = Session(session_id=conversation_id)
    session.conversation_store = store
    session.conversation_id = conversation_id

    with patch("webapp.backend.ws_handler.run_agent_loop") as mock_agent:
        mock_agent.return_value = asyncio.Future()
        mock_agent.return_value.set_result(None)

        await handle_message(
            ws,
            session,
            {"type": "user_message", "payload": {"text": "show chr1"}},
            MagicMock(),
        )

    snapshot = store.get_snapshot(conversation_id)
    assert snapshot["messages"][0]["role"] == "user"
    assert snapshot["messages"][0]["content"] == "show chr1"
    assert session.ui_messages[0]["id"] == snapshot["messages"][0]["id"]
    mock_agent.assert_called_once()
    sent_types = [call.args[0]["type"] for call in ws.send_json.call_args_list]
    assert "conversation.updated" in sent_types


@pytest.mark.asyncio
async def test_conversation_new_creates_clean_session(tmp_path: Path):
    store = _store(tmp_path)
    old_id = store.create_conversation(title="Old")
    store.append_message(old_id, "user", "old")

    ws = AsyncMock()
    session = Session(session_id=old_id)
    session.conversation_store = store
    session.conversation_id = old_id
    session.conversation_history = [{"role": "user", "content": "old"}]

    await handle_message(
        ws,
        session,
        {"type": "conversation.new", "payload": {}},
        MagicMock(),
    )

    sent = ws.send_json.call_args[0][0]
    assert sent["type"] == "conversation.snapshot"
    assert sent["conversation"]["id"] != old_id
    assert sent["messages"] == []
    assert session.conversation_history == []
    assert session.ui_messages == []


@pytest.mark.asyncio
async def test_text_artifact_can_be_persisted_to_transcript(tmp_path: Path):
    from webapp.backend.ws_handler import persist_text_artifact

    store = _store(tmp_path)
    conversation_id = store.create_conversation(title="Artifact")
    session = Session(session_id=conversation_id)
    session.conversation_store = store
    session.conversation_id = conversation_id

    persist_text_artifact(session, "Data loaded: example.h5cd")

    snapshot = store.get_snapshot(conversation_id)
    assert snapshot["messages"][0]["role"] == "assistant"
    assert snapshot["messages"][0]["content"] == "Data loaded: example.h5cd"


def test_rest_conversation_endpoints_list_and_load(tmp_path: Path, monkeypatch):
    from fastapi.testclient import TestClient
    import webapp.backend.main as main

    store = _store(tmp_path)
    conversation_id = store.create_conversation(title="REST", data_path="/data/rest.h5cd")
    store.append_message(conversation_id, "user", "hello rest")
    monkeypatch.setattr(main, "conversation_store", store)

    client = TestClient(main.app)

    listing = client.get("/api/conversations")
    assert listing.status_code == 200
    assert listing.json()["conversations"][0]["id"] == conversation_id

    loaded = client.get(f"/api/conversations/{conversation_id}")
    assert loaded.status_code == 200
    assert loaded.json()["messages"][0]["content"] == "hello rest"


def test_ws_connect_hydrates_existing_persistent_conversation(tmp_path: Path, monkeypatch):
    from fastapi.testclient import TestClient
    import webapp.backend.main as main

    store = _store(tmp_path)
    conversation_id = store.create_conversation(title="Reconnect")
    store.append_message(conversation_id, "user", "remember me")
    monkeypatch.setattr(main, "conversation_store", store)
    main.sessions.pop(conversation_id, None)

    client = TestClient(main.app)
    with client.websocket_connect(f"/ws/main?conversation_id={conversation_id}") as ws:
        ws.send_json({"type": "conversation.request_snapshot", "payload": {}})
        data = ws.receive_json()
        while data["type"] != "conversation.snapshot":
            data = ws.receive_json()

    assert data["type"] == "conversation.snapshot"
    assert data["conversation"]["id"] == conversation_id
    assert data["messages"][0]["content"] == "remember me"


@pytest.mark.asyncio
async def test_conversation_load_clears_views_when_snapshot_has_none(tmp_path: Path):
    store = _store(tmp_path)
    conversation_id = store.create_conversation(title="No views")
    store.append_message(conversation_id, "user", "plain chat")

    ws = AsyncMock()
    session = Session(session_id="old")
    session.conversation_store = store
    session.get_or_create_view("stale", "gosling").replace({"spec": {"stale": True}})

    await handle_message(
        ws,
        session,
        {"type": "conversation.load", "payload": {"conversation_id": conversation_id}},
        MagicMock(),
    )

    assert session.views == {}
