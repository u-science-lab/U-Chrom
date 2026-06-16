from pathlib import Path


def test_conversation_store_round_trips_messages_events_and_views(tmp_path: Path):
    from webapp.backend.conversation_store import ConversationStore

    store = ConversationStore(tmp_path / "history.sqlite3")
    conversation_id = store.create_conversation(
        title="Load chr1",
        data_path="/data/example.h5cd",
    )

    user = store.append_message(conversation_id, "user", "加载 chr1 数据")
    assistant = store.append_message(conversation_id, "assistant", "我来加载。")
    store.append_event(
        conversation_id,
        assistant["id"],
        "tool_call_start",
        {
            "tool_use_id": "tool-1",
            "tool_name": "load_data",
        },
    )
    store.append_event(
        conversation_id,
        assistant["id"],
        "tool_call_result",
        {
            "tool_use_id": "tool-1",
            "tool_name": "load_data",
            "status": "ok",
            "summary": "Loaded example.h5cd",
        },
    )
    store.save_view_snapshot(
        conversation_id,
        [
            {
                "view_id": "view-1",
                "view_type": "gosling",
                "title": "Genome",
                "state": {"spec": {"tracks": []}},
                "revision": 2,
            }
        ],
    )

    snapshot = store.get_snapshot(conversation_id)

    assert snapshot["conversation"]["id"] == conversation_id
    assert snapshot["conversation"]["title"] == "Load chr1"
    assert snapshot["conversation"]["data_path"] == "/data/example.h5cd"
    assert [m["id"] for m in snapshot["messages"]] == [user["id"], assistant["id"]]
    assert snapshot["messages"][0]["role"] == "user"
    assert snapshot["messages"][0]["content"] == "加载 chr1 数据"
    assert snapshot["messages"][1]["role"] == "assistant"
    assert [e["type"] for e in snapshot["messages"][1]["events"]] == [
        "tool_call_start",
        "tool_call_result",
    ]
    assert snapshot["messages"][1]["events"][1]["payload"]["status"] == "ok"
    assert snapshot["views"][0]["view_id"] == "view-1"
    assert snapshot["views"][0]["state"]["spec"]["tracks"] == []

    summaries = store.list_conversations()
    assert len(summaries) == 1
    assert summaries[0]["id"] == conversation_id
    assert summaries[0]["title"] == "Load chr1"
    assert summaries[0]["data_path"] == "/data/example.h5cd"
    assert summaries[0]["data_name"] == "example.h5cd"
    assert summaries[0]["message_count"] == 2
    assert summaries[0]["last_message"] == "我来加载。"


def test_conversation_store_reopens_existing_database(tmp_path: Path):
    from webapp.backend.conversation_store import ConversationStore

    db_path = tmp_path / "history.sqlite3"
    first = ConversationStore(db_path)
    conversation_id = first.create_conversation(title="Persist me")
    first.append_message(conversation_id, "user", "hello")

    second = ConversationStore(db_path)
    snapshot = second.get_snapshot(conversation_id)

    assert snapshot["conversation"]["title"] == "Persist me"
    assert snapshot["messages"][0]["content"] == "hello"


def test_conversation_store_round_trips_model_history(tmp_path: Path):
    from webapp.backend.conversation_store import ConversationStore

    store = ConversationStore(tmp_path / "history.sqlite3")
    conversation_id = store.create_conversation(title="Model context")
    history = [
        {"role": "user", "content": "plot chr1"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "tool-1",
                    "name": "render_gosling",
                    "input": {"title": "chr1"},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tool-1",
                    "content": '{"success": true}',
                }
            ],
        },
    ]

    store.save_model_history(conversation_id, history)

    assert store.load_model_history(conversation_id) == history


def test_conversation_store_avoids_duplicate_message_ids(tmp_path: Path):
    from webapp.backend.conversation_store import ConversationStore

    store = ConversationStore(tmp_path / "history.sqlite3")
    conversation_id = store.create_conversation(title="Duplicate ids")

    first = store.append_message(conversation_id, "assistant", "one", message_id="same")
    second = store.append_message(conversation_id, "assistant", "two", message_id="same")

    assert first["id"] == "same"
    assert second["id"].startswith("same-")
    snapshot = store.get_snapshot(conversation_id)
    assert [m["content"] for m in snapshot["messages"]] == ["one", "two"]


def test_conversation_store_list_hides_empty_conversations(tmp_path: Path):
    from webapp.backend.conversation_store import ConversationStore

    store = ConversationStore(tmp_path / "history.sqlite3")
    empty_id = store.create_conversation(title="New conversation")
    active_id = store.create_conversation(title="Has messages")
    data_id = store.create_conversation(title="Has data", data_path="/data/file.h5cd")
    store.append_message(active_id, "user", "hello")

    listed_ids = [item["id"] for item in store.list_conversations()]

    assert empty_id not in listed_ids
    assert active_id in listed_ids
    assert data_id in listed_ids


def test_conversation_store_returns_empty_snapshot_for_missing_conversation(tmp_path: Path):
    from webapp.backend.conversation_store import ConversationStore

    store = ConversationStore(tmp_path / "history.sqlite3")

    assert store.get_snapshot("missing") is None
