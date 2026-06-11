"""Tests for the TOOL_EXECUTORS registry (ws_handler refactor).

Each executor is an async (websocket, tool_input) -> str. We assert it:
  - emits the right agent_artifact (where applicable), and
  - returns a tool_result content string the agent can consume.

This locks in the behaviour that used to live in ws_handler's if/elif ladder.
"""
import json
import pytest
from unittest.mock import AsyncMock

from webapp.backend.agent_tools import TOOLS
from webapp.backend.tool_executors import TOOL_EXECUTORS


def test_every_tool_has_an_executor():
    """Every schema in TOOLS must have a registered executor (and vice versa)."""
    tool_names = {t["name"] for t in TOOLS}
    assert tool_names == set(TOOL_EXECUTORS), (
        f"schema/executor mismatch: "
        f"schema-only={tool_names - set(TOOL_EXECUTORS)}, "
        f"executor-only={set(TOOL_EXECUTORS) - tool_names}"
    )


@pytest.mark.asyncio
async def test_render_gosling_emits_spec_artifact():
    ws = AsyncMock()
    content = await TOOL_EXECUTORS["render_gosling"](
        ws, {"spec": {"tracks": [1, 2]}, "title": "T", "_tool_use_id": "u1"}
    )
    art = ws.send_json.call_args[0][0]
    assert art["type"] == "agent_artifact"
    assert art["artifact_type"] == "gosling_spec"
    assert art["artifact_id"] == "u1"
    assert json.loads(content)["spec_tracks"] == 2


@pytest.mark.asyncio
async def test_patch_gosling_requires_path():
    ws = AsyncMock()
    content = await TOOL_EXECUTORS["patch_gosling"](
        ws, {"target_id": "", "patch": {}}
    )
    assert json.loads(content)["success"] is False


@pytest.mark.asyncio
async def test_export_view_normalizes_format():
    ws = AsyncMock()
    content = await TOOL_EXECUTORS["export_view"](ws, {"format": "svg"})
    art = ws.send_json.call_args[0][0]
    assert art["format"] == "png"  # unknown -> png
    assert "PNG" in content


@pytest.mark.asyncio
async def test_run_analysis_dispatches_and_emits(monkeypatch):
    ws = AsyncMock()
    fake_handle = {
        "type": "tad", "chrom": "chr1", "record_count": 3,
        "records": [{"chrom": "chr1", "start": 0, "end": 100}],
        "data_url": "/api/tads/chr1?format=gosling",
        "chromosome_field": "chrom", "genomic_fields": ["start", "end"],
        "suggested_mark": "rule",
    }
    import webapp.backend.strc_api as strc_api
    monkeypatch.setattr(strc_api, "run_registered_analysis", lambda t, c: fake_handle)

    content = await TOOL_EXECUTORS["run_analysis"](
        ws, {"type": "tad", "region": "chr1:1-1000"}
    )
    art = ws.send_json.call_args[0][0]
    assert art["artifact_type"] == "analysis_result"
    assert art["analysis_type"] == "tad"
    payload = json.loads(content)
    assert payload["success"] is True
    assert payload["data_url"] == "/api/tads/chr1?format=gosling"


@pytest.mark.asyncio
async def test_run_analysis_failure_returns_message(monkeypatch):
    ws = AsyncMock()
    import webapp.backend.strc_api as strc_api

    def _boom(t, c):
        raise RuntimeError("no data")
    monkeypatch.setattr(strc_api, "run_registered_analysis", _boom)

    content = await TOOL_EXECUTORS["run_analysis"](ws, {"type": "tad", "region": "chr1"})
    assert "Analysis failed" in content


@pytest.mark.asyncio
async def test_write_analysis_function_deploys_and_emits(monkeypatch):
    """Happy path: a valid analyze() compiles, deploys, emits custom_analysis_deployed."""
    ws = AsyncMock()
    import webapp.backend.dynamic_api as dynamic_api
    code = (
        "def analyze(cd, chrom, **p):\n"
        "    return pd.DataFrame({'chrom': [chrom], 'start': [0], 'end': [100]})\n"
    )
    try:
        content = await TOOL_EXECUTORS["write_analysis_function"](
            ws, {"name": "myfn", "code": code, "genomic_fields": ["start", "end"],
                 "suggested_mark": "bar"}
        )
        art = ws.send_json.call_args[0][0]
        assert art["artifact_type"] == "custom_analysis_deployed"
        assert art["analysis_id"] == "myfn"
        payload = json.loads(content)
        assert payload["success"] is True
        assert payload["data_url"].startswith("/api/custom/myfn/")
    finally:
        dynamic_api.clear_registry()


@pytest.mark.asyncio
async def test_write_analysis_function_rejects_malicious():
    """Sandbox rejection -> success:False, no artifact emitted."""
    ws = AsyncMock()
    bad = "import os\ndef analyze(cd, chrom, **p):\n    return pd.DataFrame()\n"
    content = await TOOL_EXECUTORS["write_analysis_function"](
        ws, {"name": "evil", "code": bad}
    )
    payload = json.loads(content)
    assert payload["success"] is False
    assert "sandbox" in payload["error"].lower()
    ws.send_json.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("name,inp,art_type", [
    ("select_cells", {"cell_ids": ["a", "b"]}, "select_cells"),
    ("color_embedding", {"color_by": "ATAC"}, "color_embedding"),
    ("show_structure", {"cell_id": "c1", "chrom": "chr1"}, "show_structure"),
    ("color_structure", {"color_by": "compartment"}, "color_structure"),
])
async def test_simple_forwarders(name, inp, art_type):
    ws = AsyncMock()
    content = await TOOL_EXECUTORS[name](ws, inp)
    art = ws.send_json.call_args[0][0]
    assert art["artifact_type"] == art_type
    assert isinstance(content, str) and content


# ---------------------------------------------------------------------------
# View-state authority (Phase 1) + state round-trip (Phase 2-A)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_render_gosling_records_view_state():
    """render_gosling must persist the spec on the session's view registry."""
    from webapp.backend.session import Session
    ws = AsyncMock()
    session = Session(session_id="s1")
    await TOOL_EXECUTORS["render_gosling"](
        ws, {"spec": {"tracks": [1]}, "title": "T", "_tool_use_id": "v1", "_session": session}
    )
    assert "v1" in session.views
    assert session.views["v1"].state["spec"] == {"tracks": [1]}
    assert session.views["v1"].revision == 1


@pytest.mark.asyncio
async def test_patch_gosling_updates_view_spec():
    """A valid patch deep-applies to the backend-authoritative spec."""
    from webapp.backend.session import Session
    ws = AsyncMock()
    session = Session(session_id="s1")
    await TOOL_EXECUTORS["render_gosling"](
        ws, {"spec": {"tracks": [{"mark": "bar"}]}, "_tool_use_id": "v1", "_session": session}
    )
    await TOOL_EXECUTORS["patch_gosling"](
        ws, {"target_id": "v1", "patch": {"op": "replace", "path": "/tracks/0/mark", "value": "line"},
             "_session": session}
    )
    assert session.views["v1"].state["spec"]["tracks"][0]["mark"] == "line"


@pytest.mark.asyncio
async def test_get_view_state_returns_view_and_lists():
    from webapp.backend.session import Session
    ws = AsyncMock()
    session = Session(session_id="s1")
    await TOOL_EXECUTORS["render_gosling"](
        ws, {"spec": {"tracks": []}, "title": "T", "_tool_use_id": "v1", "_session": session}
    )
    # By id
    content = await TOOL_EXECUTORS["get_view_state"](ws, {"view_id": "v1", "_session": session})
    payload = json.loads(content)
    assert payload["success"] is True
    assert payload["view"]["view_id"] == "v1"
    # List all
    content = await TOOL_EXECUTORS["get_view_state"](ws, {"_session": session})
    payload = json.loads(content)
    assert any(v["view_id"] == "v1" for v in payload["views"])
    # Missing id
    content = await TOOL_EXECUTORS["get_view_state"](ws, {"view_id": "nope", "_session": session})
    assert json.loads(content)["success"] is False


@pytest.mark.asyncio
async def test_query_user_interaction_nonblocking_reads_last():
    from webapp.backend.session import Session
    ws = AsyncMock()
    session = Session(session_id="s1")
    await TOOL_EXECUTORS["render_gosling"](
        ws, {"spec": {}, "_tool_use_id": "v1", "_session": session}
    )
    # No interaction yet -> null
    content = await TOOL_EXECUTORS["query_user_interaction"](
        ws, {"view_id": "v1", "_session": session}
    )
    assert json.loads(content)["interaction"] is None
    # Simulate a recorded interaction
    session.views["v1"].state["last_interaction"] = {
        "event_name": "brush_selection",
        "payload": {"chrom": "chr1", "start": 1, "end": 9},
        "timestamp": 123.0,
    }
    content = await TOOL_EXECUTORS["query_user_interaction"](
        ws, {"view_id": "v1", "_session": session}
    )
    inter = json.loads(content)["interaction"]
    assert inter["event_name"] == "brush_selection"
    assert inter["payload"]["end"] == 9


@pytest.mark.asyncio
async def test_query_user_interaction_blocking_times_out():
    from webapp.backend.session import Session
    ws = AsyncMock()
    session = Session(session_id="s1")
    content = await TOOL_EXECUTORS["query_user_interaction"](
        ws, {"view_id": "v1", "wait": True, "timeout_seconds": 0.05, "_session": session}
    )
    payload = json.loads(content)
    assert payload["interaction"] is None
    assert "No interaction" in payload["message"]


# ---------------------------------------------------------------------------
# Tier-2 component tree (Phase 2-B)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_render_component_emits_and_records():
    from webapp.backend.session import Session
    ws = AsyncMock()
    session = Session(session_id="s1")
    tree = {
        "component": "Row",
        "children": [
            {"component": "Panel", "props": {"title": "E"},
             "children": [{"component": "EmbeddingView"}]},
            {"component": "StructureView"},
        ],
    }
    content = await TOOL_EXECUTORS["render_component"](
        ws, {"tree": tree, "title": "Compare", "_tool_use_id": "c1", "_session": session}
    )
    art = ws.send_json.call_args[0][0]
    assert art["artifact_type"] == "component_tree"
    assert art["tree"]["component"] == "Row"
    assert json.loads(content)["success"] is True
    assert session.views["c1"].state["tree"] == tree


@pytest.mark.asyncio
async def test_render_component_rejects_unknown_component():
    """The whitelist is the security boundary — unknown nodes are rejected, no artifact."""
    ws = AsyncMock()
    bad = {"component": "ScriptTag", "props": {"src": "evil.js"}}
    content = await TOOL_EXECUTORS["render_component"](ws, {"tree": bad})
    payload = json.loads(content)
    assert payload["success"] is False
    assert "unknown component" in payload["error"].lower()
    ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_render_component_rejects_unknown_nested_component():
    ws = AsyncMock()
    bad = {
        "component": "Row",
        "children": [{"component": "Panel"}, {"component": "iframe"}],
    }
    content = await TOOL_EXECUTORS["render_component"](ws, {"tree": bad})
    assert json.loads(content)["success"] is False
    ws.send_json.assert_not_called()

