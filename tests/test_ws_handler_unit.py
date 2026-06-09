"""
Unit tests for ws_handler.py utility functions.
Tests _parse_actions, _extract_code_blocks, _extract_steps, _run_code_in_worker,
and _execute_tool without requiring a real Anthropic API connection or WebSocket.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import Mock, AsyncMock, patch
from webapp.backend.ws_handler import (
    _parse_actions,
    _extract_code_blocks,
    _extract_steps,
    _run_code_in_worker,
    _execute_tool,
)
from webapp.backend.session import Session, Viewport


# ── _parse_actions ──────────────────────────────────────────────────────────

class TestParseActions:
    def test_single_action(self):
        text = '<action type="set_viewport">{"chrom":"chr1","start":0,"end":1000}</action>'
        result = _parse_actions(text)
        assert result == [{"action_type": "set_viewport", "payload": {"chrom": "chr1", "start": 0, "end": 1000}}]

    def test_two_actions(self):
        text = (
            '<action type="set_viewport">{"chrom":"chr1","start":0,"end":1000}</action>\n'
            '<action type="select_cells">{"mode":"cell_type","ids":[],"label":"Purkinje"}</action>'
        )
        result = _parse_actions(text)
        assert len(result) == 2
        assert result[0]["action_type"] == "set_viewport"
        assert result[1]["action_type"] == "select_cells"

    def test_invalid_json_returns_empty(self):
        text = '<action type="foo">not-json</action>'
        result = _parse_actions(text)
        assert result == []

    def test_no_action_tags(self):
        text = "This is just plain text with no action tags."
        result = _parse_actions(text)
        assert result == []

    def test_mixed_valid_and_invalid(self):
        text = (
            '<action type="good">{"key":"val"}</action>\n'
            '<action type="bad">not-json</action>'
        )
        result = _parse_actions(text)
        assert len(result) == 1
        assert result[0]["action_type"] == "good"


# ── _extract_code_blocks ────────────────────────────────────────────────────

class TestExtractCodeBlocks:
    def test_single_block(self):
        text = '```python\nprint("hi")\n```'
        result = _extract_code_blocks(text)
        assert result == ['print("hi")\n']

    def test_two_blocks(self):
        text = '```python\ncode1\n```\nsome text\n```python\ncode2\n```'
        result = _extract_code_blocks(text)
        assert len(result) == 2
        assert result[0] == 'code1\n'
        assert result[1] == 'code2\n'

    def test_no_blocks(self):
        text = "No code blocks here."
        result = _extract_code_blocks(text)
        assert result == []

    def test_multiline_block(self):
        text = '```python\nimport numpy as np\nx = np.array([1, 2])\n```'
        result = _extract_code_blocks(text)
        assert len(result) == 1
        assert 'import numpy as np' in result[0]


# ── _extract_steps ──────────────────────────────────────────────────────────

class TestExtractSteps:
    def test_valid_step(self):
        text = '<step id="1" description="Load data">\n```python\ncode\n```\n</step>'
        result = _extract_steps(text)
        assert len(result) == 1
        assert result[0]["id"] == "1"
        assert result[0]["description"] == "Load data"
        assert result[0]["code"] == "code\n"

    def test_no_steps(self):
        text = "No step tags here."
        result = _extract_steps(text)
        assert result == []

    def test_multiple_steps(self):
        text = (
            '<step id="1" description="Step one">\n```python\ncode1\n```\n</step>\n'
            '<step id="2" description="Step two">\n```python\ncode2\n```\n</step>'
        )
        result = _extract_steps(text)
        assert len(result) == 2
        assert result[0]["id"] == "1"
        assert result[1]["id"] == "2"


# ── _run_code_in_worker ─────────────────────────────────────────────────────

class TestRunCodeInWorker:
    def test_simple_emit(self):
        code = 'emit_artifact("text_block", {"content": "ok"})'
        result = _run_code_in_worker(code, chromdata_path=None)
        assert len(result) == 1
        assert result[0]["artifact_type"] == "text_block"
        assert result[0]["payload"]["content"] == "ok"

    def test_multiple_emits(self):
        code = (
            'emit_artifact("text_block", {"content": "first"})\n'
            'emit_artifact("text_block", {"content": "second"})'
        )
        result = _run_code_in_worker(code, chromdata_path=None)
        assert len(result) == 2

    def test_syntax_error(self):
        code = "def bad("
        result = _run_code_in_worker(code, chromdata_path=None)
        assert len(result) == 1
        assert result[0].get("payload", {}).get("format") == "error" or \
               result[0].get("artifact_type") == "text_block"
        # Should contain some error indication
        payload = result[0].get("payload", {})
        assert payload.get("format") == "error" or "error" in str(payload).lower()

    def test_runtime_error_zero_division(self):
        code = "1/0"
        result = _run_code_in_worker(code, chromdata_path=None)
        assert len(result) == 1
        payload = result[0].get("payload", {})
        assert payload.get("format") == "error"
        assert "division by zero" in str(payload) or "ZeroDivisionError" in str(payload)

    def test_numpy_available(self):
        code = "import numpy as np; emit_artifact('data', {'v': np.array([1,2]).tolist()})"
        result = _run_code_in_worker(code, chromdata_path=None)
        assert len(result) == 1
        assert result[0]["artifact_type"] == "data"
        assert result[0]["payload"]["v"] == [1, 2]

    def test_chromdata_path_none_no_crash(self):
        code = 'emit_artifact("text_block", {"content": "no cd needed"})'
        # Should not raise even with chromdata_path=None
        result = _run_code_in_worker(code, chromdata_path=None)
        assert isinstance(result, list)

    def test_pandas_available(self):
        code = "import pandas as pd; df = pd.DataFrame({'a': [1, 2]}); emit_artifact('data', {'len': len(df)})"
        result = _run_code_in_worker(code, chromdata_path=None)
        assert len(result) == 1
        assert result[0]["payload"]["len"] == 2

    def test_isolation_between_runs(self):
        # First execution sets a variable
        code1 = "x = 42"
        result1 = _run_code_in_worker(code1, chromdata_path=None)

        # Second execution should not see x
        code2 = """
try:
    y = x
    emit_artifact("text_block", {"content": "x found"})
except NameError:
    emit_artifact("text_block", {"content": "x not found"})
"""
        result2 = _run_code_in_worker(code2, chromdata_path=None)
        assert len(result2) == 1
        assert "not found" in result2[0]["payload"]["content"]

    def test_unicode_content(self):
        code = 'emit_artifact("text_block", {"content": "你好世界 🧬"})'
        result = _run_code_in_worker(code, chromdata_path=None)
        assert len(result) == 1
        assert "你好世界" in result[0]["payload"]["content"]
        assert "🧬" in result[0]["payload"]["content"]


# ── _execute_tool ───────────────────────────────────────────────────────────

class TestExecuteTool:
    """Test _execute_tool function with mocked WebSocket and Session."""

    @pytest.mark.asyncio
    async def test_set_viewport(self):
        ws = AsyncMock()
        session = Session(session_id="test_session")
        session.viewport = Viewport(chrom=None, start=None, end=None)

        await _execute_tool(
            ws, session, "sess_1", "set_viewport", "tool_1",
            {"chrom": "chr15", "start": 1000000, "end": 2000000},
            executor=None
        )

        assert session.viewport.chrom == "chr15"
        assert session.viewport.start == 1000000
        assert session.viewport.end == 2000000
        ws.send_json.assert_called_once()
        call_args = ws.send_json.call_args[0][0]
        assert call_args["type"] == "agent_viewport_update"
        assert call_args["payload"]["chrom"] == "chr15"

    @pytest.mark.asyncio
    async def test_select_cells(self):
        ws = AsyncMock()
        session = Session(session_id="test_session")

        await _execute_tool(
            ws, session, "sess_1", "select_cells", "tool_2",
            {"ids": ["cell_001", "cell_002"], "mode": "cell_type"},
            executor=None
        )

        assert session.cell_selection == ["cell_001", "cell_002"]
        ws.send_json.assert_called_once()
        call_args = ws.send_json.call_args[0][0]
        assert call_args["type"] == "agent_cell_selection"

    @pytest.mark.asyncio
    async def test_highlight_region(self):
        ws = AsyncMock()
        session = Session(session_id="test_session")

        await _execute_tool(
            ws, session, "sess_1", "highlight_region", "tool_3",
            {"chrom": "chr15", "start": 30000000, "end": 35000000, "color": "#ff6b6b"},
            executor=None
        )

        ws.send_json.assert_called_once()
        call_args = ws.send_json.call_args[0][0]
        assert call_args["type"] == "agent_highlight_region"

    @pytest.mark.asyncio
    async def test_set_colormap(self):
        ws = AsyncMock()
        session = Session(session_id="test_session")

        await _execute_tool(
            ws, session, "sess_1", "set_colormap", "tool_4",
            {"scheme": "viridis", "property": "compartment"},
            executor=None
        )

        ws.send_json.assert_called_once()
        call_args = ws.send_json.call_args[0][0]
        assert call_args["type"] == "agent_set_colormap"

    @pytest.mark.asyncio
    async def test_run_python_no_executor(self):
        ws = AsyncMock()
        session = Session(session_id="test_session")

        # When executor is None, should not crash
        await _execute_tool(
            ws, session, "sess_1", "run_python", "tool_5",
            {"code": "print('hello')"},
            executor=None
        )

        # No messages sent when executor is None
        ws.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_python_with_executor(self):
        ws = AsyncMock()
        session = Session(session_id="test_session")
        session.chromdata = None

        mock_executor = Mock()

        with patch('asyncio.get_running_loop') as mock_get_loop:
            mock_loop = AsyncMock()
            mock_get_loop.return_value = mock_loop

            # Mock executor result
            mock_loop.run_in_executor.return_value = [
                {"artifact_type": "text_block", "payload": {"content": "Done", "format": "info"}}
            ]

            await _execute_tool(
                ws, session, "sess_1", "run_python", "tool_6",
                {"code": 'emit_artifact("text_block", {"content": "Done"})'},
                executor=mock_executor
            )

            # Should send artifact
            ws.send_json.assert_called_once()
            call_args = ws.send_json.call_args[0][0]
            assert call_args["type"] == "agent_artifact"
            assert call_args["payload"]["artifact_type"] == "text_block"

    @pytest.mark.asyncio
    async def test_run_python_execution_error(self):
        ws = AsyncMock()
        session = Session(session_id="test_session")
        session.chromdata = None

        mock_executor = Mock()

        with patch('asyncio.get_running_loop') as mock_get_loop:
            mock_loop = AsyncMock()
            mock_get_loop.return_value = mock_loop

            # Simulate execution error
            mock_loop.run_in_executor.side_effect = Exception("Worker crashed")

            await _execute_tool(
                ws, session, "sess_1", "run_python", "tool_7",
                {"code": "1/0"},
                executor=mock_executor
            )

            # Should send error message
            ws.send_json.assert_called_once()
            call_args = ws.send_json.call_args[0][0]
            assert "error" in str(call_args).lower()

    @pytest.mark.asyncio
    async def test_run_python_with_chromdata(self):
        ws = AsyncMock()
        session = Session(session_id="test_session")

        # Create mock chromdata
        mock_cd = Mock()
        mock_cd.write = Mock()
        session.chromdata = mock_cd

        mock_executor = Mock()

        with patch('asyncio.get_running_loop') as mock_get_loop, \
             patch('tempfile.NamedTemporaryFile') as mock_temp, \
             patch('os.unlink') as mock_unlink:

            mock_loop = AsyncMock()
            mock_get_loop.return_value = mock_loop

            # Mock temp file
            mock_file = Mock()
            mock_file.name = "/tmp/test.h5cd"
            mock_file.close = Mock()
            mock_temp.return_value = mock_file

            mock_loop.run_in_executor.return_value = [
                {"artifact_type": "text_block", "payload": {"content": "CD loaded"}}
            ]

            await _execute_tool(
                ws, session, "sess_1", "run_python", "tool_8",
                {"code": 'emit_artifact("text_block", {"content": "CD loaded"})'},
                executor=mock_executor
            )

            # Should write chromdata to temp file
            mock_cd.write.assert_called_once()
            # Should clean up temp file
            mock_unlink.assert_called_once()


# ── Edge cases and error handling ───────────────────────────────────────────

class TestEdgeCases:
    """Test edge cases and unusual inputs."""

    def test_parse_actions_nested_json(self):
        text = '<action type="complex">{"nested":{"key":"value"},"array":[1,2,3]}</action>'
        result = _parse_actions(text)
        assert len(result) == 1
        assert result[0]["payload"]["nested"]["key"] == "value"
        assert result[0]["payload"]["array"] == [1, 2, 3]

    def test_parse_actions_empty_payload(self):
        text = '<action type="empty">{}</action>'
        result = _parse_actions(text)
        assert len(result) == 1
        assert result[0]["payload"] == {}

    def test_extract_code_blocks_empty(self):
        text = '```python\n```'
        result = _extract_code_blocks(text)
        assert len(result) == 1
        assert result[0] == ''

    def test_extract_steps_no_code_block(self):
        text = '<step id="1" description="No code">Just text</step>'
        result = _extract_steps(text)
        assert len(result) == 0

    def test_extract_steps_multiple_code_blocks_takes_first(self):
        text = '''<step id="1" description="Multi">
```python
first_code
```
Some text
```python
second_code
```
</step>'''
        result = _extract_steps(text)
        assert len(result) == 1
        assert "first_code" in result[0]["code"]

    def test_run_code_empty_string(self):
        result = _run_code_in_worker("", chromdata_path=None)
        # Empty code should not crash
        assert isinstance(result, list)

    def test_run_code_only_comments(self):
        code = "# This is a comment\n# Another comment"
        result = _run_code_in_worker(code, chromdata_path=None)
        assert isinstance(result, list)

    def test_run_code_import_error(self):
        code = "import nonexistent_module"
        result = _run_code_in_worker(code, chromdata_path=None)
        assert len(result) == 1
        assert result[0]["payload"]["format"] == "error"

    def test_parse_actions_json_with_quotes(self):
        text = r'<action type="test">{"text":"He said \"hello\""}</action>'
        result = _parse_actions(text)
        assert len(result) == 1
        assert 'hello' in result[0]["payload"]["text"]

    def test_extract_code_blocks_with_backticks_inside(self):
        # Code block containing backticks
        text = '```python\ncode = "`inner`"\n```'
        result = _extract_code_blocks(text)
        assert len(result) == 1
        assert "`inner`" in result[0]
