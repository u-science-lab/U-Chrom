# U-Chrom WebApp 最终方案：对话驱动的染色质分析工作台

**日期**：2026-06-10
**分支**：`feat/phase0-viewer-integration`（worktree：`.claude/worktrees/webapp`）
**状态**：方案定稿（开发暂停，先对齐方案）
**产品定位决策**：本分支**只做分析工作台**。数据门户（Data Portal / cellxgene 类）是**另一个 worktree** 的事，本分支不涉及。

---

## 1. 产品定位

**一句话**：U-Chrom WebApp 是一个**对话驱动**的染色质 3D 结构**分析工作台**——研究者加载自己的 ChromData，通过与 AI Agent 对话来可视化、分析、探索数据。

### 1.1 核心理念：A2UI（Agent-to-UI）
Agent 不只是回答问题，而是**直接驱动界面**。用户说"显示 chr21 的 ATAC 信号和接触矩阵"，
Agent 生成 **Gosling.js JSON spec**，前端直接渲染。Gosling 的声明式 JSON spec 天然契合
LLM 的结构化输出能力，使"对话即可视化"成为现实。

```
用户: "显示 chr21 的 ATAC 信号和 Hi-C 矩阵"
  ↓ Claude 调用 render_gosling 工具，生成 Gosling spec JSON
  ↓ WebSocket emit agent_artifact (type: gosling_spec)
  ↓ 前端 GoslingComponent 渲染到 Genomic Tab
  ↓ 用户继续: "换成 bar 图" / "加上 TAD 边界"
  ↓ Agent emit gosling_patch (增量修改) 或新 spec
```

### 1.2 目标用户
正在分析**自己**染色质结构数据（FISH/染色质追踪/Hi-C 重建）的研究者。
区别于数据门户的"浏览下载他人数据"，这里是"分析我的数据"。

### 1.3 非目标（明确排除）
- ❌ 数据集发布 / 搜索 / 下载门户（属于另一 worktree）
- ❌ 多用户协作 / 账号系统
- ❌ IGV / HiGlass 原生面板（统一用 Gosling 替代）
- ❌ Plotly 预生成静态图（工作台用 Gosling + deck.gl + Three.js 实时渲染）

---

## 2. 功能清单

### 2.1 左侧：Chat 面板（对话驱动核心）
- 与 Claude Agent 自然语言对话
- Agent 流式回复（token streaming）
- Agent 可调用工具：
  - `render_gosling` — 生成基因组可视化 spec → Genomic Tab
  - （规划）`run_analysis` — 触发 TAD/loop/compartment 分析
  - （规划）`add_notebook_cell` — 向 Notebook Tab 插入代码 cell
- Chat 中展示 Agent 产出的 artifact 卡片（点击"打开"切到对应 Tab）

### 2.2 右侧：四个 Tab

| Tab | 技术 | 数据源 | 功能 |
|---|---|---|---|
| **Genomic** | Gosling.js | `/api/track_wig/{name}`、tileset API | 信号轨道（bar/line/area）+ 接触矩阵（rect mark）+ TAD/loop overlay |
| **Embedding** | deck.gl | `/api/umap` | 细胞 UMAP 散点，按 cell_type 着色，框选细胞 |
| **3D Structure** | Three.js | `/api/coords/batch` | 单细胞/单条染色质 3D 结构，OrbitControls，按 marker/compartment 着色 |
| **Notebook** | 自建 cell UI | `/api/execute_code` | **混合模式**：Agent 生成 cell + 用户可编辑/手动添加 cell，服务端 `exec()` 执行，渲染 stdout/图片 |

### 2.3 顶部 / 底部
- **TopBar**：Logo + "Open File"（加载 `.h5cd` → `/api/load` 或 WS `load_data`）+ 设置
- **GenomicNavBar**：当前 `chrom:start-end` + 分辨率，与 Gosling viewport 双向同步

### 2.4 Notebook Tab 交互模式（已定：混合模式）
- Agent 生成的代码自动插入为新 cell
- 用户可**编辑**这些 cell 并重新执行
- 用户可**手动添加**新 cell
- 每个 cell 独立执行，输出渲染在下方（文本 + matplotlib PNG）
- 共享一个持久 namespace（注入 `uchrom` + `cd = 当前 ChromData`）

---

## 3. 整体架构

### 3.1 技术栈
- **前端**：React 18 + Vite + TypeScript + Tailwind + Zustand
- **可视化**：Gosling.js（基因组）+ deck.gl v9（UMAP）+ Three.js v0.163（3D）
- **后端**：FastAPI + WebSocket（单一入口 `main.py`）
- **Agent**：AsyncAnthropic（非阻塞）+ ThreadPoolExecutor（跑 exec）
- **数据核心**：`uchrom.core.ChromData`

### 3.2 组件树（目标态）
```
App.tsx
├── TopBar                  Open File → 加载 ChromData
├── TwoColumnLayout
│   ├── ChatPanel           WS /ws/main，对话 + artifact 卡片
│   └── TabContainer
│       ├── GenomicPanel    Gosling 渲染（GoslingRenderer）
│       ├── EmbeddingPanel  deck.gl UMAP    → /api/umap
│       ├── Structure3DPanel Three.js 3D    → /api/coords/batch
│       └── NotebookPanel   混合 cell UI    → /api/execute_code
└── GenomicNavBar           viewport 同步
```

### 3.3 后端结构（目标态，单一入口）
```
webapp/backend/
├── main.py          唯一 FastAPI 入口：router 注册 + /ws/main + upload/download/export
├── ws_handler.py    handle_message(ws, session, msg, executor) — 重构，含 agent loop
├── session.py       Session dataclass
├── data_api.py      /api/umap /api/coords /api/contact /api/track /api/browse（真实数据）
├── tileset_api.py   HiGlass 兼容 tileset
├── track_wig.py     /api/track_wig/{name}（Gosling CSV）
├── strc_api.py      /api/tads /api/loops /api/compartments
├── notebook_api.py  /api/execute_code（新建，从 staging 迁入）
├── agui_events.py   AG-UI 事件构造
└── figure_render.py SVG 出图（导出用，非 FigureComposer UI）
```

### 3.4 WebSocket 消息协议（AG-UI）
**前端 → 后端**（`/ws/main`）：
```json
{ "type": "user_message", "text": "显示 chr21 ATAC" }
{ "type": "load_data", "path": "/path/to/data.h5cd" }
{ "type": "update_viewport", "payload": {...} }
{ "type": "select_cells", "payload": {...} }
```
**后端 → 前端**：
```json
{ "type": "agent_token", "text": "..." }                       // 流式文本
{ "type": "agent_artifact", "artifact_type": "gosling_spec",
  "artifact_id": "viz_001", "title": "...", "content": {...} } // 渲染 spec
{ "type": "agent_artifact", "artifact_type": "gosling_patch",
  "target_id": "viz_001", "patch": {...} }                     // 增量修改
{ "type": "data_loaded", "stats": {...} }
```

---

## 4. A2UI 交互设计（核心差异化）

### 4.1 render_gosling 工具
Agent 通过此工具产出 Gosling spec。System prompt 内置 Gosling 规则：
- 必设 `assembly`（hg19/hg38/mm10）
- 多轨道用 `arrangement: "vertical"`
- 信号轨道数据源：`{type:"csv", url:"/api/track_wig/{name}", chromosomeField:"chrom", genomicFields:["start","end"]}`
- 接触矩阵：`rect` mark + 二维 genomic 字段，数据走 tileset API
- 常用 mark：bar/line/area（信号）、rect（矩阵/注释）、withinLink（loop）

### 4.2 增量修改（gosling_patch）
用户说"换个颜色"，Agent 只需发 JSON Patch（`{op, path, value}`）修改活跃 spec 的单个字段，
前端 `applyGoslingPatch` 局部更新，无需重渲染整个 spec。

### 4.3 与其他 Tab 的协同（规划）
```
用户: "分析 chr21 的 TAD，然后可视化"
  Agent:
  1. add_notebook_cell（Python: uchrom.strc.tad 检测 TAD）→ Notebook Tab 执行
  2. 拿到 TAD 坐标
  3. render_gosling（TAD 边界叠加到 ATAC 轨道）→ Genomic Tab
```

---

## 5. 数据流

```
.h5cd 文件
  ↓ TopBar Open File / WS load_data
ChromData (session.chromdata)
  ├→ /api/umap         → EmbeddingPanel (deck.gl)
  ├→ /api/coords/batch → Structure3DPanel (Three.js)
  ├→ /api/track_wig    → GenomicPanel (Gosling 信号轨道)
  ├→ tileset API       → GenomicPanel (Gosling 接触矩阵)
  ├→ /api/tads 等      → Gosling overlay
  └→ /api/execute_code → NotebookPanel (cd 注入 namespace)
```
**关键**：所有面板共享 `session.chromdata` 这一份真实数据，无 demo / 假数据。

---

## 6. 当前状态 vs 目标态（待办，见配套文档）

详细的现状勘查、阻断问题、收口步骤见
[`20260610-backend-status-and-plan.md`](./20260610-backend-status-and-plan.md)。

摘要：
- ⛔ **后端当前无法启动**：`main.py:8` 导入不存在的 `handle_message`
- 🔀 两套 ws_handler 并存需合并为单一 `handle_message`
- 🔌 前端面板仍连 demo 端点（`/api/embedding`、`/api/structure3d`），需改连真实端点
- 🧹 待删除：IGV/HiGlass/FigureComposer 及其他未接入旧组件
- ➕ 待迁入：`/api/execute_code`（Notebook 执行）

---

## 7. 已确认的方案决策（本次对齐）

| 决策点 | 结论 |
|---|---|
| **产品定位** | 只做分析工作台；数据门户归另一 worktree |
| **可视化技术** | 统一 Gosling（基因组）+ deck.gl（UMAP）+ Three.js（3D）；**删除 IGV/HiGlass/FigureComposer** |
| **Notebook 模式** | **混合模式**：Agent 生成 cell + 用户可编辑/手动添加 |
| **后端入口** | 单一 `main.py`，WS 端点 `/ws/main` |
| **数据真实性** | 所有面板连真实 ChromData，无 demo 数据 |
| **git** | 全程 worktree，不碰 git 历史（误提交到 main 的 commit 由用户处理） |

---

## 8. 关联文档
- `20260610-backend-status-and-plan.md` — 现状勘查 + 收口步骤（实施级）
- `webapp_redesign_proposal.md` — 原始重构方案（两栏 + Gosling + Notebook）
- `20260610-gosling-agui-design.md` — Gosling 作为 A2UI 输出格式
- `20260610-phase3-gosling-plan.md` — Gosling 集成技术选型
- `20260610-webapp-phase1-complete.md` — Phase 1 完成记录
- ~~`docs/data_portal_design.md`~~ — **属于数据门户 worktree，本分支不涉及**
