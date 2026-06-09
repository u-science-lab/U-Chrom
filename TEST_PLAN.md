# U-Chrom Webapp — Test Plan

## Overview

This document outlines the testing strategy for the U-Chrom webapp, derived from analysis of the existing codebase and current test coverage gaps.

---

## 1. Current Test Status

| Test File | Status | Notes |
|-----------|--------|-------|
| `tests/test_api.py` | ✅ Passing | REST endpoints, session lifecycle |
| `tests/test_ws.py` | ✅ Passing | WebSocket message handling |
| `tests/test_session.py` | ✅ Passing | Session/Viewport dataclass |
| `tests/test_export_api.py` | ✅ Passing | Export REST endpoint |
| `tests/test_integration.py` | ✅ Passing | Full stack integration (mock AI) |
| `tests/test_figure.py` | ⚠️ Needs scipy | Unit tests for figure generation |
| `tests/test_figure_e2e.py` | ⚠️ Needs scipy | End-to-end figure export |
| `tests/test_e2e_agent.py` | ⚠️ Needs real API key | Live agent E2E tests |

---

## 2. Architecture Under Test

```
Frontend (React/TypeScript)
        │  WebSocket + REST
        ▼
Backend (FastAPI)
  ├── REST: /api/sessions, /api/umap, /api/export, /api/figure
  ├── WebSocket: /ws/{session_id}
  │     └── ws_handler.py  ← agent logic lives here
  ├── session.py           ← Session, Viewport state
  └── agui_events.py       ← AG-UI event protocol

Agent pipeline:
  user message → _run_agent_agui()
    → Anthropic SDK (claude-opus-4, streaming)
    → tool calls: set_viewport, select_cells, highlight_region, run_python
    → _execute_tool() → emit AG-UI events back to WS
```

---

## 3. Test Layers

### 3.1 Unit Tests (fast, no external deps)

#### 3.1.1 `ws_handler.py` — Parser Functions

```python
# Target: _parse_actions(), _extract_code_blocks(), _extract_steps()
```

| Test | Input | Expected |
|------|-------|----------|
| parse single action | `<action type="set_viewport">{"chrom":"chr1","start":0,"end":1000}</action>` | `[{action_type: set_viewport, payload: {...}}]` |
| parse multiple actions | two action tags | list of 2 dicts |
| malformed JSON in action | `<action type="foo">not-json</action>` | returns `[]` (no crash) |
| extract python block | ` ```python\nprint("hi")\n``` ` | `['print("hi")\n']` |
| extract multi block | two code blocks | list of 2 strings |
| extract steps | `<step id="1" description="Load">```python\ncode\n```</step>` | `[{id:"1", description:"Load", code:"code\n"}]` |
| no steps in plain text | plain text only | `[]` |

#### 3.1.2 `session.py` — Data Classes

| Test | Scenario |
|------|----------|
| Viewport defaults | `Viewport()` → chrom/start/end are None |
| Session init | `Session()` → empty history, empty selection |
| Session with id | `Session(session_id="abc")` → id preserved |

#### 3.1.3 `agui_events.py` — Event Enum & Sender

| Test | Scenario |
|------|----------|
| AGUI enum values | All expected event names present |
| send_agui format | Mock WS receives `{"type": "...", "payload": {...}}` |

---

### 3.2 Integration Tests (mock Anthropic, real FastAPI)

#### 3.2.1 REST Endpoints (`test_api.py` — already covered)

- `POST /api/sessions` → returns session_id
- `GET /api/sessions/{id}` → 200 for valid, 404 for unknown
- `DELETE /api/sessions/{id}` → 204

**Gap: Add tests for:**
- `GET /api/umap` when chromdata has UMAP vs not
- `POST /api/export` with valid `session_id` and format

#### 3.2.2 Export Endpoint (`test_export_api.py` — already covered)

- `POST /api/export` happy path
- Missing `session_id` → 422
- Unknown format → handled

**Gap: Add tests for:**
- Concurrent export requests (race condition check)
- Export when session has no chromdata loaded

#### 3.2.3 WebSocket Message Dispatch (`test_ws.py` — already covered)

- `load_data` message → `data_loaded` response
- `update_viewport` → session state updated
- `select_cells` → session cell_selection updated
- Unknown message type → `error` response

**Gap: Add tests for:**
- `agent_message` → triggers `_run_agent_agui` (mock the function)
- `multimodal_query` → triggers `_run_agent_multimodal` (mock)
- `run_analysis` → returns `analysis_progress` queued

---

### 3.3 Agent Pipeline Tests (mock Anthropic SDK)

#### 3.3.1 AG-UI Event Sequence

Mock `anthropic.Anthropic` to emit controlled streaming events. Verify the WS receives AG-UI events in correct order.

**Test: Text-only response**
```
Stream: content_block_start(text) → content_block_delta(text_delta "Hello") → message_delta
Expected WS events:
  1. run_started
  2. text_message_start
  3. text_message_content {delta: "Hello"}
  4. text_message_end
  5. run_finished
```

**Test: Tool call — set_viewport**
```
Stream: content_block_start(tool_use, name=set_viewport) 
      → content_block_delta(input_json_delta '{"chrom":')
      → content_block_delta(input_json_delta '"chr1","start":0,"end":1000}')
      → content_block_stop
Expected WS events:
  1. run_started
  2. tool_call_start {tool_call_name: "set_viewport"}
  3. tool_call_args (delta chunks)
  4. tool_call_end
  5. agent_viewport_update {chrom: "chr1", ...}   ← legacy compat
  6. run_finished
```

**Test: Tool call — run_python**
```
Stream: tool_use(name=run_python, code="emit_artifact('text_block',{'content':'done'})")
Expected WS events:
  1. tool_call_start / end
  2. agent_artifact {artifact_type: "text_block", ...}
```

**Test: Error from Anthropic**
```
Stream: raises Exception("rate limit")
Expected: run_error event + error JSON on WS
```

#### 3.3.2 _execute_tool() Dispatch

Direct unit tests for each tool branch:

| Tool | Inputs | Expected side effects |
|------|--------|-----------------------|
| `set_viewport` | `{chrom: "chr15", start: 0, end: 1e6}` | `session.viewport` updated, WS gets `agent_viewport_update` |
| `select_cells` | `{ids: ["c1","c2"]}` | `session.cell_selection == ["c1","c2"]`, WS gets `agent_cell_selection` |
| `highlight_region` | `{regions: [...]}` | WS gets `agent_highlight_region` |
| `set_colormap` | `{scheme: "viridis"}` | WS gets `agent_set_colormap` |
| `run_python` | `{code: "emit_artifact('text_block', {'content':'hi'})"}` | WS gets `agent_artifact` |
| `run_python` with error | code that raises `ZeroDivisionError` | WS gets artifact with `format: "error"` |

---

### 3.4 Code Execution Sandbox Tests

#### Target: `_run_code_in_worker()`

| Test | Code | Expected artifacts |
|------|------|--------------------|
| Simple emit | `emit_artifact("text_block", {"content": "ok"})` | `[{artifact_type: "text_block", payload: {content: "ok"}}]` |
| Multiple emits | Two `emit_artifact` calls | List of 2 artifacts |
| Syntax error | `def bad(` | artifact with `format: "error"` |
| Runtime error | `1/0` | artifact with `format: "error"` containing `ZeroDivisionError` |
| numpy available | `import numpy as np; emit_artifact("data", {"v": np.array([1,2]).tolist()})` | data artifact with `v: [1, 2]` |
| No chromdata | path=None | runs without crash (cd not in sandbox) |

---

### 3.5 Figure Generation Tests (requires scipy)

These exist in `test_figure.py` and `test_figure_e2e.py`. Run separately:

```bash
pip install scipy
pytest tests/test_figure.py tests/test_figure_e2e.py -v
```

Key scenarios:
- `create_figure()` with nature/cell/science style
- Single vs double column layout
- PDF/PNG export produces non-empty bytes
- `to_base64()` returns valid base64 string
- `emit_artifact("figure", ...)` round-trip via WS

---

### 3.6 End-to-End Agent Tests (requires ANTHROPIC_API_KEY)

Located in `tests/test_e2e_agent.py`. Only run in CI with real key.

```bash
ANTHROPIC_API_KEY=sk-... pytest tests/test_e2e_agent.py -v -m e2e
```

Scenarios:
- User asks "show chr15" → agent emits `set_viewport` action
- User asks "run compartment analysis" → code block executed, artifact returned
- Multi-turn: follow-up question uses conversation history

---

## 4. Test Implementation Plan (Priority Order)

### Phase 1 — Fill Unit Test Gaps (no deps)

**File: `tests/test_ws_handler_unit.py`** (new)

```python
# Tests for _parse_actions, _extract_code_blocks, _extract_steps
# Tests for _execute_tool (mock WebSocket + Session)
# Tests for _run_code_in_worker (no chromdata)
```

### Phase 2 — Mock Agent Pipeline

**File: `tests/test_agent_pipeline.py`** (new)

```python
# Mock anthropic.Anthropic to return controlled stream events
# Verify AG-UI event sequence via mock WebSocket
# Cover all 4 tool call types
# Cover error path
```

### Phase 3 — REST Gap Coverage

**Extend `tests/test_api.py`:**
- Add `/api/umap` tests
- Add concurrent session creation test

**Extend `tests/test_export_api.py`:**
- Export with no chromdata loaded

### Phase 4 — scipy-gated Figure Tests

```bash
# In CI: install scipy before running
pip install scipy
pytest tests/test_figure.py tests/test_figure_e2e.py
```

### Phase 5 — E2E with real API key (CI only)

```bash
pytest tests/test_e2e_agent.py -m e2e
```

---

## 5. Test Infrastructure

### Fixtures (add to `conftest.py`)

```python
@pytest.fixture
def mock_ws():
    """AsyncMock WebSocket that records sent JSON."""
    ws = AsyncMock()
    ws.sent = []
    async def _send(data): ws.sent.append(data)
    ws.send_json.side_effect = _send
    return ws

@pytest.fixture
def session():
    return Session(session_id="test-session")

@pytest.fixture
def mock_anthropic_stream(mocker):
    """Patch anthropic.Anthropic to return a controlled event stream."""
    # Returns factory accepting a list of events to emit
    ...
```

### Markers (`pytest.ini` / `pyproject.toml`)

```ini
[tool.pytest.ini_options]
markers = [
    "e2e: requires ANTHROPIC_API_KEY",
    "slow: takes > 5s",
    "needs_scipy: requires scipy installation",
]
```

### CI Matrix

```yaml
# .github/workflows/test.yml
- name: Unit + Integration
  run: pytest tests/ --ignore=tests/test_figure.py --ignore=tests/test_figure_e2e.py --ignore=tests/test_e2e_agent.py

- name: Figure tests
  run: pip install scipy && pytest tests/test_figure.py tests/test_figure_e2e.py

- name: E2E (main branch only)
  if: github.ref == 'refs/heads/main'
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  run: pytest tests/test_e2e_agent.py -m e2e
```

---

## 6. Coverage Targets

| Module | Current | Target |
|--------|---------|--------|
| `ws_handler.py` | ~30% | 80% |
| `session.py` | ~90% | 95% |
| `agui_events.py` | ~60% | 90% |
| `main.py` (REST routes) | ~70% | 85% |
| `figure.py` | ~20% | 75% |

Run coverage:
```bash
pytest tests/ --ignore=tests/test_e2e_agent.py --cov=webapp --cov-report=html
```

---

## 7. Key Risk Areas

1. **Streaming event order** — AG-UI protocol requires strict ordering; easy to emit `run_finished` before `text_message_end`
2. **Tool call JSON assembly** — `partial_json` chunks must be concatenated correctly before `json.loads`
3. **Executor lifecycle** — `ProcessPoolExecutor` passed into WS handler; tests must mock or provide real executor
4. **Conversation history** — Multi-turn tests verify history is appended and sent correctly on next call
5. **Chromdata serialization** — Worker process receives path, not object; tests with real chromdata need temp file lifecycle

---

*Generated from codebase analysis of U-Chrom webapp v0.x*
