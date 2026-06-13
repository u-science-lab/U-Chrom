"""Tests for ws_handler handle_message."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from webapp.backend.ws_handler import handle_message
from webapp.backend.session import Session

from tests._agent_loop_harness import (
    text_block,
    turn,
    single_tool_then_done,
    drive_loop,
    artifacts,
)


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
    """load_data should reject non-.h5cd files."""
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
    assert ".h5cd format" in call_args["message"]


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
