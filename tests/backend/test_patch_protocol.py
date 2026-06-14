"""Tests for the standardized patch protocol (RFC 6902 JSON-Patch) + the
view-state reconciliation and render-diagnostics feedback loop.

Covers the third-wave changes:
  - patch_gosling emits a standard JSON-Patch `ops` array and applies it to the
    backend-authoritative spec via the jsonpatch library.
  - view revisions increment on render/patch; patch artifacts carry
    base_revision / new_revision so the client can detect a gap.
  - a `view.diagnostic` message lands on the view's capped diagnostics list and
    is surfaced by get_view_state so the agent can SEE a broken render.
"""
import json
import pytest
from unittest.mock import AsyncMock

from webapp.backend.tool_executors import (
    TOOL_EXECUTORS,
    apply_json_patch,
    _normalize_ops,
)
from webapp.backend.session import Session, MAX_VIEW_DIAGNOSTICS


# ---------------------------------------------------------------------------
# apply_json_patch / _normalize_ops — RFC 6902 primitives
# ---------------------------------------------------------------------------

def test_normalize_ops_accepts_single_and_array():
    single = {"op": "replace", "path": "/a", "value": 1}
    assert _normalize_ops(single) == [single]
    arr = [single, {"op": "add", "path": "/b", "value": 2}]
    assert _normalize_ops(arr) == arr
    assert _normalize_ops("nonsense") == []


def test_apply_json_patch_replace_add_remove():
    doc = {"tracks": [{"mark": "bar"}], "title": "t"}
    new_doc, err = apply_json_patch(doc, [
        {"op": "replace", "path": "/tracks/0/mark", "value": "line"},
        {"op": "add", "path": "/tracks/0/color", "value": "red"},
        {"op": "remove", "path": "/title"},
    ])
    assert err is None
    assert new_doc["tracks"][0]["mark"] == "line"
    assert new_doc["tracks"][0]["color"] == "red"
    assert "title" not in new_doc
    # Original document is not mutated (apply returns a patched copy).
    assert doc["tracks"][0]["mark"] == "bar"
    assert "title" in doc


def test_apply_json_patch_bad_path_returns_error():
    doc = {"tracks": []}
    new_doc, err = apply_json_patch(doc, [
        {"op": "replace", "path": "/tracks/5/mark", "value": "x"},
    ])
    assert err is not None
    assert new_doc == doc  # unchanged on failure


# ---------------------------------------------------------------------------
# patch_gosling — standard ops array + revision accounting
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_gosling_emits_ops_array_and_updates_spec():
    ws = AsyncMock()
    session = Session(session_id="s1")
    await TOOL_EXECUTORS["render_gosling"](
        ws, {"spec": {"tracks": [{"mark": "bar"}]}, "_tool_use_id": "v1", "_session": session}
    )
    base_rev = session.views["v1"].revision  # == 1 after replace()
    await TOOL_EXECUTORS["patch_gosling"](
        ws, {
            "target_id": "v1",
            "patch": {"op": "replace", "path": "/tracks/0/mark", "value": "line"},
            "_session": session,
        },
    )
    # Backend spec mutated via JSON-Patch.
    assert session.views["v1"].state["spec"]["tracks"][0]["mark"] == "line"
    # Revision bumped.
    assert session.views["v1"].revision == base_rev + 1
    # Emitted artifact is a standard ops array with base/new revision.
    art = ws.send_json.call_args[0][0]
    assert art["artifact_type"] == "gosling_patch"
    assert art["ops"][0] == {"op": "replace", "path": "/tracks/0/mark", "value": "line"}
    assert art["base_revision"] == base_rev
    assert art["new_revision"] == base_rev + 1


@pytest.mark.asyncio
async def test_patch_gosling_accepts_op_array():
    ws = AsyncMock()
    session = Session(session_id="s1")
    await TOOL_EXECUTORS["render_gosling"](
        ws, {"spec": {"tracks": [{"mark": "bar"}]}, "_tool_use_id": "v1", "_session": session}
    )
    await TOOL_EXECUTORS["patch_gosling"](
        ws, {
            "target_id": "v1",
            "patch": [
                {"op": "replace", "path": "/tracks/0/mark", "value": "point"},
                {"op": "add", "path": "/tracks/0/color", "value": "blue"},
            ],
            "_session": session,
        },
    )
    spec = session.views["v1"].state["spec"]
    assert spec["tracks"][0]["mark"] == "point"
    assert spec["tracks"][0]["color"] == "blue"


@pytest.mark.asyncio
async def test_patch_gosling_bad_path_does_not_emit_or_mutate():
    ws = AsyncMock()
    session = Session(session_id="s1")
    await TOOL_EXECUTORS["render_gosling"](
        ws, {"spec": {"tracks": []}, "_tool_use_id": "v1", "_session": session}
    )
    ws.reset_mock()
    content = await TOOL_EXECUTORS["patch_gosling"](
        ws, {
            "target_id": "v1",
            "patch": {"op": "replace", "path": "/tracks/9/mark", "value": "x"},
            "_session": session,
        },
    )
    payload = json.loads(content)
    assert payload["success"] is False
    # No artifact emitted on an unresolvable patch.
    ws.send_json.assert_not_called()
    # Spec untouched.
    assert session.views["v1"].state["spec"] == {"tracks": []}


@pytest.mark.asyncio
async def test_patch_gosling_rejects_unsafe_url_in_op():
    ws = AsyncMock()
    session = Session(session_id="s1")
    await TOOL_EXECUTORS["render_gosling"](
        ws, {"spec": {"tracks": [{}]}, "_tool_use_id": "v1", "_session": session}
    )
    ws.reset_mock()
    content = await TOOL_EXECUTORS["patch_gosling"](
        ws, {
            "target_id": "v1",
            "patch": {"op": "replace", "path": "/tracks/0/url", "value": "javascript:alert(1)"},
            "_session": session,
        },
    )
    payload = json.loads(content)
    assert payload["success"] is False
    assert "URL" in payload["error"]
    ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_render_gosling_emits_revision():
    ws = AsyncMock()
    session = Session(session_id="s1")
    await TOOL_EXECUTORS["render_gosling"](
        ws, {"spec": {"tracks": []}, "_tool_use_id": "v1", "_session": session}
    )
    art = ws.send_json.call_args[0][0]
    assert art["revision"] == session.views["v1"].revision == 1


# ---------------------------------------------------------------------------
# Reconciliation: base_revision drives the client snapshot re-pull. The backend
# carries the authoritative revision; we assert the artifact tells the client
# what to base its local check on.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_base_revision_tracks_successive_patches():
    ws = AsyncMock()
    session = Session(session_id="s1")
    await TOOL_EXECUTORS["render_gosling"](
        ws, {"spec": {"tracks": [{"mark": "bar"}]}, "_tool_use_id": "v1", "_session": session}
    )
    revs = []
    for value in ("line", "point", "area"):
        ws.reset_mock()
        await TOOL_EXECUTORS["patch_gosling"](
            ws, {
                "target_id": "v1",
                "patch": {"op": "replace", "path": "/tracks/0/mark", "value": value},
                "_session": session,
            },
        )
        art = ws.send_json.call_args[0][0]
        revs.append((art["base_revision"], art["new_revision"]))
    # Each patch's base is the previous new; new increments by 1.
    assert revs == [(1, 2), (2, 3), (3, 4)]


# ---------------------------------------------------------------------------
# Diagnostics feedback: view.diagnostic → session view → get_view_state
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_view_diagnostic_lands_and_is_visible_to_agent():
    from webapp.backend.ws_handler import handle_message
    ws = AsyncMock()
    session = Session(session_id="s1")
    await TOOL_EXECUTORS["render_gosling"](
        ws, {"spec": {"tracks": []}, "_tool_use_id": "v1", "_session": session}
    )
    # Frontend reports a render failure.
    await handle_message(ws, session, {
        "type": "view.diagnostic",
        "payload": {
            "view_id": "v1",
            "level": "error",
            "source": "gosling-spec",
            "message": "track 0 has no mark",
            "revision": 1,
        },
    }, executor=None)
    diags = session.views["v1"].diagnostics
    assert len(diags) == 1
    assert diags[0]["message"] == "track 0 has no mark"
    assert diags[0]["source"] == "gosling-spec"
    # get_view_state surfaces it so the agent can SEE the broken render.
    content = await TOOL_EXECUTORS["get_view_state"](
        ws, {"view_id": "v1", "_session": session}
    )
    payload = json.loads(content)
    assert payload["success"] is True
    assert payload["view"]["diagnostics"][0]["message"] == "track 0 has no mark"


@pytest.mark.asyncio
async def test_view_diagnostic_creates_stub_for_unknown_view():
    from webapp.backend.ws_handler import handle_message
    ws = AsyncMock()
    session = Session(session_id="s1")
    await handle_message(ws, session, {
        "type": "view.diagnostic",
        "payload": {"view_id": "ghost", "message": "boom"},
    }, executor=None)
    assert "ghost" in session.views
    assert session.views["ghost"].diagnostics[0]["message"] == "boom"


@pytest.mark.asyncio
async def test_diagnostics_are_capped():
    from webapp.backend.ws_handler import handle_message
    ws = AsyncMock()
    session = Session(session_id="s1")
    session.get_or_create_view("v1", "gosling")
    for i in range(MAX_VIEW_DIAGNOSTICS + 5):
        await handle_message(ws, session, {
            "type": "view.diagnostic",
            "payload": {"view_id": "v1", "message": f"err {i}"},
        }, executor=None)
    diags = session.views["v1"].diagnostics
    assert len(diags) == MAX_VIEW_DIAGNOSTICS
    # FIFO: oldest dropped, newest kept.
    assert diags[-1]["message"] == f"err {MAX_VIEW_DIAGNOSTICS + 4}"
    assert diags[0]["message"] == "err 5"


@pytest.mark.asyncio
async def test_get_view_state_list_includes_diagnostic_count():
    ws = AsyncMock()
    session = Session(session_id="s1")
    v = session.get_or_create_view("v1", "gosling")
    v.add_diagnostic({"message": "x"})
    content = await TOOL_EXECUTORS["get_view_state"](ws, {"_session": session})
    payload = json.loads(content)
    entry = next(e for e in payload["views"] if e["view_id"] == "v1")
    assert entry["n_diagnostics"] == 1
