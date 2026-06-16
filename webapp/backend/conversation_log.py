"""Lightweight JSONL conversation tracing for backend debugging.

The logger is intentionally best-effort: failures must never break websocket
handling or the Claude tool loop.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
from typing import Any

logger = logging.getLogger(__name__)

_DISABLED_VALUES = {"0", "false", "off", "no"}
_SENSITIVE_KEY_PARTS = ("api_key", "auth", "token", "secret", "password", "credential")
_DATA_URL_RE = re.compile(r"^data:([^;,]+)(?:;base64)?,", re.IGNORECASE)


def conversation_log_enabled() -> bool:
    value = os.getenv("UCHROM_CONVERSATION_LOG", "1").strip().lower()
    return value not in _DISABLED_VALUES


def conversation_log_dir() -> Path:
    configured = os.getenv("UCHROM_CONVERSATION_LOG_DIR")
    if configured:
        return Path(configured)
    return Path.cwd() / "logs" / "conversations"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_session_id(session: Any) -> str:
    raw = getattr(session, "session_id", None) or "unknown"
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(raw)).strip("._")
    return safe or "unknown"


def _is_path_key(key: str | None) -> bool:
    if not key:
        return False
    lowered = key.lower()
    return lowered == "path" or lowered.endswith("_path") or lowered in {"file", "filename"}


def _summarize_string(value: str, key: str | None, max_string: int) -> Any:
    match = _DATA_URL_RE.match(value)
    if match:
        return {
            "kind": "data_url",
            "media_type": match.group(1),
            "length": len(value),
        }

    if _is_path_key(key) and os.getenv("UCHROM_CONVERSATION_LOG_FULL_PATHS", "0") not in {"1", "true", "yes"}:
        return {
            "kind": "path",
            "basename": os.path.basename(value),
            "length": len(value),
        }

    if len(value) <= max_string:
        return value

    half = max(1, max_string // 2)
    return {
        "value": value[:half] + "..." + value[-half:],
        "truncated": True,
        "original_length": len(value),
    }


def sanitize_for_log(
    value: Any,
    *,
    max_string: int = 2000,
    max_items: int = 20,
    max_depth: int = 8,
    _key: str | None = None,
    _depth: int = 0,
) -> Any:
    """Return a JSON-safe, redacted, bounded representation of ``value``."""
    if _key and any(part in _key.lower() for part in _SENSITIVE_KEY_PARTS):
        return "[redacted]"

    if _depth >= max_depth:
        return {
            "truncated": True,
            "reason": "max_depth",
            "type": type(value).__name__,
        }

    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        return _summarize_string(value, _key, max_string)

    if isinstance(value, dict):
        items = list(value.items())
        sanitized = {}
        for key, child in items[:max_items]:
            text_key = str(key)
            sanitized[text_key] = sanitize_for_log(
                child,
                max_string=max_string,
                max_items=max_items,
                max_depth=max_depth,
                _key=text_key,
                _depth=_depth + 1,
            )
        if len(items) > max_items:
            sanitized["__truncated__"] = {
                "omitted_items": len(items) - max_items,
                "original_items": len(items),
            }
        return sanitized

    if isinstance(value, (list, tuple, set)):
        items = list(value)
        sanitized = [
            sanitize_for_log(
                child,
                max_string=max_string,
                max_items=max_items,
                max_depth=max_depth,
                _depth=_depth + 1,
            )
            for child in items[:max_items]
        ]
        if len(items) > max_items:
            sanitized.append({
                "truncated": True,
                "omitted_items": len(items) - max_items,
                "original_items": len(items),
            })
        return sanitized

    if hasattr(value, "__dict__"):
        public_attrs = {
            key: child
            for key, child in vars(value).items()
            if not key.startswith("_")
        }
        if public_attrs:
            return sanitize_for_log(
                public_attrs,
                max_string=max_string,
                max_items=max_items,
                max_depth=max_depth,
                _depth=_depth + 1,
            )

    return _summarize_string(repr(value), _key, max_string)


def append_conversation_event(session: Any, event: str, payload: Any) -> Path | None:
    """Append one JSONL event for ``session`` and return the path written."""
    if not conversation_log_enabled():
        return None

    try:
        session_id = _safe_session_id(session)
        record = {
            "timestamp": _timestamp(),
            "session_id": session_id,
            "event": event,
            "payload": sanitize_for_log(payload),
        }

        log_dir = conversation_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"{session_id}.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            fh.write("\n")
        return path
    except Exception:
        logger.exception("failed to append conversation log event %s", event)
        return None
