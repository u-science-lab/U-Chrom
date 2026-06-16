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


@pytest.fixture(autouse=True)
def _clear_current_session():
    import webapp.backend.data_api as _data_api

    previous = getattr(_data_api, "current_session", None)
    _data_api.current_session = None
    try:
        yield
    finally:
        _data_api.current_session = previous


def test_every_tool_has_an_executor():
    """TOOLS and TOOL_EXECUTORS must be in 1:1 correspondence.

    color_embedding / show_structure / color_structure are now wired up (第二波)
    and exposed in TOOLS, so the registry is symmetric again: every schema has
    an executor and every executor has a schema.
    """
    tool_names = {t["name"] for t in TOOLS}
    executor_names = set(TOOL_EXECUTORS)

    schema_only = tool_names - executor_names
    assert not schema_only, f"schema without executor: {schema_only}"

    executor_only = executor_names - tool_names
    assert not executor_only, f"executor without schema: {executor_only}"


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
async def test_render_gosling_normalizes_local_contact_matrix_for_gosling_1x():
    """Agent-generated contact specs should match Gosling 1.0.7's matrix shape."""
    ws = AsyncMock()
    await TOOL_EXECUTORS["render_gosling"](
        ws,
        {
            "spec": {
                "assembly": "hg38",
                "layout": "linear",
                "xDomain": {"chromosome": "chr1", "interval": [0, 50_000_000]},
                "tracks": [
                    {
                        "title": "Hi-C Contact Matrix",
                        "data": {
                            "type": "matrix",
                            "url": "/api/v1/tileset_info/?d=contact-chr1",
                        },
                        "mark": "rect",
                        "x": {"field": "start1", "type": "genomic"},
                        "xe": {"field": "end1", "type": "genomic"},
                        "y": {"field": "start2", "type": "genomic"},
                        "ye": {"field": "end2", "type": "genomic"},
                        "color": {"field": "value", "type": "quantitative"},
                    },
                    {
                        "title": "Chromosome Ideogram",
                        "alignment": "overlay",
                        "data": {
                            "type": "csv",
                            "url": "https://example.com/cytoband.csv",
                            "chromosomeField": "Chr",
                            "genomicFields": ["ISCN_start", "ISCN_stop"],
                        },
                        "mark": "rect",
                    },
                ],
            },
            "title": "Contact",
            "_tool_use_id": "u1",
        },
    )

    art = ws.send_json.call_args[0][0]
    matrix_track = art["spec"]["tracks"][0]
    assert matrix_track["mark"] == "bar"
    assert matrix_track["x"]["field"] == "xs"
    assert matrix_track["xe"]["field"] == "xe"
    assert matrix_track["y"]["field"] == "ys"
    assert matrix_track["ye"]["field"] == "ye"
    assert "alignment" not in art["spec"]["tracks"][1]


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
async def test_run_analysis_emits_render_metadata_and_annotations(monkeypatch):
    from webapp.backend.session import Session

    ws = AsyncMock()
    session = Session(session_id="analysis-session")
    fake_handle = {
        "type": "compartment",
        "chrom": "chr1",
        "record_count": 2,
        "records": [
            {"chrom": "chr1", "start": 0, "end": 150, "compartment": "A", "score": 0.8},
            {"chrom": "chr1", "start": 150, "end": 300, "compartment": "B", "score": -0.6},
        ],
        "data_url": "/api/compartments/chr1?format=gosling",
        "chromosome_field": "chrom",
        "genomic_fields": ["start", "end"],
        "suggested_mark": "rect",
    }
    import webapp.backend.strc_api as strc_api
    monkeypatch.setattr(strc_api, "run_registered_analysis", lambda t, c: fake_handle)

    content = await TOOL_EXECUTORS["run_analysis"](
        ws, {"type": "compartment", "region": "chr1:1-300", "_session": session}
    )

    art = ws.send_json.call_args[0][0]
    assert art["artifact_type"] == "analysis_result"
    assert art["data_url"] == "/api/compartments/chr1?format=gosling"
    assert art["record_count"] == 2
    assert art["genomic_fields"] == ["start", "end"]
    assert art["suggested_mark"] == "rect"
    payload = json.loads(content)
    assert payload["record_count"] == 2
    assert payload["data_url"] == "/api/compartments/chr1?format=gosling"
    assert session.analysis_annotations["compartment:chr1"]["records"] == fake_handle["records"]


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
# Linkage tools (第二波): real artifacts + validation against live ChromData
# ---------------------------------------------------------------------------

class _FakeCell:
    def __init__(self, spots):
        self.spots = spots


class _FakeCD:
    """Minimal ChromData stand-in for executor validation tests."""
    def __init__(self, cells=None, spots=None, cell_map=None):
        self.cells = cells
        self.spots = spots
        self._cell_map = cell_map or {}

    def get_cell(self, cid):
        return self._cell_map.get(str(cid), _FakeCell(_EmptySpots()))


class _EmptySpots:
    def __len__(self):
        return 0


def _session_with(cd):
    from types import SimpleNamespace
    return SimpleNamespace(chromdata=cd)


@pytest.mark.asyncio
async def test_color_embedding_emits_color_by():
    ws = AsyncMock()
    content = await TOOL_EXECUTORS["color_embedding"](ws, {"color_by": "cell_type"})
    art = ws.send_json.call_args[0][0]
    assert art["artifact_type"] == "color_embedding"
    assert art["color_by"] == "cell_type"
    assert json.loads(content)["success"] is True


@pytest.mark.asyncio
async def test_color_embedding_rejects_unknown_field():
    import pandas as pd
    cells = pd.DataFrame({"cell_type": ["typeA", "typeB"]},
                         index=pd.Index(["c0", "c1"], name="cell_id"))
    ws = AsyncMock()
    content = await TOOL_EXECUTORS["color_embedding"](
        ws, {"color_by": "nope", "_session": _session_with(_FakeCD(cells=cells))}
    )
    payload = json.loads(content)
    assert payload["success"] is False
    assert "not a cell field" in payload["error"]
    ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_color_embedding_requires_color_by():
    ws = AsyncMock()
    content = await TOOL_EXECUTORS["color_embedding"](ws, {"color_by": ""})
    assert json.loads(content)["success"] is False
    ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_show_structure_emits_cell_id():
    ws = AsyncMock()
    content = await TOOL_EXECUTORS["show_structure"](ws, {"cell_id": "c1", "chrom": "chr1"})
    art = ws.send_json.call_args[0][0]
    assert art["artifact_type"] == "show_structure"
    assert art["cell_id"] == "c1"
    assert art["chrom"] == "chr1"
    assert json.loads(content)["success"] is True


@pytest.mark.asyncio
async def test_show_structure_requires_cell_id():
    ws = AsyncMock()
    content = await TOOL_EXECUTORS["show_structure"](ws, {"cell_id": ""})
    assert json.loads(content)["success"] is False
    ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_show_structure_rejects_missing_cell():
    import pandas as pd
    cd = _FakeCD(cell_map={})  # get_cell returns empty spots → cell not found
    cd.spots = pd.DataFrame({"chrom": ["chr1"]})
    ws = AsyncMock()
    content = await TOOL_EXECUTORS["show_structure"](
        ws, {"cell_id": "ghost", "_session": _session_with(cd)}
    )
    payload = json.loads(content)
    assert payload["success"] is False
    assert "no cell" in payload["error"]
    ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_color_structure_emits_color_by():
    ws = AsyncMock()
    content = await TOOL_EXECUTORS["color_structure"](ws, {"color_by": "chrom"})
    art = ws.send_json.call_args[0][0]
    assert art["artifact_type"] == "color_structure"
    assert art["color_by"] == "chrom"
    assert json.loads(content)["success"] is True


@pytest.mark.asyncio
async def test_color_structure_rejects_unknown_field():
    import pandas as pd
    spots = pd.DataFrame({"chrom": ["chr1"], "start": [0], "end": [1],
                          "trace_id": ["t0"], "cell_id": ["c0"]})
    ws = AsyncMock()
    content = await TOOL_EXECUTORS["color_structure"](
        ws, {"color_by": "compartment", "_session": _session_with(_FakeCD(spots=spots))}
    )
    payload = json.loads(content)
    assert payload["success"] is False
    assert "not a spot field" in payload["error"]
    ws.send_json.assert_not_called()


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


@pytest.mark.asyncio
async def test_render_component_accepts_safe_action_id():
    ws = AsyncMock()
    tree = {
        "component": "Button",
        "props": {
            "label": "Apply",
            "action_id": "apply_region",
            "aria_label": "Apply selected region",
        },
    }
    content = await TOOL_EXECUTORS["render_component"](ws, {"tree": tree})
    payload = json.loads(content)
    assert payload["success"] is True
    art = ws.send_json.call_args[0][0]
    assert art["tree"]["props"]["action_id"] == "apply_region"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_id", ["", "../escape", "bad id", "x" * 81])
async def test_render_component_rejects_bad_action_id(bad_id):
    ws = AsyncMock()
    tree = {"component": "Button", "props": {"label": "Apply", "action_id": bad_id}}
    content = await TOOL_EXECUTORS["render_component"](ws, {"tree": tree})
    payload = json.loads(content)
    assert payload["success"] is False
    assert "action_id" in payload["error"]
    ws.send_json.assert_not_called()
