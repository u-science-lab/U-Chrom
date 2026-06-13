"""Tests for agent linkage-tool dispatch in run_agent_loop.

Covers the Phase 1+ tools: select_cells, color_embedding, show_structure,
color_structure, export_view, patch_gosling, run_analysis (type/region →
strc_api), and write_analysis_function. Each test drives the *full*
run_agent_loop and asserts on the artifacts / tool_results it produces,
mocking only the Anthropic boundary (via tests/_agent_loop_harness). This keeps
the tests link-level rather than poking individual executors.
"""
import json

from tests._agent_loop_harness import (
    single_tool_then_done,
    run_loop,
    artifacts,
    tool_results,
)


def _run(tool_name, tool_input):
    """Drive run_agent_loop for a single tool call; return sent messages."""
    sent, _history, _fake = run_loop(single_tool_then_done(tool_name, tool_input))
    return sent


def test_select_cells_sends_artifact():
    sent = _run("select_cells", {"cell_ids": ["c0", "c1", "c2"]})
    arts = artifacts(sent, "select_cells")
    assert len(arts) == 1
    assert arts[0]["cell_ids"] == ["c0", "c1", "c2"]
    assert arts[0]["type"] == "agent_artifact"


def test_color_embedding_sends_artifact():
    sent = _run("color_embedding", {"color_by": "cell_type"})
    arts = artifacts(sent, "color_embedding")
    assert len(arts) == 1
    assert arts[0]["color_by"] == "cell_type"


def test_show_structure_sends_artifact():
    sent = _run("show_structure", {"cell_id": "c5", "chrom": "chr21"})
    arts = artifacts(sent, "show_structure")
    assert len(arts) == 1
    assert arts[0]["cell_id"] == "c5"
    assert arts[0]["chrom"] == "chr21"


def test_color_structure_sends_artifact():
    sent = _run("color_structure", {"color_by": "compartment"})
    arts = artifacts(sent, "color_structure")
    assert len(arts) == 1
    assert arts[0]["color_by"] == "compartment"


def test_export_view_sends_artifact():
    sent = _run("export_view", {"format": "pdf"})
    arts = artifacts(sent, "export_view")
    assert len(arts) == 1
    assert arts[0]["format"] == "pdf"


def test_export_view_defaults_to_png():
    sent = _run("export_view", {})
    arts = artifacts(sent, "export_view")
    assert len(arts) == 1
    assert arts[0]["format"] == "png"


def test_patch_gosling_forwards_patch():
    sent = _run("patch_gosling", {
        "target_id": "viz_1",
        "patch": {"op": "replace", "path": "/views/0/tracks/0/mark", "value": "bar"},
    })
    arts = artifacts(sent, "gosling_patch")
    assert len(arts) == 1
    assert arts[0]["target_id"] == "viz_1"
    assert arts[0]["patch"]["path"] == "/views/0/tracks/0/mark"
    assert arts[0]["patch"]["value"] == "bar"


def test_patch_gosling_missing_fields_reports_error():
    """A patch with no target_id/path is rejected *before* any artifact is
    emitted: no gosling_patch artifact, and the tool_result flags the failure
    so the agent can correct itself."""
    sent, history, _ = run_loop(
        single_tool_then_done("patch_gosling", {"patch": {"op": "replace"}})
    )

    # Validate-before-emit: no artifact for the rejected patch.
    assert artifacts(sent, "gosling_patch") == []

    results = tool_results(history)
    assert len(results) == 1
    payload = json.loads(results[0]["content"])
    assert payload["success"] is False


def test_run_analysis_dispatches_to_strc_api():
    """run_analysis(type='tad', region='chr21') routes through
    run_registered_analysis → get_tads('chr21') and emits an analysis_result
    artifact whose result re-wraps the records under the '<type>s' key."""
    from unittest.mock import patch

    fake = {"tads": [{"start": 0, "end": 1000}, {"start": 1000, "end": 2000}]}
    with patch("webapp.backend.strc_api.get_tads", return_value=fake) as gt:
        sent, _history, _ = run_loop(
            single_tool_then_done("run_analysis", {"type": "tad", "region": "chr21"})
        )

    gt.assert_called_once_with("chr21")
    arts = artifacts(sent, "analysis_result")
    assert len(arts) == 1
    assert arts[0]["analysis_type"] == "tad"
    assert arts[0]["chrom"] == "chr21"
    # _run_analysis re-wraps records under "<type>s"; the raw getter dict is
    # parsed by _records_from_response (which tolerates a plain dict).
    assert arts[0]["result"] == {"tads": fake["tads"]}


def test_run_analysis_tool_result_carries_render_handle():
    """The tool_result fed back to Claude must include the data_url + field
    names + suggested_mark so the agent can chain into render_gosling."""
    from unittest.mock import patch

    fake = {"tads": [{"chrom": "chr21", "start": 0, "end": 1000}]}
    with patch("webapp.backend.strc_api.get_tads", return_value=fake):
        _sent, history, _ = run_loop(
            single_tool_then_done("run_analysis", {"type": "tad", "region": "chr21"})
        )

    results = tool_results(history)
    assert len(results) == 1
    payload = json.loads(results[0]["content"])
    assert payload["success"] is True
    assert payload["data_url"] == "/api/tads/chr21?format=gosling"
    assert payload["chromosome_field"] == "chrom"
    assert payload["genomic_fields"] == ["start", "end"]
    assert payload["suggested_mark"] == "rule"
    assert payload["record_count"] == 1
    assert "render_gosling" in payload["next_step"]


def test_unknown_tool_returns_error_result():
    """An unrecognized tool name still completes with an error tool_result and
    emits no artifact."""
    sent = _run("nonexistent_tool", {})
    assert artifacts(sent, "nonexistent_tool") == []


_GOOD_ANALYSIS = (
    "def analyze(cd, chrom, **params):\n"
    "    n = cd.coords.shape[0]\n"
    "    starts = cd.spots['start'].to_numpy()\n"
    "    return pd.DataFrame({'chrom': [chrom]*n, 'start': starts, 'end': starts+1})\n"
)


def _run_capture_history(tool_name, tool_input):
    """Drive run_agent_loop once with a clean registry; return (sent, history)."""
    import webapp.backend.dynamic_api as dynamic_api

    dynamic_api.clear_registry()
    sent, history, _ = run_loop(single_tool_then_done(tool_name, tool_input))
    return sent, history


def _json_tool_results(history):
    """tool_result contents, JSON-decoded where possible."""
    out = []
    for block in tool_results(history):
        content = block["content"]
        try:
            out.append(json.loads(content))
        except (ValueError, TypeError):
            out.append(content)
    return out


def test_write_analysis_deploys_and_returns_handle():
    sent, history = _run_capture_history("write_analysis_function", {
        "name": "myrg",
        "code": _GOOD_ANALYSIS,
        "chromosome_field": "chrom",
        "genomic_fields": ["start", "end"],
        "suggested_mark": "line",
    })

    arts = artifacts(sent, "custom_analysis_deployed")
    assert len(arts) == 1
    assert arts[0]["analysis_id"] == "myrg"
    assert arts[0]["data_url"] == "/api/custom/myrg/{chrom}?format=gosling"

    results = _json_tool_results(history)
    assert len(results) == 1
    payload = results[0]
    assert payload["success"] is True
    assert payload["data_url"] == "/api/custom/myrg/{chrom}?format=gosling"
    assert payload["chromosome_field"] == "chrom"
    assert payload["genomic_fields"] == ["start", "end"]
    assert payload["suggested_mark"] == "line"
    assert "render_gosling" in payload["next_step"]


def test_write_analysis_rejects_malicious():
    sent, history = _run_capture_history("write_analysis_function", {
        "name": "evil",
        "code": "import os\ndef analyze(cd, chrom, **p):\n    return os.listdir('/')\n",
    })

    # No deploy artifact for rejected code.
    assert artifacts(sent, "custom_analysis_deployed") == []

    results = _json_tool_results(history)
    assert len(results) == 1
    payload = results[0]
    assert payload["success"] is False
    assert "Rejected by sandbox" in payload["error"]
    assert "hint" in payload
