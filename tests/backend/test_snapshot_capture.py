"""Tests for the view-snapshot Future mechanism (capture_view_snapshot).

Mirrors test_interaction_future.py. The capture_view_snapshot tool aligns with
the pantheon live-view-screenshot pattern:

  - wait_for_snapshot registers a Future under a unique ``request_id``, awaits
    it with a timeout, and always pops it (resolve / timeout / cancel).
  - a ``snapshot_result`` ws message carrying that request_id resolves EXACTLY
    that Future with {data_url, error}.
  - the executor turns a resolved data URL into an Anthropic tool_result content
    block list (text + image), returned under ``_content_blocks`` so
    run_agent_loop can pass the image through to the vision model.
  - timeout / capture error / bad data URL fall back to a plain-text JSON error
    so the agent loop keeps going.
"""
import asyncio
import base64
import json

import pytest
from unittest.mock import AsyncMock

from webapp.backend import ws_handler
from webapp.backend.ws_handler import handle_message, wait_for_snapshot
from webapp.backend.session import Session
from webapp.backend.tool_executors import (
    TOOL_EXECUTORS,
    build_snapshot_content_blocks,
)

# A 1x1 transparent PNG as a base64 data URL — the smallest valid image.
_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
_DATA_URL = f"data:image/png;base64,{_PNG_B64}"


def _snapshot_result(request_id, data_url=None, error=None):
    return {
        "type": "snapshot_result",
        "payload": {"request_id": request_id, "data_url": data_url, "error": error},
    }


@pytest.fixture(autouse=True)
def _clean_registry():
    ws_handler._pending_snapshots.clear()
    yield
    ws_handler._pending_snapshots.clear()


@pytest.mark.asyncio
async def test_wait_resolves_on_matching_request_id():
    """A snapshot_result echoing the request_id resolves the Future."""
    ws = AsyncMock()
    session = Session()
    rid = "rid-1"

    async def _waiter():
        return await wait_for_snapshot(rid, timeout=5)

    task = asyncio.create_task(_waiter())
    await asyncio.sleep(0)

    await handle_message(ws, session, _snapshot_result(rid, data_url=_DATA_URL),
                         AsyncMock())

    result = await asyncio.wait_for(task, timeout=1)
    assert result is not None
    assert result["data_url"] == _DATA_URL
    assert result["error"] is None
    assert ws_handler._pending_snapshots == {}


@pytest.mark.asyncio
async def test_wait_times_out_returns_none_and_pops():
    """No snapshot within the timeout → None, and the waiter is popped."""
    result = await wait_for_snapshot("rid-timeout", timeout=0.05)
    assert result is None
    assert ws_handler._pending_snapshots == {}


@pytest.mark.asyncio
async def test_wrong_request_id_does_not_resolve():
    """A snapshot_result with a different request_id must not resolve the waiter."""
    ws = AsyncMock()
    session = Session()

    async def _waiter():
        return await wait_for_snapshot("correct", timeout=0.2)

    task = asyncio.create_task(_waiter())
    await asyncio.sleep(0)

    await handle_message(ws, session, _snapshot_result("WRONG", data_url=_DATA_URL),
                         AsyncMock())

    result = await asyncio.wait_for(task, timeout=1)
    assert result is None
    assert ws_handler._pending_snapshots == {}


def test_build_snapshot_content_blocks_shape():
    """The content-block list has a text block + a valid Anthropic image block."""
    blocks = build_snapshot_content_blocks("structure3d", _DATA_URL)
    assert isinstance(blocks, list) and len(blocks) == 2
    text, image = blocks
    assert text["type"] == "text" and "structure3d" in text["text"]
    assert image["type"] == "image"
    src = image["source"]
    assert src["type"] == "base64"
    assert src["media_type"] == "image/png"
    assert src["data"] == _PNG_B64
    # The data must be valid base64 that decodes to a PNG signature.
    raw = base64.b64decode(src["data"])
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"


def test_build_snapshot_content_blocks_rejects_non_image():
    """A non-image / non-base64 data URL is rejected."""
    with pytest.raises(ValueError):
        build_snapshot_content_blocks("genomic", "not-a-data-url")
    with pytest.raises(ValueError):
        build_snapshot_content_blocks("genomic", "data:text/plain;base64,aGVsbG8=")


@pytest.mark.asyncio
async def test_executor_blocks_then_returns_image_block():
    """capture_view_snapshot announces request_snapshot, blocks, and returns an
    image content-block list once a matching snapshot_result arrives."""
    ws = AsyncMock()
    sent = []

    async def _capture(obj):
        sent.append(obj)
    ws.send_json = _capture

    session = Session()

    async def _call_tool():
        ti = {"view_id": "structure3d", "timeout_seconds": 5, "_session": session}
        return await TOOL_EXECUTORS["capture_view_snapshot"](ws, ti)

    task = asyncio.create_task(_call_tool())
    for _ in range(100):
        await asyncio.sleep(0.01)
        req = [m for m in sent if m.get("type") == "request_snapshot"]
        if req:
            break
    assert req, "executor never sent request_snapshot"
    rid = req[0]["request_id"]
    assert rid and req[0]["view_id"] == "structure3d"

    await handle_message(ws, session, _snapshot_result(rid, data_url=_DATA_URL),
                         AsyncMock())

    result = await asyncio.wait_for(task, timeout=2)
    # Structured return: a dict carrying _content_blocks with an image block.
    assert isinstance(result, dict) and "_content_blocks" in result
    blocks = result["_content_blocks"]
    assert any(b["type"] == "image" for b in blocks)
    img = next(b for b in blocks if b["type"] == "image")
    assert img["source"]["data"] == _PNG_B64


@pytest.mark.asyncio
async def test_executor_timeout_returns_text_error():
    """On capture timeout the executor returns a plain JSON text error (str),
    not an image — so run_agent_loop keeps the loop alive."""
    ws = AsyncMock()
    sent = []

    async def _capture(obj):
        sent.append(obj)
    ws.send_json = _capture

    session = Session()
    ti = {"view_id": "genomic", "timeout_seconds": 0.05, "_session": session}
    result = await TOOL_EXECUTORS["capture_view_snapshot"](ws, ti)
    assert isinstance(result, str)
    parsed = json.loads(result)
    assert parsed["success"] is False
    assert "no snapshot" in parsed["error"].lower()


@pytest.mark.asyncio
async def test_executor_rejects_unknown_view_id():
    """An unknown view_id is rejected up front with a text error."""
    ws = AsyncMock()
    session = Session()
    ti = {"view_id": "bogus", "_session": session}
    result = await TOOL_EXECUTORS["capture_view_snapshot"](ws, ti)
    parsed = json.loads(result)
    assert parsed["success"] is False
    assert "unknown view_id" in parsed["error"].lower()


@pytest.mark.asyncio
async def test_executor_surfaces_frontend_capture_error():
    """A snapshot_result carrying an error resolves to a text error result."""
    ws = AsyncMock()
    sent = []

    async def _capture(obj):
        sent.append(obj)
    ws.send_json = _capture

    session = Session()

    async def _call_tool():
        ti = {"view_id": "embedding", "timeout_seconds": 5, "_session": session}
        return await TOOL_EXECUTORS["capture_view_snapshot"](ws, ti)

    task = asyncio.create_task(_call_tool())
    for _ in range(100):
        await asyncio.sleep(0.01)
        req = [m for m in sent if m.get("type") == "request_snapshot"]
        if req:
            break
    assert req
    rid = req[0]["request_id"]

    await handle_message(ws, session,
                         _snapshot_result(rid, error="canvas not ready"),
                         AsyncMock())

    result = await asyncio.wait_for(task, timeout=2)
    assert isinstance(result, str)
    parsed = json.loads(result)
    assert parsed["success"] is False
    assert "canvas not ready" in parsed["error"]
