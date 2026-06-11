"""Tests for agent linkage-tool dispatch in run_agent_loop.

Covers the Phase 1 tools whose executors were previously missing:
select_cells, color_embedding, show_structure, color_structure, and the
rewritten run_analysis (type/region → strc_api). Drives run_agent_loop
with a mocked Anthropic client so no network/API key is needed.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_block(tool_id, name, inp):
    return SimpleNamespace(type="tool_use", id=tool_id, name=name, input=inp)


def _response(blocks, stop_reason):
    return SimpleNamespace(content=blocks, stop_reason=stop_reason)


def _run(tool_name, tool_input, second_text="done"):
    """Drive run_agent_loop for a single tool call; return sent messages.

    The mocked client returns a tool_use turn first, then an end_turn turn,
    so the loop dispatches the tool exactly once and exits.
    """
    from webapp.backend import ws_handler

    responses = [
        _response([_tool_block("t1", tool_name, tool_input)], "tool_use"),
        _response([_text_block(second_text)], "end_turn"),
    ]
    call_iter = iter(responses)

    ws = AsyncMock()
    sent = []
    async def _capture(obj):
        sent.append(obj)
    ws.send_json = _capture

    async def _create(**kwargs):
        return next(call_iter)

    with patch.object(ws_handler.client, "messages") as messages:
        messages.create = AsyncMock(side_effect=_create)
        asyncio.run(ws_handler.run_agent_loop(ws, [{"role": "user", "content": "hi"}]))
    return sent


def _artifacts(sent, artifact_type):
    return [m for m in sent if m.get("artifact_type") == artifact_type]


def test_select_cells_sends_artifact():
    sent = _run("select_cells", {"cell_ids": ["c0", "c1", "c2"]})
    arts = _artifacts(sent, "select_cells")
    assert len(arts) == 1
    assert arts[0]["cell_ids"] == ["c0", "c1", "c2"]
    assert arts[0]["type"] == "agent_artifact"


def test_color_embedding_sends_artifact():
    sent = _run("color_embedding", {"color_by": "cell_type"})
    arts = _artifacts(sent, "color_embedding")
    assert len(arts) == 1
    assert arts[0]["color_by"] == "cell_type"


def test_show_structure_sends_artifact():
    sent = _run("show_structure", {"cell_id": "c5", "chrom": "chr21"})
    arts = _artifacts(sent, "show_structure")
    assert len(arts) == 1
    assert arts[0]["cell_id"] == "c5"
    assert arts[0]["chrom"] == "chr21"


def test_color_structure_sends_artifact():
    sent = _run("color_structure", {"color_by": "compartment"})
    arts = _artifacts(sent, "color_structure")
    assert len(arts) == 1
    assert arts[0]["color_by"] == "compartment"


def test_export_view_sends_artifact():
    sent = _run("export_view", {"format": "pdf"})
    arts = _artifacts(sent, "export_view")
    assert len(arts) == 1
    assert arts[0]["format"] == "pdf"


def test_export_view_defaults_to_png():
    sent = _run("export_view", {})
    arts = _artifacts(sent, "export_view")
    assert len(arts) == 1
    assert arts[0]["format"] == "png"


def test_patch_gosling_forwards_patch():
    sent = _run("patch_gosling", {
        "target_id": "viz_1",
        "patch": {"op": "replace", "path": "/views/0/tracks/0/mark", "value": "bar"},
    })
    arts = _artifacts(sent, "gosling_patch")
    assert len(arts) == 1
    assert arts[0]["target_id"] == "viz_1"
    assert arts[0]["patch"]["path"] == "/views/0/tracks/0/mark"
    assert arts[0]["patch"]["value"] == "bar"


def test_patch_gosling_missing_fields_reports_error():
    """A patch with no target_id/path still emits an artifact but the tool_result
    flags the failure so the agent can correct itself."""
    import json
    from webapp.backend import ws_handler

    history = [{"role": "user", "content": "patch"}]
    with patch.object(ws_handler, "client") as _client:
        responses = iter([
            _response([_tool_block("t1", "patch_gosling", {"patch": {"op": "replace"}})], "tool_use"),
            _response([_text_block("done")], "end_turn"),
        ])
        _client.messages.create = AsyncMock(side_effect=lambda **k: next(responses))
        ws = AsyncMock()
        async def _capture(obj):
            pass
        ws.send_json = _capture
        asyncio.run(ws_handler.run_agent_loop(ws, history))

    tool_results = [
        block
        for msg in history
        if msg["role"] == "user" and isinstance(msg["content"], list)
        for block in msg["content"]
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]
    assert len(tool_results) == 1
    payload = json.loads(tool_results[0]["content"])
    assert payload["success"] is False


def test_run_analysis_dispatches_to_strc_api():
    """run_analysis(type='tad', region='chr21') calls get_tads and emits result."""
    from webapp.backend import ws_handler

    fake = {"tads": [{"start": 0, "end": 1000}, {"start": 1000, "end": 2000}]}
    with patch.object(ws_handler, "client") as _client, \
         patch("webapp.backend.strc_api.get_tads", return_value=fake) as gt:
        # rebuild messages mock since we patched the whole client
        responses = iter([
            _response([_tool_block("t1", "run_analysis", {"type": "tad", "region": "chr21"})], "tool_use"),
            _response([_text_block("done")], "end_turn"),
        ])
        _client.messages.create = AsyncMock(side_effect=lambda **k: next(responses))

        ws = AsyncMock()
        sent = []

        async def _capture(obj):
            sent.append(obj)
        ws.send_json = _capture

        asyncio.run(ws_handler.run_agent_loop(ws, [{"role": "user", "content": "hi"}]))

    gt.assert_called_once_with("chr21")
    arts = [m for m in sent if m.get("artifact_type") == "analysis_result"]
    assert len(arts) == 1
    assert arts[0]["analysis_type"] == "tad"
    assert arts[0]["chrom"] == "chr21"
    assert arts[0]["result"] == fake


def test_run_analysis_tool_result_carries_render_handle():
    """The tool_result fed back to Claude must include the data_url + field
    names + suggested_mark so the agent can chain into render_gosling."""
    import json
    from webapp.backend import ws_handler

    fake = {"tads": [{"chrom": "chr21", "start": 0, "end": 1000}]}
    history = [{"role": "user", "content": "call tad"}]
    with patch.object(ws_handler, "client") as _client, \
         patch("webapp.backend.strc_api.get_tads", return_value=fake):
        responses = iter([
            _response([_tool_block("t1", "run_analysis", {"type": "tad", "region": "chr21"})], "tool_use"),
            _response([_text_block("done")], "end_turn"),
        ])
        _client.messages.create = AsyncMock(side_effect=lambda **k: next(responses))

        ws = AsyncMock()
        async def _capture(obj):
            pass
        ws.send_json = _capture

        asyncio.run(ws_handler.run_agent_loop(ws, history))

    # Find the tool_result the loop appended to history.
    tool_results = [
        block
        for msg in history
        if msg["role"] == "user" and isinstance(msg["content"], list)
        for block in msg["content"]
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]
    assert len(tool_results) == 1
    payload = json.loads(tool_results[0]["content"])
    assert payload["success"] is True
    assert payload["data_url"] == "/api/tads/chr21?format=gosling"
    assert payload["chromosome_field"] == "chrom"
    assert payload["genomic_fields"] == ["start", "end"]
    assert payload["suggested_mark"] == "rule"
    assert payload["record_count"] == 1
    assert "render_gosling" in payload["next_step"]


def test_unknown_tool_returns_error_result():
    """An unrecognized tool name still completes with an error tool_result."""
    # Should not raise; loop exits after end_turn.
    sent = _run("nonexistent_tool", {})
    # No artifact emitted for unknown tool, but the loop completed.
    assert _artifacts(sent, "nonexistent_tool") == []
