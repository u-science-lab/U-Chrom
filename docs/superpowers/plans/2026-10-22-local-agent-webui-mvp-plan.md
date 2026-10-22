# Local Agent WebUI MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在本地 U-Chrom WebUI 中实现一个可由用户自己的 Claude/Codex 驱动的 live-control MVP：agent 读取 canonical 页面状态、提出带 page/revision 的 UI 变更计划，用户在页面 Agent 面板批准后执行，页面回读实际结果。

**Architecture:** 保留现有 `actions.ts`、`ui_tools.json`、FastAPI `ActionBroker` 和 SSE 页面控制链路。新增本地 agent 控制层保存显式 page pin、canonical revision、pending plan 和 history；agent 只能读取状态和提出计划，页面用户点击 Apply/Reject 才能执行 mutation。Python `Workspace` 暴露 snapshot/plan/status 便于 Claude/Codex 通过现有本地终端与 Skills 使用。

**Tech Stack:** Python 3.11+, FastAPI/Pydantic, existing SSE broker, React/TypeScript, Zustand, Vitest, pytest, Vite static bundle, real `sim_cell1.cdz` fixture.

**Spec:** `docs/superpowers/specs/2026-10-22-local-agent-webui-handoff-design.md`

## Global Constraints

- 本轮只实现本地 live-control MVP；不把 `/api/control/*` 暴露公网。
- 页面 mutation 必须绑定显式 `page_id` 与 `expected_revision`；没有 pin 或 revision 过期时拒绝执行。
- 页面 action 继续复用 `actions.ts`；不得复制一套页面状态逻辑。
- 用户在本地 WebUI Agent 面板点击 Apply/Reject；agent 不提供绕过确认的 apply tool。
- action 输入是请求，返回值和再次 snapshot 才是页面实际 canonical state。
- 未知 cell ID、越界 locus、Stats scope 必须遵循现有 canonicalization，并在结果中报告 warnings。
- 本轮不新增任意 shell/Python 执行 MCP tool；分析继续由用户自己的本地 Python 和 Skills 完成。
- 修改前端后必须运行 `npm run build`，更新提交的 `static/` bundle。

## Review Focus

- 多标签页或 active page 变化：mutation 必须发到 pinned `page_id`，不能退回最近 active page；测试在 Task 1。
- 用户手动修改后旧 plan：`expected_revision` 不匹配必须返回 stale，不执行任何 action；测试在 Task 1。
- Apply 过程中某个 action 失败或超时：记录已完成 canonical results，不自动重试 mutation；测试在 Task 1。
- AgentPanel 显示的状态来源：pending intent 不能伪装成 page canonical state；测试在 Task 2。
- 真实 `.cdz` 页面：agent 读取和页面显示的 selection/locus/Stats scope/capture 必须一致；验证在 Task 3/4。

---

### Task 1: Local agent session, revision, and pending-plan API

**Files:**
- Create: `packages/uchrom-browser/uchrom_browser/agent.py`
- Modify: `packages/uchrom-browser/uchrom_browser/server.py`
- Modify: `packages/uchrom-browser/uchrom_browser/control.py` only if a small typed helper is required; do not change existing `/api/control/*` behavior.
- Test: `packages/uchrom-browser/tests/test_agent.py`

**Interfaces:**
- Consumes: existing `ActionBroker`, `/api/control/pages`, `/api/control/actions`, and frontend action result payloads.
- Produces: local `/api/agent/*` endpoints and typed state objects used by the Python client and AgentPanel.

- [ ] **Step 1: Write failing API tests**

Add tests using the existing `server`/`FakePage` pattern and FastAPI client:

- `test_agent_snapshot_requires_explicit_page_and_returns_revision`: attach `ptest`, seed a fake `describe_workspace` result, assert snapshot includes `page_id`, `state_revision`, dataset/views/locus and source `page_canonical`.
- `test_propose_plan_requires_page_pin_and_expected_revision`: propose a two-action plan and assert `pending`, `page_id`, `expected_revision`, and actions are returned; missing page or wrong revision returns 409.
- `test_apply_requires_user_approval_and_records_results`: assert a pending plan cannot apply before approval, approval then applies actions to the pinned FakePage, returns per-action results and increments revision.
- `test_reject_and_stale_plan_do_not_execute_actions`: reject leaves page untouched; after a manual revision bump an old plan returns `stale` and FakePage sees no mutation.
- `test_action_failure_does_not_retry`: fake second action failure; assert first result is retained, second is error, and action count is exactly one per requested action.

Run: `cd packages/uchrom-browser && ../../.venv/bin/pytest tests/test_agent.py -q`
Expected: FAIL because `/api/agent/*` and agent state manager do not exist.

- [ ] **Step 2: Implement `AgentState` and route models**

In `agent.py`, define an in-memory `AgentState` owned by the local FastAPI app:

- `attach(page_id) -> AgentSession` validates the page via `ActionBroker.pages()` and pins it.
- `snapshot(page_id) -> dict` calls the pinned page's `describe_workspace` through `broker.call(page_id=...)`, returns `state_revision` and `source: "page_canonical"`.
- `propose(page_id, expected_revision, actions) -> PendingPlan` validates each action against `ui_tools.json`, creates an opaque `plan_id`, and stores `pending`.
- `approve(plan_id) -> PendingPlan` is called only by the local AgentPanel endpoint; it marks approved but does not route to an unpinned page.
- `reject(plan_id) -> PendingPlan` marks rejected without calling the broker.
- `apply(plan_id) -> PlanResult` executes approved actions sequentially with explicit `page_id`, stores every result/error, calls `describe_workspace` after successful mutations, and increments revision only after a successful canonical readback. Never retry a mutation.
- `status(plan_id)` returns pending/approved/rejected/stale/applied/failed.

Use module-level typed Pydantic request/response models compatible with the project’s FastAPI version. Keep storage process-local and bounded to the running local server; no hosted persistence in this task.

- [ ] **Step 3: Mount routes without changing existing control endpoints**

In `server.py`, create `app.state.agent_state` next to `app.state.broker` and mount:

- `GET /api/agent/pages`
- `POST /api/agent/attach`
- `GET /api/agent/snapshot?page=<id>`
- `POST /api/agent/plans`
- `GET /api/agent/plans/{plan_id}`
- `POST /api/agent/plans/{plan_id}/approve`
- `POST /api/agent/plans/{plan_id}/reject`
- `POST /api/agent/plans/{plan_id}/apply`

All mutation routes require an explicitly pinned `page_id`; return 409 for missing page, stale revision, unapproved plan, or page disconnect; return 422 for invalid action input. Do not expose these routes when `hosted is not None` in this MVP.

- [ ] **Step 4: Run focused and existing control tests**

Run: `cd packages/uchrom-browser && ../../.venv/bin/pytest tests/test_agent.py tests/test_control.py tests/test_server.py -q`
Expected: all selected tests pass with no existing control regression.

- [ ] **Step 5: Commit**

```bash
git add packages/uchrom-browser/uchrom_browser/agent.py packages/uchrom-browser/uchrom_browser/server.py packages/uchrom-browser/tests/test_agent.py
git commit -m "feat(browser): add local agent plan control API"
```

### Task 2: Python client and WebUI Agent panel

**Files:**
- Modify: `packages/uchrom-browser/uchrom_browser/client.py`
- Create: `packages/uchrom-browser/uchrom_browser/frontend/src/agent.ts`
- Create: `packages/uchrom-browser/uchrom_browser/frontend/src/agent.test.ts`
- Create: `packages/uchrom-browser/uchrom_browser/frontend/src/components/AgentPanel.tsx`
- Modify: `packages/uchrom-browser/uchrom_browser/frontend/src/components/Inspector.tsx`
- Modify: `packages/uchrom-browser/uchrom_browser/frontend/src/index.css`

**Interfaces:**
- Consumes: Task 1 `/api/agent/*` contracts and existing `Workspace.call()/describe()`.
- Produces: `Workspace.agent_snapshot()`, `Workspace.propose_ui_changes()`, `Workspace.plan_status()`, and a visible AgentPanel with Apply/Reject.

- [ ] **Step 1: Write failing client and pure-state tests**

Python tests extend `tests/test_control.py` or a new `tests/test_agent_client.py`:

- `test_workspace_agent_snapshot_and_propose`: assert request bodies include explicit page and expected revision.
- `test_workspace_does_not_apply_without_page`: assert client raises `BrowserError` when no pinned page is supplied.

Frontend `agent.test.ts` tests pure helpers:

- snapshot source labels distinguish `page_canonical`, `handoff_imported`, and `analysis_result`;
- pending plan renders requested actions without overwriting canonical snapshot;
- stale/rejected/applied statuses map to stable labels.

Run the focused tests first and expect FAIL for new methods/helpers.

- [ ] **Step 2: Implement Python `Workspace` helpers**

Add:

- `agent_pages()`
- `agent_snapshot(page=None)`
- `propose_ui_changes(actions, page, expected_revision)`
- `plan_status(plan_id)`
- `approve_plan(plan_id)`, `reject_plan(plan_id)`, `apply_plan(plan_id)` only as explicit local-control helpers; the agent Skill should use propose/status, while UI approval remains the normal path.

Keep URL/error handling in `_request`; preserve existing `connect()` behavior.

- [ ] **Step 3: Implement pure frontend agent helpers**

`agent.ts` owns API response types, status labels, and display formatting. It must not duplicate `actions.ts` or mutate Zustand directly. Expose functions for loading snapshot, loading plan status, approving/rejecting plans, and formatting canonical state/warnings.

- [ ] **Step 4: Implement and mount `AgentPanel`**

Add a collapsible Agent section in `Inspector.tsx` that:

- displays connected page ID, dataset, canonical selection count, locus, Stats scope, layout/views and revision;
- clearly labels `page canonical`, `handoff imported`, or `analysis result`;
- polls or refreshes snapshot/status after focus and after Apply/Reject;
- shows pending plan actions and user-facing Apply/Reject buttons;
- disables Apply when revision/page is stale;
- never displays a pending requested state as if it were applied.

Use existing inspector styles and keep the panel usable when no agent is connected.

- [ ] **Step 5: Run frontend tests and build**

Run: `cd packages/uchrom-browser/uchrom_browser/frontend && npm install && npm test -- --run src/agent.test.ts src/actions.test.ts src/actions.state.test.ts && npm run build`
Expected: focused tests pass and the build updates `packages/uchrom-browser/uchrom_browser/static/`.

- [ ] **Step 6: Commit**

```bash
git add packages/uchrom-browser/uchrom_browser/client.py packages/uchrom-browser/uchrom_browser/frontend/src/agent.ts packages/uchrom-browser/uchrom_browser/frontend/src/agent.test.ts packages/uchrom-browser/uchrom_browser/frontend/src/components/AgentPanel.tsx packages/uchrom-browser/uchrom_browser/frontend/src/components/Inspector.tsx packages/uchrom-browser/uchrom_browser/frontend/src/index.css packages/uchrom-browser/uchrom_browser/static
git commit -m "feat(browser): add local agent panel and client helpers"
```

### Task 3: Local real-data end-to-end validation and regression tests

**Files:**
- Create: `packages/uchrom-browser/tests/test_agent_e2e.py`
- Modify: `packages/uchrom-browser/uchrom_browser/API.md`
- Modify: `skills/show-in-browser/SKILL.md`
- Modify: `packages/uchrom-browser/README.md`

**Interfaces:**
- Consumes: Task 1 API, Task 2 client/panel, existing `sim_cell1.cdz`, and existing `show-in-browser` workflow.
- Produces: a repeatable local verification command and documentation of the live agent loop.

- [ ] **Step 1: Write the real-data test harness**

Use `tests/fixtures/sim_cell1/sim_cell1.cdz` and the existing uvicorn/FakePage pattern to assert:

- `describe_workspace` and `get_selection` return the same cells the page handler exposes;
- `set_locus` returns the canonical locus used by Stats;
- a plan that opens Stats with `chrom_scope=locus` and a Genome view is applied only after approval;
- the final snapshot revision and pane list match the page’s action results;
- a capture action is read-only and does not create a mutation plan.

Run: `cd packages/uchrom-browser && ../../.venv/bin/pytest tests/test_agent_e2e.py -q`
Expected: FAIL until the documented local loop and test adapter are wired.

- [ ] **Step 2: Implement the test adapter and documentation**

Keep the test deterministic and local: no Chrome automation, no network dependency, and no hosted Worker. Document the exact commands for:

```bash
uv pip install -e packages/chromdata -e packages/uchrom-browser -e "packages/uchrom[web]"
python -m uchrom_browser packages/uchrom-browser/tests/fixtures/sim_cell1/sim_cell1.cdz
```

Document that Claude/Codex run the Python client/Skills locally, while the WebUI remains the visualization and approval surface.

- [ ] **Step 3: Run the complete browser package suite**

Run: `cd packages/uchrom-browser && ../../.venv/bin/pytest tests -q`
Expected: all browser tests pass; report any pre-existing skips separately.

- [ ] **Step 4: Commit**

```bash
git add packages/uchrom-browser/tests/test_agent_e2e.py packages/uchrom-browser/uchrom_browser/API.md skills/show-in-browser/SKILL.md packages/uchrom-browser/README.md
git commit -m "test(browser): verify local agent loop on real data"
```

### Task 4: Whole-branch verification and deferred hosted handoff design note

**Files:**
- Create: `docs/superpowers/plans/2026-10-22-local-agent-webui-mvp-verification.md` only if a separate verification record is useful; otherwise use the SDD ledger.
- Modify: `docs/superpowers/specs/2026-10-22-local-agent-webui-handoff-design.md` only if implementation findings change the scope; do not rewrite the design silently.

**Interfaces:**
- Consumes: Tasks 1–3 commits, tests, build output, and the design spec.
- Produces: whole-branch review package, local verification evidence, and explicit deferred items for hosted handoff/companion/relay.

- [ ] **Step 1: Run the full verification matrix**

Run:

```bash
cd packages/uchrom-browser && ../../.venv/bin/pytest tests -q
cd uchrom_browser/frontend && npm test -- --run && npm run build
```

Expected: Python suite and frontend suite pass; static bundle is current.

- [ ] **Step 2: Perform real local smoke test**

Start the local browser with the real `sim_cell1.cdz`, use `Workspace` to read the page, propose a locus/Stats/Genome plan, approve it in the local AgentPanel, then read snapshot and capture. Save command/output paths in the SDD ledger; do not claim hosted handoff support.

- [ ] **Step 3: Review deferred scope**

Record that hosted Worker handoff, one-time token storage, stdio companion installation, Claude/Codex client registration, and hosted relay remain unimplemented follow-up work because this MVP does not add a cross-origin trust boundary or package distribution channel.

- [ ] **Step 4: Commit only documentation changes if needed**

```bash
git add docs/superpowers
 git commit -m "docs: record local agent MVP verification boundary"
```

### Task 5: Local companion and stdio MCP bridge

**Files:**
- Create: `packages/uchrom-agent/pyproject.toml`
- Create: `packages/uchrom-agent/uchrom_agent/__init__.py`
- Create: `packages/uchrom-agent/uchrom_agent/__main__.py`
- Create: `packages/uchrom-agent/uchrom_agent/mcp_stdio.py`
- Create: `packages/uchrom-agent/uchrom_agent/lifecycle.py`
- Create: `packages/uchrom-agent/uchrom_agent/client_config.py`
- Create: `packages/uchrom-agent/tests/test_mcp_stdio.py`
- Create: `packages/uchrom-agent/tests/test_client_config.py`
- Modify: `packages/uchrom-browser/uchrom_browser/client.py` only when a bridge helper is needed.

**Interfaces:**
- Consumes: local `/api/agent/*`, `uchrom_browser.connect()`, `ui_tools.json`, and the handoff payload model from Task 6.
- Produces: an installable development package with `uchrom-agent` CLI and an MCP stdio server usable by Claude Code/Codex.

- [ ] **Step 1: Write protocol tests first**

Feed newline-delimited JSON-RPC messages to the stdio handler and assert:

- `initialize` returns protocol/capabilities;
- `tools/list` exposes only the fixed U-Chrom tools from the spec;
- `tools/call` for `uchrom_setup_status`, `uchrom_workspace_snapshot`, and `uchrom_propose_ui_changes` returns structured text/content;
- unknown tools and malformed calls return JSON-RPC errors without writing logs to stdout.

Run: `PYTHONPATH=packages/uchrom-agent:packages/uchrom-browser:packages/chromdata ../../.venv/bin/pytest packages/uchrom-agent/tests/test_mcp_stdio.py -q`
Expected: FAIL before the package exists.

- [ ] **Step 2: Implement the fixed stdio MCP server**

Implement the minimal MCP stdio JSON-RPC loop without arbitrary shell/Python execution. The bridge owns a `Workspace` connection and delegates page reads/proposals to `/api/agent/*`; Apply remains a WebUI approval operation. `uchrom_attach_handoff` accepts a local handoff JSON path or token payload and starts/reuses `uchrom-browser` only after the user's local agent client authorizes the command.

- [ ] **Step 3: Implement client-config preview and explicit write**

Support Claude Code and Codex adapters that first print a diff, require an explicit `--write` flag, make a timestamped backup, atomically merge the U-Chrom server entry, and read back the written JSON. Do not hard-code undocumented paths; use explicit `--config PATH` in MVP and document how users locate their config.

- [ ] **Step 4: Run protocol/config tests and commit**

Run: `PYTHONPATH=packages/uchrom-agent:packages/uchrom-browser:packages/chromdata ../../.venv/bin/pytest packages/uchrom-agent/tests -q`

Commit: `feat(agent): add local stdio MCP bridge`.

### Task 6: Hosted handoff token service

**Files:**
- Modify: `apps/hosted-browser/src/index.ts`
- Modify: `apps/hosted-browser/wrangler.jsonc`
- Modify: `apps/hosted-browser/package.json` and lockfile only for the chosen test/runtime tooling.
- Create: `apps/hosted-browser/src/handoff.ts`
- Create: `apps/hosted-browser/src/handoff.test.ts`

**Interfaces:**
- Consumes: Atlas catalog dataset IDs and hosted WebUI semantic snapshots.
- Produces: exact-origin, single-use, ten-minute handoff creation/redeem endpoints backed by a dedicated Durable Object; it must not route through the hosted Python container.

- [ ] **Step 1: Write pure handoff tests**

Cover exact origin allowlist, dataset ID/catalog validation, payload size limit, token non-disclosure in logs/URLs, TTL expiry, atomic single redemption, and replay rejection.

- [ ] **Step 2: Implement `UChromHandoff` Durable Object and Worker routing**

Route `/api/agent/handoffs` before container dispatch. Use a high-entropy bearer token in a JSON body for redeem; never put it in a URL. Atlas may create dataset-only payloads; hosted WebUI may include a bounded semantic snapshot. Hosted browser continues to omit `/api/agent/*` and `/api/control/*` from its container.

- [ ] **Step 3: Add TypeScript/build verification**

Add a Worker test script or an explicit `npx tsc --noEmit`/pure-function test command, run it, and commit `feat(hosted): add one-time local-agent handoff`.

### Task 7: Atlas and hosted handoff UI

**Files:**
- Modify: `apps/atlas/site/app.js`
- Modify: `apps/atlas/site/index.html` and `apps/atlas/site/style.css`
- Modify: `apps/atlas/build.py` only to pass the configured handoff endpoint/origin.
- Modify: hosted WebUI frontend handoff module/component as needed; do not enable hosted control SSE.
- Test: `apps/atlas/tests/test_build.py` and frontend handoff pure tests.

**Interfaces:**
- Consumes: Task 6 handoff creation endpoint and current catalog metadata.
- Produces: Atlas card `Continue locally` dialog and hosted WebUI state-confirmation dialog that copy a one-time token, show the privacy notice, and never probe localhost or run a command.

- [ ] **Step 1: Write static/build tests**

Assert the generated card includes `Open in browser`, `Continue locally`, and download; handoff copy includes dataset ID/question and no local path, credential, or navigable token URL.

- [ ] **Step 2: Implement Atlas dialog and hosted state summary**

Use the existing no-framework Atlas patterns. Keep the primary action clear, show dataset/version and the exact state that will be transferred, and tell users to paste the one-line instruction into an already configured Claude/Codex MCP client.

- [ ] **Step 3: Build and run Atlas tests; commit**

Run the existing Atlas tests plus the new handoff assertions, then commit `feat(atlas): add continue locally handoff entry`.

### Task 8: Full local-to-hosted verification and final review

**Files:**
- Modify: SDD ledger and documentation only for actual evidence and deferred limitations.

- [ ] **Step 1: Run local real-data E2E**

Use `sim_cell1.cdz` to start localhost WebUI, connect the stdio MCP bridge, read canonical snapshot, propose locus/Stats/Genome changes, approve in AgentPanel, and capture the applied state.

- [ ] **Step 2: Run hosted handoff E2E in a local Worker harness**

Create a dataset-only token from an Atlas-origin request, redeem it once through the companion handler, verify replay/expiry/origin rejection, and confirm no hosted `/api/control/*` or `/api/agent/*` route is reachable in the container.

- [ ] **Step 3: Run complete test/build matrix and whole-branch review**

Run browser pytest, companion pytest, frontend Vitest/build, Atlas tests, and Worker TypeScript/tests. Build the review package, dispatch a fresh whole-branch reviewer, address Critical/Important findings with RED→GREEN tests, then record deferred minors and unresolved environment limitations.

