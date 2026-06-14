"""Tests for the user-interaction Future mechanism in ws_handler.

The third-wave interaction upgrade aligns query_user_interaction with the
AG-UI interrupt/resume + pantheon pending-Future pattern:

  - wait_for_interaction registers a waiter under a unique ``interaction_id``,
    awaits it with a timeout, and always pops it (resolve / timeout / cancel).
  - a ``ui_event`` that echoes the SAME interaction_id resolves EXACTLY that
    waiter (precise match); an event with no id resolves by view_id (or any
    view) as a forgiving fallback for organic brush/click/pick events.
  - a wrong / stale interaction_id resolves nothing.

These tests drive ``wait_for_interaction`` concurrently with a
``handle_message`` ui_event and assert on the resolved payload, the timeout
path, and the precise-id matching.
"""
import asyncio

import pytest
from unittest.mock import AsyncMock

from webapp.backend import ws_handler
from webapp.backend.ws_handler import handle_message, wait_for_interaction
from webapp.backend.session import Session


def _ui_event(view_id=None, event_name="pick_spot", payload=None, interaction_id=None):
    p = {"event_name": event_name, "payload": payload or {}}
    if view_id is not None:
        p["source_view_id"] = view_id
    if interaction_id is not None:
        p["interaction_id"] = interaction_id
    return {"type": "ui_event", "payload": p}


@pytest.fixture(autouse=True)
def _clean_registry():
    """Each test starts/ends with an empty waiter registry (no cross-leak)."""
    ws_handler._pending_interactions.clear()
    yield
    ws_handler._pending_interactions.clear()


@pytest.mark.asyncio
async def test_wait_resolves_on_matching_interaction_id():
    """A ui_event echoing the waiter's interaction_id resolves it with the payload."""
    ws = AsyncMock()
    session = Session()
    iid = "iid-precise-1"

    async def _waiter():
        return await wait_for_interaction(session, view_id=None, timeout=5,
                                          interaction_id=iid)

    task = asyncio.create_task(_waiter())
    await asyncio.sleep(0)  # let the waiter register before we fire the event

    payload = {"cell_id": "c0", "chrom": "chr1", "start": 1000, "end": 2000,
               "spot_index": 3}
    await handle_message(ws, session, _ui_event(
        view_id="structure3d", payload=payload, interaction_id=iid), AsyncMock())

    event = await asyncio.wait_for(task, timeout=1)
    assert event is not None
    assert event["event_name"] == "pick_spot"
    assert event["payload"] == payload
    assert event["interaction_id"] == iid
    # Registry is drained after resolution.
    assert ws_handler._pending_interactions == {}


@pytest.mark.asyncio
async def test_wait_times_out_returns_none_and_pops():
    """No interaction within the timeout → None, and the waiter is popped."""
    session = Session()
    event = await wait_for_interaction(session, view_id="v1", timeout=0.05,
                                       interaction_id="iid-timeout")
    assert event is None
    assert ws_handler._pending_interactions == {}


@pytest.mark.asyncio
async def test_wrong_interaction_id_does_not_resolve():
    """A ui_event with a DIFFERENT interaction_id must not resolve the waiter.

    The named-target path is strict: a foreign/stale id resolves nothing and
    does NOT fall back to view matching, so the waiter still times out.
    """
    ws = AsyncMock()
    session = Session()

    async def _waiter():
        return await wait_for_interaction(session, view_id="structure3d",
                                          timeout=0.2, interaction_id="correct-id")

    task = asyncio.create_task(_waiter())
    await asyncio.sleep(0)

    # Event echoes a DIFFERENT id → should not wake our waiter.
    await handle_message(ws, session, _ui_event(
        view_id="structure3d", payload={"x": 1}, interaction_id="WRONG-id"),
        AsyncMock())

    event = await asyncio.wait_for(task, timeout=1)
    assert event is None  # timed out, never resolved by the wrong id
    assert ws_handler._pending_interactions == {}


@pytest.mark.asyncio
async def test_organic_event_resolves_by_view_id_without_id():
    """An interaction with NO id resolves the waiter watching that view_id.

    This is the fallback for organic brush/click/pick events the user makes
    without the agent having announced an id for that exact view.
    """
    ws = AsyncMock()
    session = Session()

    async def _waiter():
        return await wait_for_interaction(session, view_id="gos-1", timeout=5,
                                          interaction_id="iid-view")

    task = asyncio.create_task(_waiter())
    await asyncio.sleep(0)

    await handle_message(ws, session, _ui_event(
        view_id="gos-1", event_name="brush_selection",
        payload={"chrom": "chr2", "start": 5, "end": 9}), AsyncMock())

    event = await asyncio.wait_for(task, timeout=1)
    assert event is not None
    assert event["event_name"] == "brush_selection"
    assert event["payload"]["chrom"] == "chr2"


@pytest.mark.asyncio
async def test_any_view_waiter_resolves_on_any_interaction():
    """A waiter with view_id=None (any view) resolves on any organic event."""
    ws = AsyncMock()
    session = Session()

    async def _waiter():
        return await wait_for_interaction(session, view_id=None, timeout=5,
                                          interaction_id="iid-any")

    task = asyncio.create_task(_waiter())
    await asyncio.sleep(0)

    await handle_message(ws, session, _ui_event(
        view_id="structure3d", event_name="pick_spot",
        payload={"cell_id": "c9"}), AsyncMock())

    event = await asyncio.wait_for(task, timeout=1)
    assert event is not None
    assert event["payload"]["cell_id"] == "c9"


@pytest.mark.asyncio
async def test_query_user_interaction_executor_blocks_then_resolves():
    """The query_user_interaction executor (wait=true) announces an
    interaction_id, blocks, and returns the pick_spot payload once a matching
    ui_event arrives — the full agent-facing path.
    """
    import json
    from webapp.backend.tool_executors import TOOL_EXECUTORS

    ws = AsyncMock()
    sent = []

    async def _capture(obj):
        sent.append(obj)
    ws.send_json = _capture

    session = Session()

    async def _call_tool():
        ti = {"wait": True, "timeout_seconds": 5, "_session": session,
              "_tool_use_id": "tu1"}
        return await TOOL_EXECUTORS["query_user_interaction"](ws, ti)

    task = asyncio.create_task(_call_tool())
    # Wait until the executor has announced the interaction_id.
    for _ in range(100):
        await asyncio.sleep(0.01)
        announce = [m for m in sent if m.get("type") == "await_interaction"]
        if announce:
            break
    assert announce, "executor never announced await_interaction"
    iid = announce[0]["interaction_id"]
    assert iid

    payload = {"cell_id": "c3", "chrom": "chr5", "start": 100, "end": 200,
               "spot_index": 7}
    await handle_message(ws, session, _ui_event(
        view_id="structure3d", payload=payload, interaction_id=iid), AsyncMock())

    result = await asyncio.wait_for(task, timeout=2)
    parsed = json.loads(result)
    assert parsed["success"] is True
    assert parsed["interaction"]["payload"] == payload
    # The executor signals completion so the UI can clear its pending affordance.
    done = [m for m in sent if m.get("type") == "await_interaction_done"]
    assert done and done[0]["resolved"] is True
