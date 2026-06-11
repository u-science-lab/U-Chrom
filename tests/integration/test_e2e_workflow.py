"""End-to-end integration tests for Analysis Workbench workflow."""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from webapp.backend.ws_handler import handle_message, run_agent_loop
from webapp.backend.session import Session


@pytest.mark.asyncio
async def test_full_workflow_load_data_to_notebook():
    """Test complete workflow: load_data → agent interaction → notebook cell execution."""

    # Mock WebSocket
    ws = AsyncMock()

    # Create session
    session = Session()

    # Mock executor (not used in load_data flow but required by handle_message signature)
    executor = MagicMock()

    # Step 1: Load data
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

    # Verify kernel was started
    mock_start_kernel.assert_called_once()

    # Verify data loaded message sent
    calls = [call[0][0] for call in ws.send_json.call_args_list]
    assert any('data_loaded' in json.dumps(call) for call in calls), "data_loaded message not sent"

    # Verify initial artifact sent (current text is "Data loaded: ...")
    assert any('artifact' in json.dumps(call) and 'Data loaded' in json.dumps(call)
               for call in calls), "Initial artifact not sent"

    # Step 2: Agent adds notebook cell
    ws.reset_mock()  # Clear previous calls

    with patch('webapp.backend.notebook_api.execute_code', return_value={
        "status": "ok",
        "output": "Result: 42"
    }) as mock_execute:
        # Mock anthropic response
        with patch('webapp.backend.ws_handler.client') as mock_client:
            mock_response = MagicMock()
            mock_response.stop_reason = "tool_use"

            # Create mock tool use block
            mock_tool_use = MagicMock()
            mock_tool_use.type = "tool_use"
            mock_tool_use.name = "add_notebook_cell"
            mock_tool_use.id = "t1"
            mock_tool_use.input = {"code": "print(42)"}

            mock_response.content = [mock_tool_use]

            # Mock second response after tool execution
            mock_response_2 = MagicMock()
            mock_response_2.stop_reason = "end_turn"
            mock_response_2.content = [MagicMock(type="text", text="Done")]

            mock_client.messages.create = AsyncMock(side_effect=[mock_response, mock_response_2])

            conversation_history = [{"role": "user", "content": "Calculate 42"}]
            await run_agent_loop(ws, conversation_history)

    # Verify execute_code was called
    mock_execute.assert_called_once_with("print(42)")

    # Verify notebook_cell artifact sent (current impl: send_json with dicts)
    calls = [call[0][0] for call in ws.send_json.call_args_list]
    notebook_artifacts = [c for c in calls
                          if isinstance(c, dict) and c.get("artifact_type") == "notebook_cell"]
    assert len(notebook_artifacts) >= 1, "notebook_cell artifact not sent"

    # Verify artifact contains code and output. notebook_cell now travels on
    # the agent_artifact channel (so the frontend ARTIFACT_HANDLERS picks it up,
    # like every other agent-driven UI effect) — not the legacy "artifact" type.
    artifact = notebook_artifacts[0]
    assert artifact["type"] == "agent_artifact"
    assert artifact["artifact_type"] == "notebook_cell"
    assert artifact["content"]["code"] == "print(42)"
    assert artifact["content"]["output"] == "Result: 42"
    assert artifact["content"]["status"] == "ok"


@pytest.mark.asyncio
async def test_agent_run_analysis_workflow():
    """Test agent using run_analysis tool (registry-based structure analysis)."""

    ws = AsyncMock()

    with patch('webapp.backend.ws_handler.client') as mock_client:
        mock_response = MagicMock()
        mock_response.stop_reason = "tool_use"

        # Current run_analysis contract: {type, region} → run_registered_analysis.
        mock_tool_use = MagicMock()
        mock_tool_use.type = "tool_use"
        mock_tool_use.name = "run_analysis"
        mock_tool_use.id = "t2"
        mock_tool_use.input = {"type": "compartment", "region": "chr21"}

        mock_response.content = [mock_tool_use]

        # Mock second response after tool execution
        mock_response_2 = MagicMock()
        mock_response_2.stop_reason = "end_turn"
        mock_response_2.content = [MagicMock(type="text", text="Analysis complete")]

        mock_client.messages.create = AsyncMock(side_effect=[mock_response, mock_response_2])

        fake_handle = {
            "type": "compartment", "chrom": "chr21", "record_count": 2,
            "records": [{"chrom": "chr21", "start": 0, "end": 1000, "value": 0.5}],
            "data_url": "/api/compartments/chr21?format=gosling",
            "chromosome_field": "chrom", "genomic_fields": ["start", "end"],
            "suggested_mark": "bar",
        }
        with patch('webapp.backend.strc_api.run_registered_analysis',
                   return_value=fake_handle) as mock_run:
            conversation_history = [{"role": "user", "content": "Analyze"}]
            await run_agent_loop(ws, conversation_history)

    # Verify the registry analysis was invoked
    mock_run.assert_called_once()

    # Verify analysis_result artifact emitted for the frontend
    calls = [call[0][0] for call in ws.send_json.call_args_list]
    analysis_artifacts = [c for c in calls
                          if isinstance(c, dict) and c.get("artifact_type") == "analysis_result"]
    assert len(analysis_artifacts) >= 1, "analysis_result artifact not sent"
    assert analysis_artifacts[0]["analysis_type"] == "compartment"
    assert analysis_artifacts[0]["chrom"] == "chr21"


@pytest.mark.asyncio
async def test_agent_error_handling():
    """Test agent handles execution errors gracefully."""

    ws = AsyncMock()

    with patch('webapp.backend.ws_handler.client') as mock_client:
        mock_response = MagicMock()
        mock_response.stop_reason = "tool_use"

        # Create mock tool use block
        mock_tool_use = MagicMock()
        mock_tool_use.type = "tool_use"
        mock_tool_use.name = "add_notebook_cell"
        mock_tool_use.id = "t3"
        mock_tool_use.input = {"code": "raise ValueError('test error')"}

        mock_response.content = [mock_tool_use]

        # Mock second response after tool execution
        mock_response_2 = MagicMock()
        mock_response_2.stop_reason = "end_turn"
        mock_response_2.content = [MagicMock(type="text", text="Error handled")]

        mock_client.messages.create = AsyncMock(side_effect=[mock_response, mock_response_2])

        with patch('webapp.backend.notebook_api.execute_code', return_value={
            "status": "error",
            "output": "",
            "error": "ValueError: test error"
        }):
            conversation_history = [{"role": "user", "content": "Test error"}]
            await run_agent_loop(ws, conversation_history)

    # Verify artifact contains error (current impl: send_json with dicts)
    calls = [call[0][0] for call in ws.send_json.call_args_list]
    notebook_artifacts = [c for c in calls
                          if isinstance(c, dict) and c.get("artifact_type") == "notebook_cell"]
    assert len(notebook_artifacts) >= 1

    artifact = notebook_artifacts[0]
    assert artifact["content"]["status"] == "error"
    assert artifact["content"]["error"] == "ValueError: test error"


@pytest.mark.asyncio
async def test_multiple_tool_calls_in_sequence():
    """Test agent can make multiple tool calls in a single workflow."""

    ws = AsyncMock()

    with patch('webapp.backend.ws_handler.client') as mock_client:
        # First response: two tool uses (both code-executing notebook cells, since
        # run_analysis is now registry-based and does not execute arbitrary code).
        mock_response_1 = MagicMock()
        mock_response_1.stop_reason = "tool_use"

        mock_tool_use_1 = MagicMock()
        mock_tool_use_1.type = "tool_use"
        mock_tool_use_1.name = "add_notebook_cell"
        mock_tool_use_1.id = "t1"
        mock_tool_use_1.input = {"code": "x = 1"}

        mock_tool_use_2 = MagicMock()
        mock_tool_use_2.type = "tool_use"
        mock_tool_use_2.name = "add_notebook_cell"
        mock_tool_use_2.id = "t2"
        mock_tool_use_2.input = {"code": "print(x)"}

        mock_response_1.content = [mock_tool_use_1, mock_tool_use_2]

        # Second response: end turn
        mock_response_2 = MagicMock()
        mock_response_2.stop_reason = "end_turn"
        mock_response_2.content = [MagicMock(type="text", text="Both executed")]

        mock_client.messages.create = AsyncMock(side_effect=[mock_response_1, mock_response_2])

        with patch('webapp.backend.notebook_api.execute_code', return_value={
            "status": "ok",
            "output": "1"
        }) as mock_execute:
            conversation_history = [{"role": "user", "content": "Run two commands"}]
            await run_agent_loop(ws, conversation_history)

    # Verify both executions happened
    assert mock_execute.call_count == 2

    # Verify both notebook_cell artifacts sent (current impl: send_json with dicts)
    calls = [call[0][0] for call in ws.send_json.call_args_list]
    notebook_artifacts = [c for c in calls
                          if isinstance(c, dict) and c.get("artifact_type") == "notebook_cell"]
    assert len(notebook_artifacts) == 2, "expected two notebook_cell artifacts"
