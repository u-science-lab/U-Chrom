"""Tests for ws_handler handle_message."""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from webapp.backend.ws_handler import handle_message, _looks_like_fofct, _load_chromdata
from webapp.backend.session import Session

from tests._agent_loop_harness import (
    text_block,
    turn,
    single_tool_then_done,
    drive_loop,
    artifacts,
)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_RICH_H5CD = os.path.join(_REPO_ROOT, "example-data", "rich_multicell.h5cd")

# A small FOF-CT core table in the exact shape of the Takei 2021 4DN dataset
# (4DNFIHF3JCBY): ``##``/``#`` header block, a ``##columns=`` meta line, then
# Spot_ID,Trace_ID,X,Y,Z,Chrom,Chrom_Start,Chrom_End,Cell_ID rows.
_FOFCT_SAMPLE = """\
##FOF-CT_version=v0.1
##genome_assembly=GRCm38/mm10
##XYZ_unit=micron
#lab_name: Cai
##columns=(Spot_ID,Trace_ID,X,Y,Z,Chrom,Chrom_Start,Chrom_End,Cell_ID)
705144,0_1_1_0,176.998,15.132,2.821,chr1,135625000,135650000,0_1
705145,0_1_1_0,176.953,15.056,2.771,chr1,135650000,135675000,0_1
705146,0_1_1_1,165.263,21.032,2.931,chr1,135650000,135675000,0_1
705147,0_1_1_0,176.965,15.131,2.591,chr1,135700000,135725000,0_1
"""


def _write_structure_csv(dest: str) -> None:
    """Export the in-repo rich_multicell dataset as a plain structure CSV."""
    from uchrom.core import ChromData
    cd = ChromData.read(_RICH_H5CD)
    cd.to_dataframe().to_csv(dest, index=False)


@pytest.mark.asyncio
async def test_run_agent_loop_streams_lifecycle_with_stable_id():
    """A pure-text turn must emit the streaming lifecycle with a stable id:

    message_start → agent_message_delta(message_id, index, text)* → message_stop.

    Deltas carry the same message_id and an index so the frontend can append
    text in-place to one bubble instead of spawning a bubble per delta.
    """
    sent, _history, _ = await drive_loop(
        [turn([text_block("Hello world")], "end_turn")],
        history=[{"role": "user", "content": "hi"}],
        deltas=[["Hello ", "world"]],
    )

    types = [m["type"] for m in sent]
    assert "message_start" in types
    assert "message_stop" in types

    starts = [m for m in sent if m["type"] == "message_start"]
    stops = [m for m in sent if m["type"] == "message_stop"]
    deltas = [m for m in sent if m["type"] == "agent_message_delta"]

    assert len(starts) == 1
    assert len(stops) == 1
    assert len(deltas) == 2

    # All frames share one stable, non-empty message_id.
    mid = starts[0]["message_id"]
    assert mid
    assert stops[0]["message_id"] == mid
    for d in deltas:
        assert d["message_id"] == mid
        assert "index" in d
        assert d["index"] == 0
    assert "".join(d["text"] for d in deltas) == "Hello world"

    # Lifecycle ordering: start before any delta, stop after the last delta.
    assert types.index("message_start") < types.index("agent_message_delta")
    last_delta = len(types) - 1 - types[::-1].index("agent_message_delta")
    assert last_delta < types.index("message_stop")


@pytest.mark.asyncio
async def test_run_agent_loop_forwards_content_block_boundaries():
    """The loop forwards content_block_start / content_block_stop with the id+index."""
    sent, _history, _ = await drive_loop(
        [turn([text_block("hi")], "end_turn")],
        history=[{"role": "user", "content": "hi"}],
        deltas=[["hi"]],
    )

    starts = [m for m in sent if m["type"] == "content_block_start"]
    stops = [m for m in sent if m["type"] == "content_block_stop"]
    assert len(starts) == 1
    assert len(stops) == 1
    assert starts[0]["block_type"] == "text"
    assert starts[0]["index"] == 0
    assert stops[0]["index"] == 0
    mid = [m for m in sent if m["type"] == "message_start"][0]["message_id"]
    assert starts[0]["message_id"] == mid
    assert stops[0]["message_id"] == mid


@pytest.mark.asyncio
async def test_handle_message_exists():
    """handle_message function should exist and be callable."""
    ws = AsyncMock()
    session = MagicMock()
    msg = {"type": "unknown"}
    executor = MagicMock()

    # Should not raise
    await handle_message(ws, session, msg, executor)


@pytest.mark.asyncio
async def test_handle_message_load_data():
    """load_data should update session.h5cd_path and send data_loaded."""
    ws = AsyncMock()
    session = Session()
    msg = {"type": "load_data", "payload": {"path": "/path/to/data.h5cd"}}
    executor = MagicMock()

    # load_data reads the file via ChromData.read; mock it so a fake path loads.
    fake_cd = MagicMock()
    fake_cd.cells.shape = (2, 1)
    fake_cd.coords.shape = (50, 3)
    with patch('os.path.exists', return_value=True), \
         patch('os.path.abspath', return_value="/absolute/path/to/data.h5cd"), \
         patch('uchrom.core.ChromData.read', return_value=fake_cd), \
         patch('webapp.backend.notebook_api.start_kernel', lambda: None):
        await handle_message(ws, session, msg, executor)

    assert session.h5cd_path == "/absolute/path/to/data.h5cd"
    # Sends 2 messages: data_loaded + confirmation text artifact
    assert ws.send_json.call_count == 2
    first_call = ws.send_json.call_args_list[0][0][0]
    assert first_call["type"] == "data_loaded"
    assert first_call["path"] == "/absolute/path/to/data.h5cd"


@pytest.mark.asyncio
async def test_handle_message_load_data_file_not_found():
    """load_data should reject non-existent files."""
    ws = AsyncMock()
    session = Session()
    msg = {"type": "load_data", "payload": {"path": "/nonexistent/data.h5cd"}}
    executor = MagicMock()

    with patch('os.path.exists', return_value=False), \
         patch('os.path.abspath', return_value="/nonexistent/data.h5cd"):
        await handle_message(ws, session, msg, executor)

    assert session.h5cd_path is None
    ws.send_json.assert_called_once()
    call_args = ws.send_json.call_args[0][0]
    assert call_args["type"] == "error"
    assert "File not found" in call_args["message"]


@pytest.mark.asyncio
async def test_handle_message_load_data_invalid_extension():
    """load_data should reject unsupported extensions (not h5cd/csv/fofct)."""
    ws = AsyncMock()
    session = Session()
    msg = {"type": "load_data", "payload": {"path": "/path/to/data.txt"}}
    executor = MagicMock()

    with patch('os.path.exists', return_value=True), \
         patch('os.path.abspath', return_value="/absolute/path/to/data.txt"):
        await handle_message(ws, session, msg, executor)

    assert session.h5cd_path is None
    ws.send_json.assert_called_once()
    call_args = ws.send_json.call_args[0][0]
    assert call_args["type"] == "error"
    assert "must be" in call_args["message"]


@pytest.mark.asyncio
async def test_handle_message_user_message():
    """user_message should invoke agent loop with session.conversation_history."""
    import asyncio
    ws = AsyncMock()
    session = Session()
    session.h5cd_path = "/path/to/data.h5cd"
    msg = {"type": "user_message", "payload": {"text": "Show me chr1"}}
    executor = MagicMock()

    # Mock run_agent_loop to avoid actual execution
    with patch('webapp.backend.ws_handler.run_agent_loop') as mock_agent:
        mock_agent.return_value = asyncio.Future()
        mock_agent.return_value.set_result(None)

        await handle_message(ws, session, msg, executor)

        # Verify run_agent_loop was called once
        mock_agent.assert_called_once()
        call_args = mock_agent.call_args
        assert call_args[0][0] == ws  # first arg should be ws

        # Second arg should be session.conversation_history (same object reference)
        assert call_args[0][1] is session.conversation_history

        # Verify message was appended to session history
        assert len(session.conversation_history) == 1
        assert session.conversation_history[0]["role"] == "user"
        assert session.conversation_history[0]["content"] == "Show me chr1"


@pytest.mark.asyncio
async def test_handle_message_user_message_multi_turn():
    """user_message should preserve conversation history across turns."""
    import asyncio
    ws = AsyncMock()
    session = Session()
    session.h5cd_path = "/path/to/data.h5cd"
    executor = MagicMock()

    # Mock run_agent_loop to avoid actual execution
    with patch('webapp.backend.ws_handler.run_agent_loop') as mock_agent:
        mock_agent.return_value = asyncio.Future()
        mock_agent.return_value.set_result(None)

        # First turn
        msg1 = {"type": "user_message", "payload": {"text": "Show me chr1"}}
        await handle_message(ws, session, msg1, executor)

        # Simulate assistant response
        session.conversation_history.append({"role": "assistant", "content": "Here is chr1"})

        # Second turn
        msg2 = {"type": "user_message", "payload": {"text": "Now show chr2"}}
        await handle_message(ws, session, msg2, executor)

        # Verify history contains all messages
        assert len(session.conversation_history) == 3
        assert session.conversation_history[0]["content"] == "Show me chr1"
        assert session.conversation_history[1]["content"] == "Here is chr1"
        assert session.conversation_history[2]["content"] == "Now show chr2"

        # Verify second call passed full history
        assert mock_agent.call_count == 2
        second_call_history = mock_agent.call_args[0][1]
        assert len(second_call_history) == 3


@pytest.mark.asyncio
async def test_run_agent_loop_uses_agent_tools():
    """run_agent_loop should forward all TOOLS to the streaming API call."""
    from webapp.backend.agent_tools import TOOLS

    _sent, _history, fake = await drive_loop(
        [turn([text_block("response")], "end_turn")],
        history=[{"role": "user", "content": "test"}],
    )

    # The real loop passes tools= to client.messages.stream(...); the harness
    # records the kwargs of the last stream() call.
    assert fake.messages.last_kwargs is not None
    assert "tools" in fake.messages.last_kwargs
    assert len(fake.messages.last_kwargs["tools"]) == len(TOOLS)


@pytest.mark.asyncio
async def test_load_data_sends_initial_viz():
    """load_data should send data_loaded + initial text artifact."""
    ws = AsyncMock()
    session = Session()
    msg = {"type": "load_data", "payload": {"path": "/path/to/data.h5cd"}}
    executor = MagicMock()

    fake_cd = MagicMock()
    fake_cd.cells.shape = (2, 1)
    fake_cd.coords.shape = (50, 3)
    with patch('os.path.exists', return_value=True), \
         patch('os.path.abspath', return_value="/path/to/data.h5cd"), \
         patch('uchrom.core.ChromData.read', return_value=fake_cd), \
         patch('webapp.backend.notebook_api.start_kernel', lambda: None):
        await handle_message(ws, session, msg, executor)

    assert ws.send_json.call_count == 2  # data_loaded + text artifact
    calls = [call[0][0] for call in ws.send_json.call_args_list]

    # First: data_loaded
    assert calls[0]["type"] == "data_loaded"

    # Second: text artifact with confirmation
    assert calls[1]["type"] == "artifact"
    assert calls[1]["artifact_type"] == "text"
    assert "Data loaded" in calls[1]["content"]


@pytest.mark.asyncio
async def test_run_agent_loop_add_notebook_cell():
    """run_agent_loop should handle add_notebook_cell tool."""
    with patch('webapp.backend.notebook_api.execute_code',
               return_value={"status": "ok", "output": "2", "error": None}):
        sent, _history, _ = await drive_loop(
            single_tool_then_done("add_notebook_cell", {"code": "1+1"}),
            history=[{"role": "user", "content": "Run 1+1"}],
        )

    notebook_cells = artifacts(sent, "notebook_cell")
    assert len(notebook_cells) == 1
    assert notebook_cells[0]["content"]["code"] == "1+1"
    assert notebook_cells[0]["content"]["output"] == "2"
    assert notebook_cells[0]["content"]["status"] == "ok"
    assert notebook_cells[0]["content"]["error"] is None


@pytest.mark.asyncio
async def test_run_agent_loop_run_analysis():
    """run_agent_loop should handle run_analysis tool (registry-based)."""
    fake_handle = {
        "type": "tad", "chrom": "chr21", "record_count": 3,
        "records": [{"chrom": "chr21", "start": 0, "end": 1000}],
        "data_url": "/api/tads/chr21?format=gosling",
        "chromosome_field": "chrom", "genomic_fields": ["start", "end"],
        "suggested_mark": "rule",
    }
    with patch('webapp.backend.strc_api.run_registered_analysis', return_value=fake_handle):
        sent, _history, _ = await drive_loop(
            single_tool_then_done("run_analysis", {"type": "tad", "region": "chr21"}),
            history=[{"role": "user", "content": "Analyze data"}],
        )

    analysis_artifacts = artifacts(sent, "analysis_result")
    assert len(analysis_artifacts) >= 1
    assert analysis_artifacts[0]["analysis_type"] == "tad"
    assert analysis_artifacts[0]["chrom"] == "chr21"


# --- CSV / FOF-CT dispatch ------------------------------------------------

def test_looks_like_fofct_discriminates(tmp_path):
    """Header/signature columns → FOF-CT; lowercase structure cols → not."""
    struct = tmp_path / "struct.csv"
    struct.write_text("chrom,start,end,x,y,z\nchr1,0,1000,1.0,2.0,3.0\n")
    assert _looks_like_fofct(str(struct)) is False

    fofct = tmp_path / "core.csv"
    fofct.write_text(_FOFCT_SAMPLE)
    assert _looks_like_fofct(str(fofct)) is True

    # Header-less FOF-CT recognised by signature columns alone.
    sig = tmp_path / "sig.csv"
    sig.write_text("Spot_ID,Trace_ID,X,Y,Z,Chrom,Chrom_Start,Chrom_End\n"
                   "1,0,1.0,2.0,3.0,chr1,0,1000\n")
    assert _looks_like_fofct(str(sig)) is True


def test_load_chromdata_structure_csv(tmp_path):
    """A plain structure CSV loads via from_dataframe."""
    csv = tmp_path / "struct.csv"
    _write_structure_csv(str(csv))
    cd = _load_chromdata(str(csv))
    assert cd.coords.shape[1] == 3
    assert cd.coords.shape[0] > 0


def test_load_chromdata_fofct_csv(tmp_path):
    """A FOF-CT core table loads via from_fofct."""
    csv = tmp_path / "core.csv"
    csv.write_text(_FOFCT_SAMPLE)
    cd = _load_chromdata(str(csv))
    assert cd.coords.shape == (4, 3)
    assert cd.uns.get("genome_assembly") == "GRCm38/mm10"


@pytest.mark.asyncio
async def test_handle_message_load_data_structure_csv(tmp_path):
    """load_data must accept a structure CSV, not reject it as non-h5cd."""
    csv = tmp_path / "struct.csv"
    _write_structure_csv(str(csv))

    ws = AsyncMock()
    session = Session()
    msg = {"type": "load_data", "payload": {"path": str(csv)}}

    with patch('webapp.backend.notebook_api.start_kernel', lambda: None), \
         patch('webapp.backend.notebook_api.seed_kernel', lambda *a, **k: None):
        await handle_message(ws, session, msg, MagicMock())

    assert session.h5cd_path == str(csv)
    assert session.chromdata is not None
    calls = [c[0][0] for c in ws.send_json.call_args_list]
    types = [c["type"] for c in calls]
    assert "error" not in types
    assert "data_loaded" in types
    loaded = next(c for c in calls if c["type"] == "data_loaded")
    assert loaded["n_spots"] > 0


@pytest.mark.asyncio
async def test_handle_message_load_data_fofct_csv(tmp_path):
    """load_data must accept a FOF-CT core table and seed via a temp .h5cd."""
    csv = tmp_path / "core.csv"
    csv.write_text(_FOFCT_SAMPLE)

    seeded = {}

    def _fake_seed(path, *a, **k):
        seeded["path"] = path

    ws = AsyncMock()
    session = Session()
    msg = {"type": "load_data", "payload": {"path": str(csv)}}

    with patch('webapp.backend.notebook_api.start_kernel', lambda: None), \
         patch('webapp.backend.notebook_api.seed_kernel', _fake_seed):
        await handle_message(ws, session, msg, MagicMock())

    assert session.chromdata is not None
    assert session.chromdata.coords.shape == (4, 3)
    types = [c[0][0]["type"] for c in ws.send_json.call_args_list]
    assert "error" not in types
    assert "data_loaded" in types
    # CSV inputs seed the kernel from a temporary .h5cd (not the .csv path),
    # so the notebook's `cd` matches the session without re-parsing the CSV.
    assert seeded["path"].endswith(".h5cd")
    assert seeded["path"] != str(csv)
    assert os.path.exists(seeded["path"])


# --- Tool-call lifecycle events (loading / result three-state UI) ----------

def _tool_events(sent, etype):
    return [m for m in sent if isinstance(m, dict) and m.get("type") == etype]


@pytest.mark.asyncio
async def test_tool_call_emits_start_and_ok_result():
    """A successful tool call emits tool_call_start (id+name) then a status=ok
    tool_call_result, in that order."""
    with patch('webapp.backend.notebook_api.execute_code',
               return_value={"status": "ok", "output": "2", "error": None}):
        sent, _history, _ = await drive_loop(
            single_tool_then_done("add_notebook_cell", {"code": "1+1"}, tool_id="tc1"),
            history=[{"role": "user", "content": "Run 1+1"}],
        )

    starts = _tool_events(sent, "tool_call_start")
    results = _tool_events(sent, "tool_call_result")
    assert len(starts) == 1
    assert len(results) == 1

    assert starts[0]["tool_use_id"] == "tc1"
    assert starts[0]["tool_name"] == "add_notebook_cell"

    assert results[0]["tool_use_id"] == "tc1"
    assert results[0]["tool_name"] == "add_notebook_cell"
    assert results[0]["status"] == "ok"

    # start precedes result for the same tool_use_id.
    types = [m["type"] for m in sent]
    assert types.index("tool_call_start") < types.index("tool_call_result")


@pytest.mark.asyncio
async def test_tool_call_result_error_explicit_success_false():
    """color_embedding with no color_by returns {success:false} → status=error."""
    sent, _history, _ = await drive_loop(
        single_tool_then_done("color_embedding", {}, tool_id="tc3"),
        history=[{"role": "user", "content": "Color it"}],
    )
    results = _tool_events(sent, "tool_call_result")
    assert len(results) == 1
    assert results[0]["tool_use_id"] == "tc3"
    assert results[0]["status"] == "error"
    assert results[0]["summary"]  # carries the validation error one-liner


@pytest.mark.asyncio
async def test_tool_call_result_error_on_executor_exception():
    """An executor that raises (unknown internal failure) → status=error."""
    from webapp.backend import tool_executors

    async def _boom(ws, ti):
        raise RuntimeError("kaboom")

    with patch.dict(tool_executors.TOOL_EXECUTORS, {"add_notebook_cell": _boom}):
        sent, _history, _ = await drive_loop(
            single_tool_then_done("add_notebook_cell", {"code": "x"}, tool_id="tc4"),
            history=[{"role": "user", "content": "go"}],
        )

    results = _tool_events(sent, "tool_call_result")
    assert len(results) == 1
    assert results[0]["status"] == "error"
    assert "kaboom" in (results[0]["summary"] or "")


@pytest.mark.asyncio
async def test_unknown_tool_emits_error_result():
    """An unregistered tool name emits a status=error tool_call_result."""
    sent, _history, _ = await drive_loop(
        single_tool_then_done("no_such_tool", {}, tool_id="tc5"),
        history=[{"role": "user", "content": "go"}],
    )
    results = _tool_events(sent, "tool_call_result")
    assert len(results) == 1
    assert results[0]["status"] == "error"
    assert "Unknown tool" in (results[0]["summary"] or "")


def test_tool_status_classifier_handles_dict_and_str():
    """_tool_status_and_summary covers the dict/str/exception return shapes."""
    from webapp.backend.ws_handler import _tool_status_and_summary
    import json as _json

    # Vision tool's structured image return → ok.
    s, _ = _tool_status_and_summary({"_content_blocks": [{"type": "text"}]}, False)
    assert s == "ok"
    # Dict with explicit failure → error.
    s, summ = _tool_status_and_summary({"success": False, "error": "nope"}, False)
    assert s == "error" and summ == "nope"
    # JSON string with success:false → error.
    s, summ = _tool_status_and_summary(_json.dumps({"success": False, "error": "bad"}), False)
    assert s == "error" and summ == "bad"
    # JSON string with success:true + message → ok, summary is the message.
    s, summ = _tool_status_and_summary(_json.dumps({"success": True, "message": "did it"}), False)
    assert s == "ok" and summ == "did it"
    # Plain (non-JSON) string → ok.
    s, _ = _tool_status_and_summary("Cell added. Output: 2", False)
    assert s == "ok"
    # Executor failure flag → error regardless of content.
    s, summ = _tool_status_and_summary(_json.dumps({"success": False, "error": "x failed: y"}), True)
    assert s == "error" and "y" in summ

