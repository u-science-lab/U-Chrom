# Whole-branch final fix wave report

Date: 2026-10-24
Base reviewed: `b9cd601` (`codex/local-agent-webui`)

## Fixed

1. **Privacy and data minimization**
   - `buildHandoffState` now applies one deterministic default redaction policy to focus, pane scopes, stats `compareGroups`, nested genome-row scopes, and genome-row ratio group references.
   - Summary mode retains semantic kind/count/source fields and omits cell/group identifiers everywhere.
   - The explicit `includeCellIds: true` path preserves those canonical identifiers for user opt-in.
   - Prompt wording now states the cell/group privacy boundary and requires comparing the hosted reference snapshot with local canonical state before proposing changes.
   - Tests cover focus, pane scopes, compare groups, nested genome rows, default redaction, and opt-in preservation.

2. **Explicit page binding and revision binding**
   - Companion MCP read and mutation tools require an explicit `page_id`; proposal tools also require a non-empty `expected_revision`.
   - The bridge now verifies that the selected page is connected and already pinned by the local AgentPanel. It no longer auto-attaches a sole connected page or silently fills a missing page/revision.
   - `uchrom_attach_handoff` remains an explicit optional relay/import path. Setup status now returns connected page details so the agent can inspect them.
   - Tests cover missing arguments, unpinned-page rejection, and the absence of implicit attach calls.

3. **Selected-page setup stage**
   - Added `setupStageForPage` and selected-page-aware setup status typing.
   - AgentPanel derives its stage and next action from the selected page, so a pinned page A no longer makes unpinned page B appear ready.
   - Reject is rendered only for pending plans.
   - Tests cover pinned A plus selected unpinned B => `page_connected` / `Pin page`.

4. **Partial mutation failure recovery**
   - Apply captures the existing UI snapshot before mutations, and on action/readback failure performs one best-effort restore under the existing mutation lease.
   - Rollback outcome is recorded in plan results, final canonical state is read back, and `after_state` is exposed for audit. Rollback failure preserves partial results and adds an explicit warning; the original mutation is never retried.
   - A focused test covers first action success, second action failure, rollback, final canonical state, and `after_state` reporting.

## Verification

- Frontend focused Vitest: 27 tests passed.
- Frontend full Vitest: 45 files / 361 tests passed after the final nested-row redaction tests.
- Frontend TypeScript/Vite build: passed, 332 modules transformed. The generated hash-based `static/` bundle was removed during final cleanup per the request to remove build/static artifacts; the pre-wave tracked bundle remains in place.
- Companion MCP focused suite: 16 passed.
- Companion lifecycle/config suites: 85 passed.
- Companion complete test directory: 101 passed.
- Browser agent suite: 27 passed in 103.90s.
- Browser control and real-data E2E suites: 13 passed; the existing timeout test emitted one teardown thread warning while the assertions passed.
- Source/test/report paths pass `git diff --check`. A full `origin/main...HEAD` check still reports trailing whitespace in pre-existing minified static assets and blank-at-EOF lines in historical plan/E2E files; those paths are outside this fix wave and the generated hash bundle was removed during cleanup.

## Deferred or unverified boundaries

- Worker create/redeem/attach runtime E2E remains unverified and remains optional.
- Rendered browser DOM interaction for AgentPanel Apply remains unverified; unit/API coverage verifies the selected-page and stale-plan contracts.
- PyPI/desktop distribution, automatic Claude/Codex setup, cross-platform installation, and private-data/network interruption behavior remain unverified.
- Session-proof refresh remains a parked minor review item; this fix wave did not broaden auth/session behavior.

## Cleanup commit

The cleanup commit after the implementation restores the pre-wave tracked static bundle and removes the hash-based build output and transient `uv.lock` files. The implementation fix is in `8473342`.

No additional ruling is required for the four Important findings. The existing local-first ruling remains: inspect pages, have the user pin the page in AgentPanel, read local canonical state, compare the hosted reference, then propose a revision-bound plan for WebUI approval.
