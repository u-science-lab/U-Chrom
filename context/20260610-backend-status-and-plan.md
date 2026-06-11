# U-Chrom WebApp 后端现状 & 收口计划

**日期**：2026-06-10
**分支**：`feat/phase0-viewer-integration`（worktree：`.claude/worktrees/webapp`）
**作者**：现状勘查 + 合并方案
**状态**：⛔ 后端当前无法启动（见 §1 阻断问题）

---

## 0. TL;DR

worktree 后端目前**起不来**：`main.py` 第 8 行 `from .ws_handler import handle_message`
导入了一个**不存在**的符号。根因是 worktree 里并存两套互相冲突的后端实现，前端
也有两套 WS 客户端、面板调用的端点一半指向尚未合并的 staging 文件。

收口方向（详见 §5）：以 `main.py`（功能完整、router 化、连真实 ChromData）为唯一入口，
把 Gosling agent loop 重写成 `handle_message(ws, session, msg, executor)` 挂到 `/ws/main`，
新增 `/api/execute_code`，前端面板改连真实端点，删掉 demo 端点和未接入的旧组件。

---

## 1. 阻断问题（必须先修）

| # | 问题 | 证据 | 影响 |
|---|---|---|---|
| **B1** | `handle_message` 不存在 | `main.py:8` 导入它；`grep "def handle_message" webapp/backend/` 全仓零命中 | **后端 import 即崩，无法启动** |
| **B2** | 两套 ws_handler 并存 | `ws_handler.py`(7KB) 与 `ws_handler_gosling_staging.py`(12.6KB) 都各自 `app=FastAPI()`+`@app.websocket("/ws")`+`run_agent_loop`，都**没有** `handle_message` | 职责重叠、入口冲突 |
| **B3** | 前端两套 WS 客户端，路径不一致 | `ws.ts`→`/ws/main`；`ChatPanel.tsx:26`→`/ws` | live App 用 ChatPanel(`/ws`)，但 `main.py` 只暴露 `/ws/main` → 连不上 |

---

## 2. 后端文件清单（worktree `webapp/backend/`）

| 文件 | 角色 | 状态 |
|---|---|---|
| `main.py` | **权威入口**：FastAPI + 5 个 router + HiGlass alias + `/ws/main` + upload/download/export/plugins | ✅ 保留为唯一入口（待修 B1） |
| `data_api.py` | 真实数据端点：`/api/umap`、`/api/coords/{id}`+`/batch`、`/api/contact/{chrom}`、`/api/track/{name}`、`/api/bins`、`/api/browse` | ✅ 真实，连 ChromData |
| `tileset_api.py` | HiGlass 兼容 tileset（`tileset_info`/`tiles`） | ✅ 保留 |
| `track_wig.py` | `/api/track_wig/{name}` 信号轨道（Gosling CSV） | ✅ 保留 |
| `strc_api.py` | 结构分析端点（tads/loops/compartments） | ✅ 保留 |
| `figure_render.py` | SVG 出图 | ✅ 保留 |
| `session.py` | `Session` dataclass（chromdata/viewport/selection/...） | ✅ 保留 |
| `agui_events.py` | AG-UI 事件构造 | ✅ 复用 |
| `ws_handler.py` | 旧 Gosling 版（自带 app+`/ws`，只有 run_agent_loop） | ⚠️ 待重构为 `handle_message` |
| `ws_handler_gosling_staging.py` | 我合并保留的完整版（+`/api/load`、`/api/execute_code`、demo `/api/embedding`+`/api/structure3d`） | 🔀 取其精华后删除 |

### staging 文件里值得保留的部分
- ✅ `_run_code_sync(code)` + `/api/execute_code`：ThreadPoolExecutor 跑 `exec()`，捕获
  stdout/stderr + matplotlib base64 PNG。**main.py 体系完全没有，必须迁入。**
- ✅ `run_agent_loop` 的 `for _ in range(MAX_TOOL_ITERATIONS)` + `else` 上限保护。
- ✅ `TOOLS`（`render_gosling`）+ `SYSTEM_PROMPT`（Gosling spec 规则）。
- ❌ demo `/api/embedding`、`/api/structure3d`、`/api/load`：被 data_api 的真实端点取代，丢弃。

---

## 3. 前端现状（worktree `webapp/frontend/src/`）

### 真正接入的组件树
```
App.tsx
├── TopBar              (✅ 已收口：Open File modal → /api/load)
├── TwoColumnLayout
│   ├── ChatPanel       (WS → /ws  ⚠️ 应为 /ws/main)
│   └── TabContainer
│       ├── GenomicPanel      → /api/v1/tileset_info        ✅
│       ├── EmbeddingPanel    → /api/embedding   ❌应为 /api/umap
│       ├── Structure3DPanel  → /api/structure3d ❌应为 /api/coords/batch
│       └── NotebookPanel     → /api/execute_code ❌端点未迁入 main.py
└── GenomicNavBar
```

### 未接入但仍在仓库里的旧组件（候选删除）
`AgentPanel.tsx`、`DataTree.tsx`（用旧 `ws.ts`→`/ws/main`）、`IGVPanel.tsx`、
`HiGlassPanel.tsx`、`CellEmbedding.tsx`、`StructureViewer.tsx`、`MainCanvas.tsx`、
`PanelContainer.tsx`、`FigureComposer.tsx`、`FigurePreview.tsx`、`FileBrowser.tsx`、
`A2UIChat.tsx`、`StructureViewer.tsx` 等 —— 方案文档明确要移除 IGV/HiGlass/网格布局。

---

## 4. 前端期待 vs 后端提供（差距矩阵）

| 前端调用 | 后端真实端点 | 动作 |
|---|---|---|
| `/api/embedding` | `/api/umap`（data_api ✅） | 改前端 EmbeddingPanel |
| `/api/structure3d` | `/api/coords/batch`（data_api ✅） | 改前端 Structure3DPanel |
| `/api/execute_code` | （无） | 从 staging 迁入 main.py 体系 |
| `/ws`（ChatPanel） | `/ws/main`（main.py ✅） | 改前端 ChatPanel WS 路径 |
| `/api/load`（TopBar） | WS `load_data` 或新增 REST | 决定走 REST `/api/load`（迁入） |
| `/api/v1/tileset_info`（Genomic） | main.py alias ✅ | 无需改 |

---

## 5. 收口计划（下一步开发）

> 原则：**main.py 单一入口**，data_api 真实端点优先，删除 demo 与未接入旧组件。
> 全程在 worktree，**不碰 git 历史**（误提交到 main 的 3 个 commit 由用户自行处理）。

### Step 1 — 修复 B1/B2：统一后端入口
1. 新建 `ws_handler.py`（重写）：把 `run_agent_loop`/`TOOLS`/`SYSTEM_PROMPT` 包成
   `async def handle_message(ws, session, msg, executor)`，签名匹配 `main.py:51` 的调用。
   - 处理消息类型：`user_message`（跑 agent loop）、`load_data`、`update_viewport`、
     `select_cells`、`run_analysis`（参照旧 841f1cbcb 的 handle_message 骨架）。
   - 通过 `session` 而非模块全局拿 ChromData；agent 产出 `agent_artifact`(gosling_spec/patch)。
2. 删除 `ws_handler_gosling_staging.py`（精华已迁出）。
3. 移除两个 ws_handler 里各自的 `app=FastAPI()`/`@app.websocket("/ws")`/`serve_frontend`
   —— 入口只能是 main.py。

### Step 2 — 迁入 Notebook 执行
4. 把 `_run_code_sync` + `/api/execute_code` 作为新 router（或挂在 main.py）迁入，
   ThreadPoolExecutor 注入 `uchrom` + `cd=current_session.chromdata`，30s 超时保护。

### Step 3 — 前端连真实端点
5. EmbeddingPanel：`/api/embedding` → `/api/umap`（响应字段 `points[{cell_id,x,y,cell_type}]`）。
6. Structure3DPanel：`/api/structure3d` → `/api/coords/batch`（float32 binary）。
7. ChatPanel：`/ws` → `/ws/main`（或统一用 `ws.ts`）。
8. 校验 NotebookPanel ↔ `/api/execute_code` 字段（`{outputs:[...]}`）。

### Step 4 — 清理
9. 删除 demo 端点（embedding/structure3d/load 的 demo 版，若已被真实端点取代）。
10. 删除未接入旧组件（IGV/HiGlass/MainCanvas/AgentPanel/DataTree/CellEmbedding/...）。
11. 删除 `ws.ts` 或 `ChatPanel` 内联 WS 之一，避免双客户端。

### Step 5 — 验证（按 CLAUDE.md 纪律：真实数据）
12. 起后端 `python -m webapp.backend.main`（或 uvicorn），确认无 import 错误。
13. 加载真实 `.h5cd`，逐 Tab 验证：Genomic 渲染 / Embedding UMAP / 3D 结构 / Notebook 执行。
14. ChatPanel 输入"显示 chrX ATAC"，确认 agent 产出 gosling_spec 并渲染。

---

## 6. 验收标准
- [ ] `python -c "import webapp.backend.main"` 无错（B1 修复）
- [ ] 后端仅一个 FastAPI app、一个 WS 端点 `/ws/main`（B2 修复）
- [ ] 前端 4 个 Tab 全部连真实 ChromData 端点，无 demo 残留
- [ ] ChatPanel 经 `/ws/main` 收发，agent 可产 gosling_spec（B3 修复）
- [ ] 旧 IGV/HiGlass/网格组件已删除
- [ ] `example-data/README.md` 记录验证所用数据集（若新引入）

---

## 7. 关联文档
- `context/webapp_redesign_proposal.md` — 两栏布局 + Gosling + Notebook 总方案
- `context/20260610-gosling-agui-design.md` — Gosling spec 作为 A2UI 输出格式
- `context/20260610-phase3-gosling-plan.md` — Gosling 集成技术选型
- `context/20260610-webapp-phase1-complete.md` — Phase 1 完成记录
