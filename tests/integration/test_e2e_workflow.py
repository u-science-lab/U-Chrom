"""End-to-end integration tests for Analysis Workbench workflow.

These drive the full WS message path and agent loop, mocking only the
Anthropic boundary (via tests/_agent_loop_harness) and the kernel/strc
side-effects. Pure single-tool dispatch is covered at the link level in
tests/test_agent_linkage_tools.py and tests/backend/test_ws_handler.py; this
file keeps the genuinely end-to-end pathways: the load_data → kernel → agent
hand-off, the notebook error path, and multi-tool-per-turn dispatch.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from webapp.backend.ws_handler import handle_message
from webapp.backend.session import Session

from tests._agent_loop_harness import (
    text_block,
    tool_block,
    turn,
    single_tool_then_done,
    drive_loop,
    artifacts,
)


@pytest.mark.asyncio
async def test_full_workflow_load_data_to_notebook():
    """Complete workflow: load_data → kernel start → agent → notebook cell."""
    ws = AsyncMock()
    session = Session()
    executor = MagicMock()

    # Step 1: Load data (real handle_message path; mock the file + kernel).
    fake_cd = MagicMock()
    fake_cd.cells.shape = (2, 1)
    fake_cd.coords.shape = (50, 3)
    with patch('webapp.backend.notebook_api.start_kernel') as mock_start_kernel, \
         patch('os.path.exists', return_value=True), \
         patch('uchrom.core.ChromData.read', return_value=fake_cd):
        await handle_message(ws, session, {
            "type": "load_data",
            "payload": {"path": "/fake/data.h5cd"}
        }, executor)

    mock_start_kernel.assert_called_once()
    calls = [call[0][0] for call in ws.send_json.call_args_list]
    assert any('data_loaded' in json.dumps(call) for call in calls), "data_loaded not sent"
    assert any('artifact' in json.dumps(call) and 'Data loaded' in json.dumps(call)
               for call in calls), "Initial artifact not sent"

    # Step 2: Agent adds a notebook cell (full streaming loop via harness).
    with patch('webapp.backend.notebook_api.execute_code',
               return_value={"status": "ok", "output": "Result: 42"}) as mock_execute:
        sent, _history, _ = await drive_loop(
            single_tool_then_done("add_notebook_cell", {"code": "print(42)"}),
            history=[{"role": "user", "content": "Calculate 42"}],
        )

    mock_execute.assert_called_once_with("print(42)")
    notebook_artifacts = artifacts(sent, "notebook_cell")
    assert len(notebook_artifacts) >= 1, "notebook_cell artifact not sent"
    # notebook_cell travels on the agent_artifact channel so the frontend
    # ARTIFACT_HANDLERS picks it up like every other agent-driven UI effect.
    artifact = notebook_artifacts[0]
    assert artifact["type"] == "agent_artifact"
    assert artifact["artifact_type"] == "notebook_cell"
    assert artifact["content"]["code"] == "print(42)"
    assert artifact["content"]["output"] == "Result: 42"
    assert artifact["content"]["status"] == "ok"


@pytest.mark.asyncio
async def test_agent_error_handling():
    """Agent surfaces a notebook execution error on the notebook_cell artifact."""
    with patch('webapp.backend.notebook_api.execute_code', return_value={
        "status": "error",
        "output": "",
        "error": "ValueError: test error",
    }):
        sent, _history, _ = await drive_loop(
            single_tool_then_done(
                "add_notebook_cell", {"code": "raise ValueError('test error')"}
            ),
            history=[{"role": "user", "content": "Test error"}],
        )

    notebook_artifacts = artifacts(sent, "notebook_cell")
    assert len(notebook_artifacts) >= 1
    artifact = notebook_artifacts[0]
    assert artifact["content"]["status"] == "error"
    assert artifact["content"]["error"] == "ValueError: test error"


@pytest.mark.asyncio
async def test_multiple_tool_calls_in_sequence():
    """Two tool_use blocks in a single turn are each dispatched and executed."""
    two_tools_then_done = [
        turn([
            tool_block("t1", "add_notebook_cell", {"code": "x = 1"}),
            tool_block("t2", "add_notebook_cell", {"code": "print(x)"}),
        ], "tool_use"),
        turn([text_block("Both executed")], "end_turn"),
    ]
    with patch('webapp.backend.notebook_api.execute_code',
               return_value={"status": "ok", "output": "1"}) as mock_execute:
        sent, _history, _ = await drive_loop(
            two_tools_then_done,
            history=[{"role": "user", "content": "Run two commands"}],
        )

    assert mock_execute.call_count == 2
    notebook_artifacts = artifacts(sent, "notebook_cell")
    assert len(notebook_artifacts) == 2, "expected two notebook_cell artifacts"
