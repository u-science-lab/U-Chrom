# Task 2 report — local setup and connection stage feedback

## Status
Implemented and committed as requested. Existing user modifications in `docs/superpowers/plans/2026-10-22-local-agent-webui-mvp-plan.md` and `docs/superpowers/specs/2026-10-22-local-agent-webui-handoff-design.md` were preserved and excluded from the commit.

## Changes

- `packages/uchrom-agent/uchrom_agent/mcp_stdio.py`
  - `uchrom_setup_status` now preserves existing fields and adds `stage`.
  - Derivation uses only local health and connected page pin evidence: `not_running`, `browser_ready`, `page_connected`, `page_pinned`.
- `packages/uchrom-agent/tests/test_mcp_stdio.py`
  - Added coverage for health failure, connected page, and pinned page stages.
- `packages/uchrom-browser/uchrom_browser/frontend/src/agent.ts`
  - Added `AgentSetupStage`, `AgentSetupStatus`, `agentSetupStatus()`, stage labels, and next-action labels.
  - Status reads `/api/health` and `/api/agent/pages` through the existing API boundary.
- `packages/uchrom-browser/uchrom_browser/frontend/src/components/AgentPanel.tsx`
  - Displays current stage and next action, including `Start local WebUI`, `Open local page`, `Pin page`, and `Ready for analysis`.
  - Existing page/revision stale guard and Apply/Reject flow remain intact; pending plans remain separate from canonical snapshot state.
- `packages/uchrom-browser/uchrom_browser/frontend/src/index.css`
  - Added compact stage/next-action styling.
- `packages/uchrom-browser/uchrom_browser/frontend/src/agent.test.ts`
  - Added setup stage/action and API boundary tests.

## Verification

- `PYTHONPATH=. uv run pytest tests/test_mcp_stdio.py -q` from `packages/uchrom-agent`: **13 passed**.
- `npm test -- --run src/agent.test.ts` from `packages/uchrom-browser/uchrom_browser/frontend`: **1 file, 6 tests passed**.
- `npm run build` from `packages/uchrom-browser/uchrom_browser/frontend`: **passed** (`tsc` and Vite production build).
- `git diff --check`: **passed**.

The brief's literal Python command using `../../.venv/bin/pytest` was unavailable in this worktree. The equivalent test was run with the repository's available `uv` runtime and `PYTHONPATH=.`.

## Unverified / concerns

- No browser UI E2E test was run; component tests are not configured with a DOM renderer in this frontend.
- Stage polling retains the existing five-second bounded interval.
- Build output was generated for verification and restored so no generated static assets are included.

## Fix round 1 — component-level coverage

Reviewer feedback addressed by adding `packages/uchrom-browser/uchrom_browser/frontend/src/components/AgentPanel.test.tsx`. Because the existing Vitest configuration intentionally uses the Node environment and no DOM renderer dependency is installed, the test exercises `agentPanelViewModel`, a pure view-model helper imported by and used in `AgentPanel`. Coverage includes all four setup stages and next-action labels, plus Apply availability for matching versus stale page/revision values.

Validation:

- `npm test -- --run src/agent.test.ts src/components/AgentPanel.test.tsx`: **2 files, 11 tests passed**.
- `npm run build`: **passed**.
- Generated static build assets were restored and excluded from the commit.
