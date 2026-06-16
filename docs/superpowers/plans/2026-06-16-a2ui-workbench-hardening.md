# A2UI Workbench Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden U-Chrom webapp into a versioned, session-safe, analysis-aware AI UI workbench for ChromData/U-Chrom visualization and collaborative exploration.

**Architecture:** Keep the existing FastAPI + single WebSocket + REST topology. Add a small protocol-contract layer, make REST endpoints resolve data through explicit session ids with global fallback compatibility, project structure-analysis records onto bin metadata, and make Tier-2 component controls emit structured UI actions.

**Tech Stack:** FastAPI, Pydantic-compatible JSON contracts, React 18, Vite, Zustand, Gosling.js, Three.js, deck.gl, pytest, Vitest/TypeScript build.

**Working directory:** `/Volumes/sandisk/Coding/U-Chrom/.claude/worktrees/webapp`

---

## File Map

- Create `webapp/backend/a2ui_protocol.py` for protocol version, capabilities, artifact schemas, and hello payload.
- Modify `webapp/backend/main.py` to keep a global session registry available to REST dependencies and emit protocol hello on WS connect.
- Modify `webapp/backend/data_api.py` to resolve `ChromData` from request session id, and add bin annotations.
- Modify `webapp/backend/tileset_api.py`, `track_wig.py`, `strc_api.py`, and `dynamic_api.py` to use the same session resolver.
- Modify `webapp/backend/tool_executors.py` to enrich `analysis_result` artifacts and project analysis records onto session bin annotations.
- Modify `webapp/frontend/src/ws.ts` to expose session id, handle protocol hello, and provide session-aware REST URL helpers (`sessionApiUrl`).
- Modify `webapp/frontend/src/store.ts` and `artifactHandlers.ts` to store protocol capabilities and analysis metadata.
- Modify `webapp/frontend/src/components/EmbeddingPanel.tsx`, `GenomicPanel.tsx`, `Structure3DPanel.tsx`, and `TopBar.tsx` to use session-aware fetch URLs.
- Modify `webapp/frontend/src/components/ComponentRenderer.tsx` to support accessible component actions.
- Add or update tests in `tests/backend/test_a2ui_protocol.py`, `tests/test_data_api.py`, `tests/backend/test_tool_executors.py`, `webapp/frontend/src/ws.test.ts`, `webapp/frontend/src/store.test.ts`, and `webapp/frontend/src/components/ComponentRenderer.test.tsx`.
- Update `docs/source/guide/browser.md` and this phase's design/plan docs with current protocol and Pantheon differences.

## Task 1: Protocol Contract And Handshake

**Files:**
- Create: `webapp/backend/a2ui_protocol.py`
- Modify: `webapp/backend/ws_handler.py`
- Modify: `webapp/backend/main.py`
- Modify: `webapp/frontend/src/ws.ts`
- Modify: `webapp/frontend/src/store.ts`
- Test: `tests/backend/test_a2ui_protocol.py`
- Test: `webapp/frontend/src/ws.test.ts`

- [x] **Step 1: Write backend failing tests**

Add tests asserting `protocol_hello()` includes:
- `type == "a2ui.protocol"`
- `protocol_version == "0.2"`
- `capabilities` includes `json_patch`, `view_snapshot`, `interaction_wait`, `snapshot_capture`, `component_tree`, `component_actions`, `analysis_projection`, and `session_scoped_rest`
- all backend tool names are listed.

Run: `python -m pytest tests/backend/test_a2ui_protocol.py -q`
Expected: fail because `a2ui_protocol.py` does not exist.

- [x] **Step 2: Implement protocol module**

Create constants and `protocol_hello()` in `webapp/backend/a2ui_protocol.py`.

- [x] **Step 3: Wire hello**

In `ws_main`, send `protocol_hello()` after accept/session binding. Also support client command `protocol.hello` in `handle_message` so reconnect/tests can request it.

- [x] **Step 4: Add frontend protocol state**

In `store.ts`, add `protocol` state and `setProtocol`. In `ws.ts`, listen for `a2ui.protocol`, store session id/protocol metadata, and export `apiUrl(path)`.

- [x] **Step 5: Verify**

Run:
- `python -m pytest tests/backend/test_a2ui_protocol.py tests/backend/test_ws_handler.py -q`
- `cd webapp/frontend && npx vitest run src/ws.test.ts src/store.test.ts`

## Task 2: Session-Scoped REST

**Files:**
- Modify: `webapp/backend/main.py`
- Modify: `webapp/backend/data_api.py`
- Modify: `webapp/backend/tileset_api.py`
- Modify: `webapp/backend/track_wig.py`
- Modify: `webapp/backend/strc_api.py`
- Modify: `webapp/backend/dynamic_api.py`
- Modify: frontend fetch callers to use `ws.apiUrl(...)`
- Test: `tests/test_data_api.py`

- [x] **Step 1: Write backend failing test**

Add a test that registers two sessions with different `ChromData` objects, calls `/api/dataset_info?session_id=a` and `/api/dataset_info?session_id=b`, and asserts each response sees only its own chromosomes. Also assert existing global fallback still works for compatibility.

Run: `python -m pytest tests/test_data_api.py::test_dataset_info_is_session_scoped -q`
Expected: fail because `session_id` is ignored.

- [x] **Step 2: Implement resolver**

Expose `get_registered_session(session_id)` from `main.py` or register a lookup callback in `data_api.py`. Add `session_id` query handling to `_cd_or_404(request)` while preserving `current_session` fallback.

- [x] **Step 3: Update REST modules**

Update tileset, tracks, structural analysis, and custom analysis resolvers to accept `Request` and use the shared resolver. Keep existing endpoint URLs compatible; `session_id` is optional.

- [x] **Step 4: Update frontend fetches**

Use `sessionApiUrl('/api/...')` for fetches in data panels and file browser. This appends the client session id.

- [x] **Step 5: Verify**

Run:
- `python -m pytest tests/test_data_api.py tests/backend/test_compute_embedding.py -q`
- `cd webapp/frontend && npm run build`

## Task 3: Analysis Metadata Projection

**Files:**
- Modify: `webapp/backend/tool_executors.py`
- Modify: `webapp/backend/session.py`
- Modify: `webapp/backend/data_api.py`
- Modify: `webapp/frontend/src/store.ts`
- Modify: `webapp/frontend/src/artifactHandlers.ts`
- Modify: `webapp/frontend/src/components/Structure3DPanel.tsx`
- Test: `tests/backend/test_tool_executors.py`

- [x] **Step 1: Write failing executor test**

Mock `run_registered_analysis("compartment", "chr1")` to return two compartment intervals. Assert `analysis_result` includes `data_url`, `record_count`, `genomic_fields`, `suggested_mark`, and that `session.analysis_annotations["compartment:chr1"]` exists with the records.

Run: `python -m pytest tests/backend/test_tool_executors.py::test_run_analysis_emits_render_metadata_and_annotations -q`
Expected: fail because metadata/annotations are incomplete.

- [x] **Step 2: Add backend annotation state**

Add `analysis_annotations: dict` to `Session`. Add helpers to project records onto bin rows. Start with interval membership for compartments and TADs, and loop anchor counts for loops.

- [x] **Step 3: Extend `/api/bins/{cell_id}`**

Include optional `annotations=true` and append annotation fields per bin when available. Preserve default response shape.

- [x] **Step 4: Update frontend state and 3D data model**

Store analysis result metadata. Fetch bin annotations from `Structure3DPanel` and carry them in `BinInfo.annotations`. Minimal visual effect: if `structureColorBy` matches an annotation field, choose segment color from the first annotated bin in that segment.

- [x] **Step 5: Verify**

Run:
- `python -m pytest tests/backend/test_tool_executors.py tests/test_data_api.py -q`
- `cd webapp/frontend && npm run build`

## Task 4: Component Actions And Accessibility

**Files:**
- Modify: `webapp/backend/tool_executors.py`
- Modify: `webapp/frontend/src/components/ComponentRenderer.tsx`
- Test: `tests/backend/test_tool_executors.py`
- Test: `webapp/frontend/src/components/ComponentRenderer.test.tsx`

- [x] **Step 1: Write failing tests**

Backend: `render_component` accepts controls with `action_id` and rejects trees whose action ids are too long or contain unsafe characters.

Frontend: `Button`, `Slider`, and `Select` render `aria-label` / `aria_label`, and emit `ui_event` with `event_name: "component_action"` carrying `{action_id, component, value}`.

- [x] **Step 2: Implement backend validation**

Validate `action_id` shape in component props. Preserve whitelist-only rendering.

- [x] **Step 3: Implement frontend events**

Controls should call `ws.send('ui_event', ...)` on click/change. Text/Panel should respect `aria_label` where applicable.

- [x] **Step 4: Verify**

Run:
- `python -m pytest tests/backend/test_tool_executors.py -q`
- `cd webapp/frontend && npx vitest run src/components/ComponentRenderer.test.tsx`

## Task 5: Documentation And Drift Cleanup

**Files:**
- Modify: `docs/source/guide/browser.md`
- Modify: `docs/superpowers/specs/2026-06-16-a2ui-workbench-hardening-design.md`
- Modify: `docs/superpowers/plans/2026-06-16-a2ui-workbench-hardening.md`

- [x] **Step 1: Update browser guide**

Document current A2UI capabilities, protocol version, session-scoped REST, analysis projection, and Pantheon LiveView differences.

- [x] **Step 2: Remove stale references**

Update outdated claims such as old tool counts, older placeholder-only statuses, and endpoints that have since changed.

- [ ] **Step 3: Verify docs and final suite**

Run:
- `python -m pytest tests/backend tests/test_data_api.py -q`
- `cd webapp/frontend && npx vitest run`
- `cd webapp/frontend && npm run build`

## Self-Review Checklist

- Every change is TDD-backed with a failing test first.
- Protocol changes are backward-compatible for old clients.
- REST `session_id` is optional but used by the frontend.
- Analysis projection does not require mutating `ChromData.spots`.
- Component actions do not execute code and only emit structured events.
- Pantheon comparison remains architectural, not a dependency import plan.
