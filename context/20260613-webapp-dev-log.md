# U-Chrom WebApp 开发决策记录

**分支**：`feat/phase0-viewer-integration`（worktree：`.claude/worktrees/webapp`，所有 webapp 开发仅在此）
**整理日期**：2026-06-13

> 本文是 2026-06-10 ~ 06-12 开发过程的**决策浓缩**，只保留不会随代码漂移的**定位与理由**。
> **当前架构、端口、工具表、组件树以 [`webapp/README.md`](../webapp/README.md) 为准**——本文不重复实现细节。
> 设计 spec / 实施 plan 见 `docs/superpowers/specs/` 与 `docs/superpowers/plans/`；
> 动态 codegen + Tier-2 生成式 UI 的设计研究见 `context/20260611-dynamic-codegen-gosling-integration/`。

---

## 1. 产品定位（不变）

U-Chrom WebApp 是**对话驱动**的染色质 3D 结构**分析工作台**：研究者加载自己的 `ChromData`，
通过与 AI Agent 对话来可视化、分析、探索数据。

**明确非目标**（避免范围蔓延）：
- ❌ 数据集发布 / 搜索 / 下载门户（cellxgene 类，属另一 worktree）
- ❌ 多用户协作 / 账号系统
- ❌ IGV / HiGlass 原生面板（统一用 Gosling 替代）
- ❌ Plotly 预生成静态图（用 Gosling + deck.gl + Three.js 实时渲染）

## 2. 核心理念：A2UI（Agent-to-UI）

Agent 不只回答，而是**直接驱动界面**：发声明式 `agent_artifact`，前端 `ARTIFACT_HANDLERS`
按 `artifact_type` 路由到 Zustand 切片。Gosling 的声明式 JSON spec 天然契合 LLM 结构化输出，
使"对话即可视化"可行（`render_gosling` 整体渲染、`patch_gosling` 增量改）。

## 3. 已确认的关键技术决策

| 决策点 | 结论 | 理由 |
|---|---|---|
| 可视化技术 | Gosling（基因组）+ deck.gl（UMAP）+ Three.js（3D） | 三者都实时、声明式/数据驱动；**删除 IGV / HiGlass 原生面板 / FigureComposer** |
| 布局 | 左 Chat + 右 TabContainer 四 Tab；**删除 MainCanvas 网格布局** | 工作台是单数据集深挖，不是多面板拼图 |
| Notebook | **混合模式**：Agent 生成 cell + 用户可编辑/手动添加 | 兼顾自动化与可控性 |
| 后端入口 | 单一 `main.py` + WS `/ws/main` + REST | 早期两套 ws_handler 并存导致 import 即崩，已统一 |
| Agent loop | **流式** `client.messages.stream(...)` + `TOOL_EXECUTORS` 分派，循环至 `MAX_TOOL_ITERATIONS=10` | loop 工具无关，加工具不碰 loop |
| 数据真实性 | 所有面板连 `session.chromdata`，**无 demo / 假数据** | 未加载文件则面板留空 |
| 视图状态 | **后端权威**：`session.views` 为真值，`get_view_state` / `query_user_interaction` / `ui_event` | 支持 agent↔用户回路与重连快照 |
| Notebook 隔离 | IPython 内核独立进程，seed `cd = ChromData.read(path)` | 改 cd 不污染 REST 面板 |
| Gosling 版本 | **gosling.js@1.0.7（从 2.0.0-alpha 降级，精确 pin）** | 2.0 alpha 渲染不稳；1.0.7 + ErrorBoundary 可 WebGL 正常渲染。剩余 4 条 React lifecycle 弃用 warning 来自 gosling 内部 HiGlass 老依赖，不 fork 无法消除（详见 `gosling-spec-reference.md`） |

## 4. 测试取向

Agent 工作流测试为**链路级**：每个测试驱动完整 `run_agent_loop`，只 mock Anthropic 边界
（共享桩 `tests/_agent_loop_harness.py` 伪造 `client.messages.stream(...)` async-CM）。
`tests/conftest.py` 把仓库根放上 `sys.path`。真实 API 路径 `tests/test_e2e_real_claude.py`
需 `ANTHROPIC_API_KEY`，手动/CI 跑，不入默认套件。

## 5. 操作性备注

- 全程在 worktree `feat/phase0-viewer-integration`，**不碰 git 历史**。
- 早期曾有 7 个 webapp commit 误提交到 `main`，已 reset main 到共同祖先移除；
  所有 webapp 开发安全保留在本 worktree 分支。
- 验证纪律按 CLAUDE.md：真实 `.h5cd` 数据端到端，不以"编译通过/测试通过"冒充验证。

## 6. 当前事实的权威来源

| 想知道什么 | 看哪里 |
|---|---|
| 架构 / 端口 / 13 工具表 / 组件树 / Setup | `webapp/README.md` |
| 产品 spec 与实施 plan | `docs/superpowers/specs/`、`docs/superpowers/plans/` |
| 动态 codegen + 生成式 UI 设计研究 | `context/20260611-dynamic-codegen-gosling-integration/` |
| Gosling 1.0.7 spec 用法参考 | `context/gosling-spec-reference.md` |
| 代码真值 | worktree 源码本身 |
