"""Persistent user-facing conversation history for U-Chrom.

This store is deliberately separate from ``conversation_log.py``. JSONL traces
remain a bounded debug/audit stream; this module owns the canonical transcript
that the UI can list, load, and continue across backend restarts.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import uuid
from typing import Any


SCHEMA_VERSION = 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _default_db_path() -> Path:
    configured = os.getenv("UCHROM_CONVERSATION_DB")
    if configured:
        return Path(configured)
    return Path.cwd() / "logs" / "conversations" / "conversations.sqlite3"


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_loads(value: str | None, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


class ConversationStore:
    """Small SQLite-backed store for chat transcripts, tool events, and views."""

    def __init__(self, path: str | os.PathLike[str] | None = None):
        self.path = Path(path) if path is not None else _default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    data_path TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
                    content TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    seq INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_conversation_seq
                ON messages(conversation_id, seq);

                CREATE TABLE IF NOT EXISTS message_events (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
                    type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    seq INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_events_message_seq
                ON message_events(message_id, seq);

                CREATE TABLE IF NOT EXISTS view_snapshots (
                    conversation_id TEXT PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
                    views_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS model_history (
                    conversation_id TEXT PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
                    history_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def create_conversation(
        self,
        *,
        conversation_id: str | None = None,
        title: str | None = None,
        data_path: str | None = None,
    ) -> str:
        cid = conversation_id or str(uuid.uuid4())
        now = _utc_now()
        clean_title = (title or "New conversation").strip() or "New conversation"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO conversations(id, title, data_path, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    data_path = COALESCE(excluded.data_path, conversations.data_path),
                    updated_at = excluded.updated_at
                """,
                (cid, clean_title, data_path, now, now),
            )
        return cid

    def ensure_conversation(
        self,
        conversation_id: str,
        *,
        title: str | None = None,
        data_path: str | None = None,
    ) -> str:
        row = self._get_conversation_row(conversation_id)
        if row is None:
            return self.create_conversation(
                conversation_id=conversation_id,
                title=title,
                data_path=data_path,
            )
        if title is not None or data_path is not None:
            self.update_conversation(conversation_id, title=title, data_path=data_path)
        return conversation_id

    def update_conversation(
        self,
        conversation_id: str,
        *,
        title: str | None = None,
        data_path: str | None = None,
    ) -> None:
        row = self._get_conversation_row(conversation_id)
        if row is None:
            self.create_conversation(
                conversation_id=conversation_id,
                title=title,
                data_path=data_path,
            )
            return

        next_title = row["title"] if title is None else ((title.strip() or row["title"]))
        next_data_path = row["data_path"] if data_path is None else data_path
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE conversations
                SET title = ?, data_path = ?, updated_at = ?
                WHERE id = ?
                """,
                (next_title, next_data_path, _utc_now(), conversation_id),
            )

    def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        *,
        message_id: str | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        self.ensure_conversation(conversation_id)
        mid = message_id or str(uuid.uuid4())
        now = created_at or _utc_now()
        with self._connect() as conn:
            seq = self._next_seq(conn, "messages", conversation_id)
            while conn.execute("SELECT 1 FROM messages WHERE id = ?", (mid,)).fetchone():
                mid = f"{message_id or 'message'}-{uuid.uuid4().hex[:8]}"
            conn.execute(
                """
                INSERT INTO messages(id, conversation_id, role, content, created_at, seq)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (mid, conversation_id, role, content or "", now, seq),
            )
            self._touch(conn, conversation_id, now)
        return {
            "id": mid,
            "conversation_id": conversation_id,
            "role": role,
            "content": content or "",
            "created_at": now,
            "seq": seq,
            "events": [],
        }

    def append_event(
        self,
        conversation_id: str,
        message_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        event_id: str | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        eid = event_id or str(uuid.uuid4())
        now = created_at or _utc_now()
        with self._connect() as conn:
            seq = self._next_seq(conn, "message_events", conversation_id)
            conn.execute(
                """
                INSERT INTO message_events(
                    id, conversation_id, message_id, type, payload_json, created_at, seq
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (eid, conversation_id, message_id, event_type, _json_dumps(payload), now, seq),
            )
            self._touch(conn, conversation_id, now)
        return {
            "id": eid,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "type": event_type,
            "payload": payload,
            "created_at": now,
            "seq": seq,
        }

    def save_view_snapshot(self, conversation_id: str, views: list[dict[str, Any]]) -> None:
        self.ensure_conversation(conversation_id)
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO view_snapshots(conversation_id, views_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    views_json = excluded.views_json,
                    updated_at = excluded.updated_at
                """,
                (conversation_id, _json_dumps(views), now),
            )
            self._touch(conn, conversation_id, now)

    def save_model_history(self, conversation_id: str, history: list[dict[str, Any]]) -> None:
        self.ensure_conversation(conversation_id)
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO model_history(conversation_id, history_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    history_json = excluded.history_json,
                    updated_at = excluded.updated_at
                """,
                (conversation_id, _json_dumps(history), now),
            )
            self._touch(conn, conversation_id, now)

    def load_model_history(self, conversation_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT history_json FROM model_history WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        if row is None:
            snapshot = self.get_snapshot(conversation_id)
            if snapshot is None:
                return []
            return [
                {"role": msg["role"], "content": msg["content"]}
                for msg in snapshot["messages"]
                if msg["role"] in {"user", "assistant"}
            ]
        history = _json_loads(row["history_json"], [])
        return history if isinstance(history, list) else []

    def get_snapshot(self, conversation_id: str) -> dict[str, Any] | None:
        conversation = self._get_conversation_row(conversation_id)
        if conversation is None:
            return None

        with self._connect() as conn:
            message_rows = conn.execute(
                """
                SELECT id, conversation_id, role, content, created_at, seq
                FROM messages
                WHERE conversation_id = ?
                ORDER BY seq ASC
                """,
                (conversation_id,),
            ).fetchall()
            event_rows = conn.execute(
                """
                SELECT id, conversation_id, message_id, type, payload_json, created_at, seq
                FROM message_events
                WHERE conversation_id = ?
                ORDER BY seq ASC
                """,
                (conversation_id,),
            ).fetchall()
            view_row = conn.execute(
                "SELECT views_json FROM view_snapshots WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()

        events_by_message: dict[str, list[dict[str, Any]]] = {}
        for row in event_rows:
            events_by_message.setdefault(row["message_id"], []).append({
                "id": row["id"],
                "conversation_id": row["conversation_id"],
                "message_id": row["message_id"],
                "type": row["type"],
                "payload": _json_loads(row["payload_json"], {}),
                "created_at": row["created_at"],
                "seq": row["seq"],
            })

        messages = []
        for row in message_rows:
            messages.append({
                "id": row["id"],
                "conversation_id": row["conversation_id"],
                "role": row["role"],
                "content": row["content"],
                "created_at": row["created_at"],
                "seq": row["seq"],
                "events": events_by_message.get(row["id"], []),
            })

        views = _json_loads(view_row["views_json"], []) if view_row else []
        return {
            "conversation": self._conversation_dict(conversation),
            "messages": messages,
            "views": views,
        }

    def list_conversations(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    c.id,
                    c.title,
                    c.data_path,
                    c.created_at,
                    c.updated_at,
                    COUNT(m.id) AS message_count,
                    (
                        SELECT lm.content
                        FROM messages AS lm
                        WHERE lm.conversation_id = c.id
                        ORDER BY lm.seq DESC
                        LIMIT 1
                    ) AS last_message
                FROM conversations AS c
                LEFT JOIN messages AS m ON m.conversation_id = c.id
                WHERE c.archived = 0
                GROUP BY c.id
                HAVING COUNT(m.id) > 0 OR c.data_path IS NOT NULL
                ORDER BY c.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [self._summary_dict(row) for row in rows]

    def _get_conversation_row(self, conversation_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT id, title, data_path, created_at, updated_at
                FROM conversations
                WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()

    @staticmethod
    def _next_seq(conn: sqlite3.Connection, table: str, conversation_id: str) -> int:
        row = conn.execute(
            f"SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM {table} WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        return int(row["next_seq"])

    @staticmethod
    def _touch(conn: sqlite3.Connection, conversation_id: str, timestamp: str) -> None:
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (timestamp, conversation_id),
        )

    @staticmethod
    def _conversation_dict(row: sqlite3.Row) -> dict[str, Any]:
        data_path = row["data_path"]
        return {
            "id": row["id"],
            "title": row["title"],
            "data_path": data_path,
            "data_name": os.path.basename(data_path) if data_path else None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _summary_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        data_path = row["data_path"]
        return {
            "id": row["id"],
            "title": row["title"],
            "data_path": data_path,
            "data_name": os.path.basename(data_path) if data_path else None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "message_count": int(row["message_count"]),
            "last_message": row["last_message"] or "",
        }
