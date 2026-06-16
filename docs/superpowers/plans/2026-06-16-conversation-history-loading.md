# Conversation History Loading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistent historical conversation loading to U-Chrom so users can list prior conversations, load one after backend restart, see chat/tool history, restore view snapshots, and continue asking questions when the original data is available.

**Architecture:** The backend owns conversation history in a lightweight SQLite store, while JSONL remains a debug trace. WebSocket events keep the live UI in sync and REST endpoints list/load history. The frontend keeps only the active conversation pointer in localStorage, hydrates chat bubbles/tool rows from `conversation.snapshot`, and asks the backend to restore view state via the existing `view.snapshot` path.

**Tech Stack:** FastAPI, WebSocket JSON events, Python stdlib `sqlite3`, pytest, React, TypeScript, Vite/Vitest, Zustand-style app store.

---

### File Structure

- Create `webapp/backend/conversation_store.py`: SQLite schema, message/event/view snapshot persistence, summary/list/load helpers.
- Modify `webapp/backend/session.py`: add a UI transcript list and view snapshot serialization helpers while preserving existing Claude `conversation_history`.
- Modify `webapp/backend/ws_handler.py`: persist user/assistant/tool events, support `conversation.request_snapshot`, `conversation.load`, `conversation.new`, and emit `conversation.updated`.
- Modify `webapp/backend/main.py`: initialize sessions from requested conversation ids and add REST history endpoints.
- Create `tests/backend/test_conversation_store.py`: store behavior tests.
- Create `tests/backend/test_conversation_ws.py`: message dispatcher snapshot/load tests using fake websockets.
- Modify `webapp/frontend/src/ws.ts`: expose session/conversation id switching and request helpers.
- Modify `webapp/frontend/src/components/ChatPanel.tsx`: add history dropdown, hydrate messages/tool rows, load/new conversation actions.
- Create `webapp/frontend/src/components/ChatPanel.test.tsx`: UI hydration and history loading tests.

### Task 1: Backend Store

**Files:**
- Create: `webapp/backend/conversation_store.py`
- Test: `tests/backend/test_conversation_store.py`

- [ ] **Step 1: Write failing store tests**

Create tests that prove:
- a new store creates a conversation,
- user/assistant messages round-trip in order,
- tool events round-trip under the assistant message,
- view snapshots round-trip,
- the list endpoint summary includes title, data file, and message count.

- [ ] **Step 2: Run tests and verify RED**

Run: `.venv/bin/python -m pytest tests/backend/test_conversation_store.py -q`
Expected: FAIL because `webapp.backend.conversation_store` does not exist.

- [ ] **Step 3: Implement `ConversationStore`**

Use stdlib `sqlite3`, schema versioning via `PRAGMA user_version`, and one DB path from `UCHROM_CONVERSATION_DB` or `Path.cwd()/logs/conversations/conversations.sqlite3`.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `.venv/bin/python -m pytest tests/backend/test_conversation_store.py -q`
Expected: all tests in the new file pass.

### Task 2: Backend WebSocket Integration

**Files:**
- Modify: `webapp/backend/session.py`
- Modify: `webapp/backend/ws_handler.py`
- Modify: `webapp/backend/main.py`
- Test: `tests/backend/test_conversation_ws.py`

- [ ] **Step 1: Write failing WS tests**

Create fake websocket tests that prove:
- `conversation.request_snapshot` sends UI transcript and view snapshot for current session,
- `conversation.load` replaces session transcript and Claude context,
- `user_message` persists a user message before calling the agent loop,
- `tool_call_start`/`tool_call_result` events can be reconstructed as tool rows.

- [ ] **Step 2: Run tests and verify RED**

Run: `.venv/bin/python -m pytest tests/backend/test_conversation_ws.py -q`
Expected: FAIL because the dispatcher does not support conversation snapshot/load.

- [ ] **Step 3: Implement WS commands**

Add backend commands:
- `conversation.request_snapshot`
- `conversation.load`
- `conversation.new`

Add send events:
- `conversation.snapshot`
- `conversation.list`
- `conversation.updated`

Persist user/assistant/tool events in existing `handle_message` and `run_agent_loop` paths.

- [ ] **Step 4: Run backend tests and verify GREEN**

Run: `.venv/bin/python -m pytest tests/backend/test_conversation_store.py tests/backend/test_conversation_ws.py -q`
Expected: all tests pass.

### Task 3: Frontend History UI

**Files:**
- Modify: `webapp/frontend/src/ws.ts`
- Modify: `webapp/frontend/src/components/ChatPanel.tsx`
- Test: `webapp/frontend/src/components/ChatPanel.test.tsx`

- [ ] **Step 1: Write failing frontend tests**

Create tests that prove:
- `conversation.snapshot` hydrates user/assistant/tool rows,
- selecting a history item sends `conversation.load`,
- creating a new conversation clears the UI and sends `conversation.new`.

- [ ] **Step 2: Run tests and verify RED**

Run: `cd webapp/frontend && npx vitest run src/components/ChatPanel.test.tsx`
Expected: FAIL because the UI has no history controls or snapshot handling.

- [ ] **Step 3: Implement frontend behavior**

Add a compact history select/menu in the chat header. Keep layout stable, avoid bottom nav/chrome restoration, and do not add marketing/instructional text. Store active conversation id in localStorage only.

- [ ] **Step 4: Run frontend tests and verify GREEN**

Run: `cd webapp/frontend && npx vitest run src/components/ChatPanel.test.tsx`
Expected: all tests in the new file pass.

### Task 4: Integration Verification

**Files:**
- May modify any touched test files if the test harness needs small helpers.

- [ ] **Step 1: Run focused backend tests**

Run: `.venv/bin/python -m pytest tests/backend/test_conversation_store.py tests/backend/test_conversation_ws.py tests/backend/test_conversation_log.py -q`
Expected: all selected backend tests pass.

- [ ] **Step 2: Run focused frontend tests**

Run: `cd webapp/frontend && npx vitest run src/components/ChatPanel.test.tsx src/App.test.ts src/components/TopBar.test.ts src/specs/*.test.ts`
Expected: all selected frontend tests pass.

- [ ] **Step 3: Build frontend**

Run: `cd webapp/frontend && npm run build`
Expected: Vite build exits 0. Existing chunk-size warning is acceptable.

- [ ] **Step 4: Manual runtime smoke**

Start/restart backend and frontend, open `http://127.0.0.1:3000/`, send one message, reload/restart backend, then use the history menu to load the prior conversation. Verify chat rows and view snapshot restore when present.

