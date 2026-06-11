# U-Chrom WebApp 设计：对话驱动的染色质分析工作台

**日期**：2026-06-10
**分支**：`feat/phase0-viewer-integration`（worktree：`.claude/worktrees/webapp`）
**状态**：设计定稿，待实施
**产品定位**：本分支**只做分析工作台**。数据门户（cellxgene 类）归另一个 worktree，本分支不涉及。

---

## 1. 概述

U-Chrom WebApp 是一个**对话驱动**的染色质 3D 结构**分析工作台**。研究者加载自己的
ChromData（`.h5cd`），通过与 AI Agent 对话来可视化、分析、探索数据。

核心差异化 = **A2UI（Agent-to-UI）**：Agent 不只是回答问题，而是直接驱动界面。
用户说"显示 chr21 的 ATAC 信号和接触矩阵"，Agent 调用工具生成 **Gosling.js JSON spec**，
前端直接渲染；用户继续说"换成 bar 图"，Agent 发增量 patch 局部更新。Gosling 的声明式
JSON spec 天然契合 LLM 的结构化输出能力，使"对话即可视化"成为现实。

**目标用户**：分析自己染色质结构数据（FISH / 染色质追踪 / Hi-C 重建）的研究者。

**非目标**：数据集发布/搜索/下载门户、多用户协作、账号系统、IGV/HiGlass 原生面板、
Plotly 预生成静态图。

---

## 2. 已确认的设计决策

| 决策点 | 结论 |
|---|---|
| 产品定位 | 只做分析工作台；数据门户归另一 worktree |
| 可视化技术 | 统一 Gosling（基因组）+ deck.gl（UMAP）+ Three.js（3D）；**删除 IGV/HiGlass/FigureComposer** |
| 整体布局 | 左 Chat + 右 4 Tab + TopBar + GenomicNavBar |
| 加载初始态 | 加载后 Agent **自动生成默认可视化**填充各 Tab |
| Agent 控制范围 | **控制所有 Tab**（完整工具集）；实现优先级：先 Gosling，其余占位 |
| 接触矩阵 | HiGlass tileset + `data.type:"matrix"` + `mark:"bar"`；先做最小验证 |
| Notebook 后端 | **jupyter_client + IPython 内核**；混合模式（Agent 生成 cell + 用户可编辑执行） |
| 跨 Tab 联动 | **全面联动**（Genomic ↔ 3D ↔ Embedding） |
| 实现顺序 | **自底向上**：先修后端启动 → 真实端点 → Gosling → Notebook → 其余 |
| git | 全程 worktree，不碰 git 历史（误提交到 main 的 commit 由用户处理） |

---

## 3. 整体架构

单页 React 应用 ↔ 单一 FastAPI 后端，通过一个 WebSocket（`/ws/main`）+ 若干 REST 端点通信。
所有可视化基于一份内存中的 `ChromData`（REST 读）和一个按需起的 IPython 内核（Notebook 用）。

### 后端结构（单一入口 `main.py`）
```
webapp/backend/
├── main.py          唯一 FastAPI 入口：router 注册 + /ws/main + upload/download
├── ws_handler.py    【重构】handle_message(ws, session, msg, executor)
│                    └─ run_agent_loop：Anthropic 流式 + 工具分发
├── agent_tools.py   【新建】工具定义 + SYSTEM_PROMPT（render_gosling 等）
├── session.py       Session dataclass（+ 持有 kernel 句柄）
├── data_api.py      /api/umap /api/coords /api/contact /api/track（真实数据）✅已有
├── tileset_api.py   HiGlass 兼容 tileset（Gosling matrix 用）✅已有
├── track_wig.py     /api/track_wig/{name}（Gosling 信号轨道 CSV）✅已有
├── strc_api.py      /api/tads /api/loops /api/compartments ✅已有
├── notebook_api.py  【新建】jupyter_client 内核管理 + 执行端点
├── agui_events.py   AG-UI 事件构造 ✅已有
└── figure_render.py SVG 导出（非 FigureComposer UI）
```

### 关键架构原则
- **单一数据源**：可视化面板（Embedding/3D/Genomic）全部走 REST 读后端内存里的
  `session.chromdata`，无 demo 数据。
- **Notebook 隔离**：IPython 内核是独立进程，启动时按 session 数据路径
  `cd = ChromData.read(path)` 重载——Notebook 里改 `cd` 不污染可视化面板（合理隔离）。
- **入口唯一**：删除两个 ws_handler 各自的 `app`/`/ws`，只保留 main.py。

### 删除清单
- 旧组件：`IGVPanel` `HiGlassPanel` `FigureComposer` `FigurePreview` `MainCanvas`
  `PanelContainer` `AgentPanel` `DataTree` `CellEmbedding` `StructureViewer`
  `A2UIChat` `FileBrowser` 等未接入组件
- `ws_handler_gosling_staging.py`（精华迁出后删除）
- demo 端点 `/api/embedding` `/api/structure3d`

---

## 4. 前端组件 + 状态管理

### 组件树（目标态）
```
App.tsx
├── TopBar                  Open File（WS load_data）+ 数据集名 + 设置
├── TwoColumnLayout
│   ├── ChatPanel           WS /ws/main：对话流 + artifact 卡片
│   └── TabContainer
│       ├── GenomicPanel    └─ GoslingRenderer（spec 驱动）
│       ├── EmbeddingPanel  deck.gl UMAP
│       ├── Structure3DPanel Three.js
│       └── NotebookPanel   └─ CodeCell[] + OutputArea（@nteract/outputs）
└── GenomicNavBar           chrom:start-end + 分辨率（双向同步）
```

### Zustand store（单一状态源）
```typescript
interface AppStore {
  dataLoaded: boolean
  datasetInfo: { path, n_cells, n_spots, ... } | null
  activeTab: 'genomic' | 'embedding' | 'structure3d' | 'notebook'

  // Genomic（A2UI 核心）
  activeGoslingSpec: GoslingSpec | null
  goslingArtifacts: GoslingArtifact[]   // chat 里列出的历史 spec
  applyGoslingPatch: (patch) => void

  // 跨 Tab 联动状态（全面联动）
  viewport: { chrom, start, end }        // Genomic ↔ NavBar ↔ 3D 高亮
  cellSelection: string[]                // Embedding ↔ 3D
  highlightBins: number[]                // viewport → 3D bin 高亮

  // Embedding / 3D（Agent 可控）
  embeddingColorBy: string               // marker / cell_type
  structureTarget: { cell_id, chrom }
  structureColorBy: string

  // Notebook（混合模式）
  notebookCells: { id, source, outputs, source_agent }[]

  messages: ChatMessage[]
}
```

### A2UI 渲染流
```
WS agent_artifact 到达
  ├─ gosling_spec    → setActiveGoslingSpec + push goslingArtifacts + 切 Genomic Tab
  ├─ gosling_patch   → applyGoslingPatch（局部更新）
  ├─ embedding_update→ setEmbeddingColorBy / cellSelection
  ├─ structure_update→ setStructureTarget / structureColorBy
  ├─ notebook_cell   → 追加 notebookCells（标 source_agent）
  └─ analysis_result → 存结果，供后续工具引用
```

### 跨 Tab 全面联动（store 作为中枢）
- Gosling pan/zoom → `viewport` → NavBar 显示 + 3D 高亮对应 bin
- Embedding 框选细胞 → `cellSelection` → 3D 显示该细胞结构
- 所有联动经 Zustand，组件订阅各自关心的切片

---

## 5. Agent 工具集 + WebSocket 协议

### 工具集（全部定义，Gosling 先实现，其余占位）

| 工具 | 输入 | 产出 artifact | 第一版状态 |
|---|---|---|---|
| `render_gosling` | title, spec | `gosling_spec` | ✅ 完整实现 |
| `patch_gosling` | target_id, patch | `gosling_patch` | ✅ 完整实现 |
| `color_embedding` | color_by | `embedding_update` | 🔲 占位 |
| `select_cells` | cell_ids / criteria | `cell_selection` | 🔲 占位 |
| `show_structure` | cell_id, chrom | `structure_update` | 🔲 占位 |
| `color_structure` | color_by | `structure_update` | 🔲 占位 |
| `add_notebook_cell` | code, run? | `notebook_cell` | ✅ 实现（依赖内核） |
| `run_analysis` | type, region | `analysis_result` | 🔲 占位（strc_api 已有） |

"占位" = 工具 schema + artifact 协议 + 前端 handler 全部定义到位，渲染端先做最小实现或
显式 TODO，保证协议闭环、后续填实不改接口。

### WebSocket 协议（`/ws/main`）

前端 → 后端：
```json
{ "type": "user_message", "text": "..." }
{ "type": "load_data", "path": "/path/to/data.h5cd" }
{ "type": "update_viewport", "payload": { "chrom","start","end" } }
{ "type": "select_cells", "payload": { "cell_ids": [...] } }
```

后端 → 前端：
```json
{ "type": "agent_token", "text": "..." }                          // 流式文本
{ "type": "agent_tool_start", "tool": "render_gosling" }          // 工具开始
{ "type": "agent_artifact", "artifact_type": "gosling_spec",
  "artifact_id": "viz_001", "title": "...", "content": {...} }
{ "type": "agent_artifact", "artifact_type": "gosling_patch",
  "target_id": "viz_001", "patch": { "op","path","value" } }
{ "type": "agent_done" }                                          // 本轮结束
{ "type": "data_loaded", "stats": {...} }
{ "type": "error", "message": "..." }
```

### Agent loop（`run_agent_loop`）
```
收到 user_message
  → 调 AsyncAnthropic(stream=True)，带 TOOLS + 当前数据上下文（可用 track/chrom 列表注入 system）
  → for _ in range(MAX_TOOL_ITERATIONS):      # 上限保护
       流式 emit agent_token
       若有 tool_use：执行工具 → emit agent_artifact → tool_result 回灌对话
       否则 break
    else: emit "已达最大工具轮次"
  → emit agent_done
```

### "加载即生成默认图"机制
`load_data` 完成后，后端自动构造一条内部 user_message（如"概览这份数据：UMAP + chr1 信号
+ 第一个细胞 3D"），跑一次 agent loop，产出默认 artifact 填充各 Tab。

---

## 6. 数据流 + Notebook 内核生命周期

### 完整数据流
```
用户 Open File(.h5cd)
  → WS load_data{path}
  → 后端 session.chromdata = ChromData.read(path)
  → 起 IPython 内核，注入 cd = ChromData.read(path)
  → emit data_loaded{stats}
  → 后端自动跑"默认概览"agent loop（render_gosling/color_embedding/show_structure）
  → 各 Tab 填充

后续可视化数据（REST，读 session.chromdata 内存对象）：
  /api/umap            → EmbeddingPanel (deck.gl)
  /api/coords/batch    → Structure3DPanel (Three.js)
  /api/track_wig/{name}→ GenomicPanel (Gosling 信号轨道 CSV)
  /api/v1/tileset_info → GenomicPanel (Gosling matrix tile)
  /api/tads|loops|comp → Gosling overlay

Notebook 数据（独立内核，ZMQ）：
  CodeCell → execute → 内核 → iopub mime bundle → OutputArea
```

### Notebook 内核生命周期（jupyter_client）
```
load_data 时：
  km = AsyncKernelManager(kernel_name="python3"); await km.start_kernel()
  kc = km.client()
  kc.execute("import uchrom; cd = uchrom.core.ChromData.read('<path>')")  # 注入数据
  session.kernel = (km, kc)

执行 cell：
  msg_id = kc.execute(code)
  while True:                          # 收 iopub
    msg = await kc.get_iopub_msg(timeout=30)
    分类：stream / display_data / execute_result / error → 转 {output_type,...} 推前端
    status==idle → 本 cell 完成

中断：kc 发 interrupt
WS 断开 / 新 load_data：await km.shutdown_kernel()；清理旧内核
```

### 接触矩阵最小验证（实现前置步骤）
```
起后端 + 真实 .h5cd
  → 确认 /api/v1/tileset_info?d=contact-chrX 返回 Gosling 能解析的 tileset_info
  → 确认 /api/v1/tiles 返回正确 dense array 编码
  → Gosling matrix(data.type:"matrix", mark:"bar") 能渲染出接触图
能成 → 复用；不能成 → 单列修复任务，不阻塞信号轨道开发
```

### 错误处理
- **数据加载失败**：`ChromData.read` 异常 → emit error，前端 toast，Tab 保持空状态
- **Agent 工具失败**：工具内异常 → tool_result 带错误回灌，Agent 自我修正或告知用户
- **Gosling spec 无效**：GoslingComponent 渲染异常 → ErrorBoundary 兜底，卡片显示"spec 无效"，不崩整页
- **内核执行**：超时(30s) → 中断 + 提示；异常 → error mime 渲染 traceback；内核崩溃 → 重启提示
- **tileset 不兼容**：矩阵 Tab 显示占位 + 说明，不阻塞其他功能

---

## 7. 测试策略

**后端**（pytest + FastAPI TestClient，沿用 `tests/test_strc_api.py` 模式）：
- `handle_message`：各消息类型分发（mock ws，断言 emit 的事件序列）
- 工具执行：`render_gosling` 产出合法 artifact；`run_analysis` 调 strc 正确
- REST 端点：`/api/umap` `/api/coords` 用 mock ChromData（沿用 `_make_mock_cd_with_coords`）
- Notebook 内核：起内核 → 执行 print / matplotlib → 断言 mime bundle；超时/异常路径
- 默认图机制：load_data 后断言自动跑了 agent loop

**前端**（Vitest + React Testing Library）：
- store：applyGoslingPatch、跨 Tab 联动（viewport→highlightBins、cellSelection）
- artifact 路由：各 artifact_type 进对应 store 切片
- GoslingRenderer：spec 变化触发渲染；ErrorBoundary 兜无效 spec

**真实数据验证**（CLAUDE.md 纪律，硬要求）：
- 用真实 `.h5cd` 起全栈，逐 Tab 人工验证：UMAP / 3D / Gosling 信号轨道 / 接触矩阵 / Notebook 执行
- ChatPanel 输入"显示 chrX ATAC" → 确认 Agent 产 gosling_spec 并渲染
- 在 `example-data/README.md` 记录所用数据集

---

## 8. 实施阶段（自底向上，每阶段可验证）

| 阶段 | 内容 | 验收 |
|---|---|---|
| **P0 修复启动** | 重构 ws_handler→`handle_message`，删冗余 app/staging，单一入口 | `import webapp.backend.main` 无错；后端起得来 |
| **P1 真实端点接线** | EmbeddingPanel→`/api/umap`、Structure3DPanel→`/api/coords`、ChatPanel WS→`/ws/main`；删 demo 端点 | 加载真实数据，Embedding+3D 渲染真实结构 |
| **P2 Gosling A2UI 闭环** | agent_tools.py（render/patch_gosling）+ GoslingRenderer + 信号轨道（track_wig）；默认图机制 | 对话"显示 chrX ATAC"→渲染；增量改色 |
| **P2.5 tileset 验证** | 最小验证接触矩阵 tileset→Gosling matrix | 矩阵能渲染 / 或单列修复任务 |
| **P3 Notebook 内核** | notebook_api.py（jupyter_client）+ NotebookPanel（cell+@nteract）+ add_notebook_cell 工具 | Agent 生成 cell + 用户编辑执行，富显示 |
| **P4 其余工具+联动** | color_embedding/select_cells/show_structure/color_structure/run_analysis 填实 + 跨 Tab 全面联动 | 各 Tab 可被 Agent 操控；联动生效 |
| **P5 清理+测试** | 删旧组件、补测试、真实数据 E2E、文档 | 测试通过；清理完毕 |

### git
全程在 worktree（`feat/phase0-viewer-integration`），不碰 git 历史（误提交到 main 的 commit
由用户处理）。提交时机由用户决定。

---

## 9. 关联文档
- `context/20260610-webapp-final-plan.md` — 方案级总览
- `context/20260610-backend-status-and-plan.md` — 现状勘查 + 阻断问题
- `context/webapp_redesign_proposal.md` — 原始重构方案
- `context/20260610-gosling-agui-design.md` — Gosling 作为 A2UI 输出格式
- `context/20260610-phase3-gosling-plan.md` — Gosling 集成技术选型
- ~~`docs/data_portal_design.md`~~ — 属于数据门户 worktree，本分支不涉及
