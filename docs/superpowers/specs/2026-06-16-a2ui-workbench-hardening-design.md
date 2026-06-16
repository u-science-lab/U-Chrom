# U-Chrom A2UI Workbench Hardening Design

**Date:** 2026-06-16
**Worktree:** `/Volumes/sandisk/Coding/U-Chrom/.claude/worktrees/webapp`
**Branch:** `feat/phase0-viewer-integration`
**Status:** Implemented and verified

---

## Goal

Harden the current U-Chrom webapp into a coherent AI-assisted chromatin analysis workbench: users load U-Chrom/ChromData results, ask an AI agent to analyze them, and receive linked visual outputs across genomic tracks, 3D structures, embeddings, notebooks, and custom component layouts.

The existing implementation is already substantially beyond the older 2026-06-10 design. It has a single FastAPI WebSocket, backend-authoritative view sessions, JSON Patch deltas, persisted conversation/view snapshots, user-interaction futures, screenshot capture, whitelisted component trees, built-in structure analyses, and sandboxed custom analyses. This design closes the remaining production gaps instead of rebuilding the system.

## Current Architecture

The app is a React/Vite frontend and a FastAPI backend. The main control plane is `/ws/main`; read-heavy visualization data comes from REST endpoints. The backend session owns the loaded `ChromData`, conversation history, and view-state snapshots.

Core backend files:
- `webapp/backend/main.py`: FastAPI app, `/ws/main`, upload/download, conversation endpoints, router registration.
- `webapp/backend/ws_handler.py`: WebSocket message dispatch, Anthropic streaming loop, interaction/snapshot futures.
- `webapp/backend/agent_tools.py`: tool schemas and system prompt.
- `webapp/backend/tool_executors.py`: tool execution registry, Gosling rendering/patching, analyses, component rendering, snapshots.
- `webapp/backend/session.py`: session and `ViewSession` state.
- `webapp/backend/data_api.py`, `strc_api.py`, `tileset_api.py`, `track_wig.py`, `dynamic_api.py`: REST data and analysis surfaces.

Core frontend files:
- `webapp/frontend/src/ws.ts`: persistent WebSocket client and session/conversation id ownership.
- `webapp/frontend/src/store.ts`: Zustand store for tabs, Gosling state, revisions, selection, notebook cells, and component trees.
- `webapp/frontend/src/artifactHandlers.ts`: `agent_artifact` dispatch.
- `webapp/frontend/src/components/GoslingRenderer.tsx`: Gosling render, viewport sync, diagnostics, export, snapshot capture.
- `webapp/frontend/src/components/Structure3DPanel.tsx`: Three.js structure view, per-cell/chrom filtering, 3D picking.
- `webapp/frontend/src/components/ComponentRenderer.tsx`: Tier-2 whitelisted component tree rendering.

## Implementation Completeness Assessment

Implemented and valuable:
- Agent can render and patch Gosling specs, with backend view state and client revision checks.
- UI can report user events (`ui_event`) and visual diagnostics back to the agent.
- Agent can wait for the next user interaction, including Gosling region selection and 3D bin picking.
- Agent can capture rendered genomic, embedding, or 3D views and inspect pixels.
- Built-in `run_analysis` exposes TAD, loop, and compartment outputs as Gosling-ready JSON endpoints.
- `write_analysis_function` deploys sandboxed custom Python analyses as live REST endpoints.
- Component-tree rendering is whitelisted and does not execute agent code.
- Conversation and view snapshots survive reconnects.

Completed in this hardening pass:
- A2UI now has a versioned `a2ui.protocol` handshake (`protocol_version: "0.2"`), capabilities, and backend tool list.
- REST endpoints resolve explicit `session_id` first and retain `data_api.current_session` only as a backward-compatible fallback.
- `run_analysis` stores session-scoped analysis annotations and exposes render metadata in both artifacts and tool results.
- `/api/bins/{cell_id}?annotations=true` projects compartment/TAD intervals and loop anchors onto bin metadata for 3D coloring/highlighting.
- Tier-2 component controls emit structured `component_action` `ui_event`s and validate safe `action_id`s.
- Browser guide documentation now states the current A2UI/Pantheon LiveView differences.

Remaining hardening opportunities:
- Generate TypeScript types from the Python protocol/artifact contract instead of relying on parallel tests and conventions.
- Broaden live E2E coverage for multi-session browser scenarios beyond focused backend/session tests.
- Add richer visual legends for projected 3D annotation fields.

## A2UI Protocol Target

U-Chrom should keep its protocol domain-specific and explicit:

- `a2ui.protocol`: server handshake with `protocol_version`, session id, capabilities, and backend tool list.
- `view.snapshot`: full state list, used on reconnect or delta mismatch.
- `agent_artifact`: typed artifact events for `gosling_spec`, `gosling_patch`, `analysis_result`, `embedding_computed`, `show_structure`, `color_structure`, `component_tree`, `notebook_cell`, `export_view`, and custom analyses.
- `ui_event`: user interactions from rendered views, optionally carrying `interaction_id`.
- `await_interaction` / `await_interaction_done`: exact wait lifecycle for agent-blocking interaction requests.
- `view.diagnostic`: frontend render/validation errors reported to backend view state.
- `request_snapshot` / `snapshot_result`: visual capture round trip.

Best-practice properties:
- Version and capability negotiation before optional features are used.
- Backend-authoritative view state with monotonic revisions.
- RFC 6902 JSON Patch for deltas.
- Full-state recovery when a delta base revision does not match.
- Tool result status frames for loading, success, and failure.
- Explicit artifact schemas, generated or checked from the same source on both sides.
- URL sanitization and no agent-provided executable JavaScript.
- Session-scoped REST data access.

## Pantheon LiveView Comparison

Pantheon is a general agent platform. It includes NATS remote backends, service discovery, stream channels, chatroom auto-start, and project-scoped skills/LiveView adapters. It is optimized for remote services and broad extensibility.

U-Chrom differs intentionally:
- U-Chrom is a domain workbench backed by `ChromData`, not a generic remote-agent UI runtime.
- U-Chrom should not add Pantheon NATS as a core dependency. The current single FastAPI + WS + REST architecture is simpler and fits a local scientific analysis app.
- U-Chrom should not accept arbitrary agent-authored JavaScript modules. It should keep the current whitelisted component-tree model and sandboxed Python-analysis model.
- U-Chrom should borrow Pantheon-style ideas where they help: explicit live-view lifecycle, adapter/capability discovery, status streaming, bounded state, and robust reconnect behavior.

## AI UI Collaboration Capabilities

After hardening, U-Chrom can support these collaborative workflows:

- Ask the agent to load/overview a dataset and produce a linked contact map, 3D structure, embedding, and notebook summary.
- Ask for TAD/loop/compartment detection and have the agent render overlays in Gosling.
- Pick a 3D bin and ask the agent to analyze or visualize the corresponding genomic region.
- Brush a genomic region and have 3D/embedding panels respond through shared store state.
- Ask for a custom analysis; the agent deploys a sandboxed endpoint, renders it, captures the view, and self-corrects if the image is blank or invalid.
- Ask for a custom comparison layout; the agent composes whitelisted panels, controls, tables, and existing views without executing frontend code.
- Export the current figure from chat.

## Design Scope

This phase will implement five bounded hardening slices:

1. Protocol contract and handshake.
2. REST session isolation.
3. Analysis-to-bin metadata linkage.
4. Tier-2 component-tree actions and accessibility.
5. Documentation and drift cleanup.

Out of scope:
- Multi-user realtime collaboration.
- Pantheon NATS integration.
- Arbitrary agent-authored frontend JavaScript.
- Account/auth infrastructure.
- A full redesign of visual styling.

## Testing Strategy

Use focused red-green tests for each slice:
- Backend protocol tests for version/capabilities and artifact schemas.
- Multi-session REST tests proving session A and session B data do not cross.
- Analysis projection tests that map compartment/TAD/loop records onto bin-level fields.
- Frontend store/renderer tests for protocol handshake, session-aware fetch URLs, component actions, and accessibility props.
- Existing backend/frontend suites as regression coverage.
