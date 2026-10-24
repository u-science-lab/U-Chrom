# Local-First Agent WebUI UX Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 U-Chrom 的 Atlas/Hosted → 本地 WebUI → 用户自己的 Claude/Codex 链路收敛为可安装、可观察、摘要优先的 local-first 默认体验，并保持页面 canonical state 与 agent readback 一致。

**Architecture:** 公网页面只生成安装/启动命令和本地 MCP 指令；本地 companion 通过 stdio MCP 连接本地 WebUI，页面 Agent 面板显示连接阶段和 pending plan。默认 prompt 只传 dataset、问题和摘要，完整 cell IDs 只有用户明确选择或通过本地导出文件获得；Worker/DO relay 只作为显式可选能力。

**Tech Stack:** Python 3.11+, FastAPI, existing SSE broker, React/TypeScript, Zustand, Vitest, pytest, Vite static bundle, real `sim_cell1.cdz` fixture.

**Spec:** `docs/superpowers/specs/2026-10-22-local-agent-webui-handoff-design.md`

## Global Constraints

- 默认 local continuation 不调用 Wrangler、Cloudflare Worker 或公网 handoff API。
- 默认 prompt 不包含完整 canonical cell ID 列表；用户明确勾选后才可包含，超过 1 MiB UTF-8 必须拒绝且不截断。
- `uchrom_attach_handoff` 只用于显式启用的 Worker token 或本地 handoff JSON 导入，不能作为默认步骤。
- 页面 mutation 必须绑定显式 `page_id` 与 `expected_revision`；只有本地 WebUI Agent 面板的用户操作可以 Apply/Reject。
- action 返回值和再次 snapshot 是页面实际状态；不得用 handoff 原始值代替 readback。
- 不新增任意 shell/Python 执行 MCP tool；分析继续由用户自己的 Python/Skills 完成。
- 修改前端后必须运行 `npm run build`，并更新提交的 `static/` bundle。
- 不安装 Docker、Playwright 或其他新依赖；使用现有仓库依赖和现有真实 fixture。

## Review Focus

- 摘要模式是否真的不把 cell IDs 放入 prompt；opt-in 模式是否明确隐私提示并保留 1 MiB 限制。
- Atlas、Hosted WebUI、MCP tool description 是否都把 attach handoff 标为可选，而不是默认步骤。
- companion/browser/page 未启动、已启动未连接、已连接未 pin、已 pin、待 Apply、已应用是否有稳定且可读的 stage。
- 状态失败时是否不会把“agent 请求”显示成“页面已生效”，以及是否继续遵守 page/revision 保护。
- 文档中的安装命令是否和实际开发包路径一致，并把未发布 PyPI/桌面安装器标为未验证。

---

### Task 1: 摘要优先的 Hosted continuation

**Files:**
- Modify: `packages/uchrom-browser/uchrom_browser/frontend/src/handoff.ts`
- Modify: `packages/uchrom-browser/uchrom_browser/frontend/src/components/HostedHandoff.tsx`
- Modify: `packages/uchrom-browser/uchrom_browser/frontend/src/handoff.test.ts`
- Modify: `packages/uchrom-browser/uchrom_browser/frontend/src/components/HostedHandoff.test.ts`
- Modify: `packages/uchrom-browser/uchrom_browser/frontend/src/index.css`

**Interfaces:**
- `buildHandoffState(view, workspace, options?: { includeCellIds?: boolean }): HandoffState`
- `buildLocalHandoff(datasetUrl, question, state): LocalHandoffResult` remains the size/privacy gate.
- UI exposes an unchecked “Include canonical cell IDs” control; default prompt contains only selection count/source.

- [ ] **Step 1: Write failing tests**
  - default `buildHandoffState` omits `selection.cells` but retains count/source metadata;
  - opt-in state includes canonical IDs;
  - default prompt explicitly says IDs are omitted and warns before opt-in;
  - state/prompt size limits still reject oversize input without truncation.

- [ ] **Step 2: Implement minimal state and UI changes**
  - Keep canonical state shape backward compatible for opt-in;
  - add a visible privacy explanation next to the checkbox;
  - preserve exact dataset URL, question, and existing UTF-8 checks.

- [ ] **Step 3: Run focused frontend tests and build**
  - `cd packages/uchrom-browser/uchrom_browser/frontend && npm test -- --run src/handoff.test.ts src/components/HostedHandoff.test.ts`
  - `npm run build`

- [ ] **Step 4: Commit**
  - `git add packages/uchrom-browser/uchrom_browser/frontend/src && git commit -m "feat(browser): make hosted continuation summary-first"`

### Task 2: Local setup and connection stage feedback

**Files:**
- Modify: `packages/uchrom-agent/uchrom_agent/mcp_stdio.py`
- Modify: `packages/uchrom-agent/tests/test_mcp_stdio.py`
- Modify: `packages/uchrom-browser/uchrom_browser/frontend/src/agent.ts`
- Modify: `packages/uchrom-browser/uchrom_browser/frontend/src/components/AgentPanel.tsx`
- Modify: `packages/uchrom-browser/uchrom_browser/frontend/src/components/AgentPanel.test.tsx` (create if no component test exists)
- Modify: `packages/uchrom-browser/uchrom_browser/frontend/src/index.css`

**Interfaces:**
- `uchrom_setup_status` keeps its existing response fields and adds `stage` with one of `not_running`, `browser_ready`, `page_connected`, `page_pinned`.
- `agentSetupStatus(): Promise<{ stage: string; ... }>` reads the local MCP/browser status endpoint through the existing API boundary.
- AgentPanel renders a stage label and next action; it never treats a pending plan as applied state.

- [ ] **Step 1: Write failing tests**
  - setup status reports `not_running` on health failure;
  - one connected page reports `page_connected`;
  - a pinned page reports `page_pinned`;
  - AgentPanel labels at least “Start local WebUI”, “Open local page”, “Pin page”, and “Ready for analysis” for the corresponding states.

- [ ] **Step 2: Implement stage derivation and panel feedback**
  - Derive stage only from local health/pages/pin evidence;
  - poll with the existing bounded interval and preserve current error handling;
  - keep mutation buttons disabled when page/revision is stale.

- [ ] **Step 3: Run focused Python/frontend tests and build**
  - `cd packages/uchrom-agent && ../../.venv/bin/pytest tests/test_mcp_stdio.py -q`
  - `cd packages/uchrom-browser/uchrom_browser/frontend && npm test -- --run src/agent.test.ts src/components/AgentPanel.test.tsx`
  - `npm run build`

- [ ] **Step 4: Commit**
  - `git add packages/uchrom-agent packages/uchrom-browser/uchrom_browser/frontend/src && git commit -m "feat(agent): expose local connection stages"`

### Task 3: Install/configuration copy and protocol wording

**Files:**
- Modify: `apps/atlas/site/index.html`
- Modify: `apps/atlas/site/app.js`
- Modify: `apps/atlas/site/style.css`
- Modify: `apps/atlas/tests/test_local_continue.py`
- Modify: `packages/uchrom-browser/uchrom_browser/frontend/src/components/HostedHandoff.tsx`
- Modify: `packages/uchrom-browser/uchrom_browser/frontend/src/handoff.ts`
- Modify: `packages/uchrom-agent/uchrom_agent/mcp_stdio.py`
- Modify: `docs/superpowers/specs/2026-10-22-local-agent-webui-handoff-design.md`

**Interfaces:**
- Atlas and Hosted copy surfaces show source-checkout install prerequisites, local browser command, and “paste after page opens” MCP instruction.
- Copy text names `uchrom_attach_handoff` as optional relay/import only; default instruction starts with setup status → canonical snapshot → analysis → propose/apply.
- No UI claims that PyPI, desktop installer, Claude/Codex auto-configuration, or full browser E2E are already available.

- [ ] **Step 1: Write failing static assertions**
  - install command includes `packages/chromdata`, `packages/uchrom-browser`, and `packages/uchrom-agent`;
  - prompt does not say “one-time handoff” or require a token;
  - prompt says to run the local command first and read canonical state;
  - `attach_handoff` tool description contains “optional”.

- [ ] **Step 2: Implement copy and wording changes**
  - preserve no-network/no-localhost-probe behavior;
  - keep Atlas catalog URL as the only dataset reference;
  - keep Worker relay code available but outside the default copy flow.

- [ ] **Step 3: Run Atlas/frontend/companion tests**
  - `PYTHONPATH=apps/atlas python -m pytest apps/atlas/tests/test_local_continue.py -q`
  - `cd packages/uchrom-browser/uchrom_browser/frontend && npm test -- --run src/handoff.test.ts src/components/HostedHandoff.test.ts`
  - `cd packages/uchrom-agent && ../../.venv/bin/pytest tests/test_mcp_stdio.py -q`

- [ ] **Step 4: Commit**
  - `git add apps/atlas packages/uchrom-browser/uchrom_browser/frontend/src packages/uchrom-agent/uchrom_agent/mcp_stdio.py docs/superpowers/specs/2026-10-22-local-agent-webui-handoff-design.md && git commit -m "docs(ui): align local-first setup instructions"`

### Task 4: Real-data verification, ledger, and branch review

**Files:**
- Modify: `.superpowers/sdd/2026-10-23-local-agent-webui-local-first/progress.md`
- Modify: `docs/superpowers/plans/2026-10-22-local-agent-webui-mvp-plan.md`
- Modify: `docs/superpowers/specs/2026-10-22-local-agent-webui-handoff-design.md` only for verified evidence and residual limits.

- [x] **Step 1: Run local real-data checks**
  - use `packages/uchrom-browser/tests/fixtures/sim_cell1/sim_cell1.cdz`;
  - run the existing real-data agent-loop/API/SSE tests;
  - record that rendered AgentPanel Apply and full Worker create→redeem→attach remain separate unverified boundaries unless actually exercised.

- [x] **Step 2: Run complete relevant matrix**
  - browser agent/control tests;
  - companion tests;
  - frontend Vitest/build;
  - Atlas local continuation tests;
  - Worker typecheck/tests only as regression checks, without making Worker the default path.

- [ ] **Step 3: Whole-branch review**
  - package the branch diff from the original branch base;
  - `git diff --check origin/main...HEAD` passed;
  - fresh reviewer dispatch and subagent fix/re-review were not run because the parent task explicitly prohibited subagent creation. Prior Task 1–3 scoped review/fix records are retained in the ledger.

- [x] **Step 4: Update evidence**
  - record passed commands, actual runtime evidence, unverified installer/E2E boundaries, and any parked minor findings;
  - do not claim PyPI/desktop distribution or full rendered browser verification without evidence.

#### Task 4 verification record (2026-10-24)

The real-data agent loop independently passed against `packages/uchrom-browser/tests/fixtures/sim_cell1/sim_cell1.cdz`. Browser agent API, browser control/SSE, companion, frontend focused and full Vitest, frontend build, Atlas local continuation/build checks, and Worker tests/typecheck all passed in the commands recorded in `.superpowers/sdd/2026-10-22-local-agent-webui-mvp-plan/task-4-report.md`. The Atlas build suite has one `cooler`-dependent skip, and the control suite retains an existing timeout-test teardown warning. A combined browser pytest invocation showed one SSE readiness/teardown flake; independent suite runs passed.

Rendered AgentPanel Apply DOM interaction and full Worker create→redeem→attach runtime E2E remain unverified. PyPI/desktop distribution, automatic Claude/Codex setup, private-data/network interruption behavior, and cross-platform installation remain unverified.

## Historical implementation baseline

The earlier MVP already delivered the local page/revision/approval API, canonical readback, local companion, Atlas/Hosted local command surfaces, Worker relay isolation, and security tests. This plan only changes the default UX and protocol wording around that baseline; it does not reopen those completed tasks unless a focused test exposes a regression.

