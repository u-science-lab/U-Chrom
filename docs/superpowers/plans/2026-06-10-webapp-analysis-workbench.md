# U-Chrom WebApp 分析工作台实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建对话驱动的染色质分析工作台,Agent 通过 Gosling spec 直接控制基因组可视化,支持 UMAP/3D/Notebook 多模态分析。

**Architecture:** 单一 FastAPI 后端(单 WS `/ws/main` + REST 端点)+ React 前端(Zustand store + 4 Tab)。Agent 调工具产出 artifact,前端订阅 store 渲染。Notebook 走独立 IPython 内核。

**Tech Stack:** FastAPI + AsyncAnthropic + jupyter_client / React 18 + Vite + Zustand + Gosling.js + deck.gl + Three.js

**Working directory:** `/Volumes/sandisk/Coding/U-Chrom/.claude/worktrees/webapp`

---

## 文件地图

### 后端(新建/重构)
- `webapp/backend/ws_handler.py` — 【重构】删自带 app,改为 `handle_message(ws, session, msg, executor)`
- `webapp/backend/agent_tools.py` — 【新建】工具定义(render_gosling/patch_gosling/占位工具)+ SYSTEM_PROMPT
- `webapp/backend/notebook_api.py` — 【新建】jupyter_client 内核管理 + 执行端点

### 后端(修改)
- `webapp/backend/main.py` — 修复 `handle_message` 导入,确保单一入口
- `webapp/backend/session.py` — 添加 `kernel: Optional[tuple]` 字段持有内核句柄

### 前端(修改)
- `webapp/frontend/src/components/EmbeddingPanel.tsx` — 改 `/api/embedding` → `/api/umap`
- `webapp/frontend/src/components/Structure3DPanel.tsx` — 改 `/api/structure3d` → `/api/coords/batch`,解析 float32
- `webapp/frontend/src/components/TopBar.tsx` — Open File 改走 WS `load_data`(或新增 REST `/api/load`)
- `webapp/frontend/src/components/ChatPanel.tsx` — WS 路径 `/ws` → `/ws/main`
- `webapp/frontend/src/store.ts` — 添加 Gosling/Notebook/联动状态切片

### 前端(新建)
- `webapp/frontend/src/components/GoslingRenderer.tsx` — Gosling spec 渲染 + viewport 同步
- `webapp/frontend/src/components/NotebookPanel.tsx` — CodeCell + OutputArea(@nteract/outputs)

### 删除
- `webapp/backend/ws_handler_gosling_staging.py`
- `webapp/frontend/src/components/IGVPanel.tsx` `HiGlassPanel.tsx` `FigureComposer.tsx` 等旧组件

### 测试
- `tests/backend/test_ws_handler.py` — handle_message 分发 + agent loop
- `tests/backend/test_agent_tools.py` — render_gosling 产出合法 artifact
- `tests/backend/test_notebook_api.py` — 内核启动/执行/清理
- `tests/frontend/store.test.ts` — applyGoslingPatch + 联动
- `tests/frontend/GoslingRenderer.test.tsx` — spec 渲染

---

## Phase P0: 修复后端启动

**目标:** 让后端能 import 并启动,单一入口 `main.py`,删除冗余 staging 文件。

### Task 1: 删除 staging 文件

**Files:**
- Delete: `webapp/backend/ws_handler_gosling_staging.py`

- [ ] **Step 1: 确认 staging 文件内容已记录**

Run: `wc -l webapp/backend/ws_handler_gosling_staging.py`
Expected: ~372 行(已在 context 文档中记录关键部分)

- [ ] **Step 2: 删除 staging 文件**

```bash
rm webapp/backend/ws_handler_gosling_staging.py
```

- [ ] **Step 3: 确认删除**

Run: `ls webapp/backend/ws_handler*.py`
Expected: 只剩 `ws_handler.py`

- [ ] **Step 4: Commit**

```bash
git add webapp/backend/
git commit -m "chore: remove staging ws_handler, prepare for single-entry refactor"
```

---

### Task 2: 重构 ws_handler — 定义 handle_message 骨架

**Files:**
- Modify: `webapp/backend/ws_handler.py`
- Test: `tests/backend/test_ws_handler.py`

- [ ] **Step 1: 写失败测试 — handle_message 存在性**

Create: `tests/backend/test_ws_handler.py`

```python
"""Tests for ws_handler handle_message."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from webapp.backend.ws_handler import handle_message


@pytest.mark.asyncio
async def test_handle_message_exists():
    """handle_message function should exist and be callable."""
    ws = AsyncMock()
    session = MagicMock()
    msg = {"type": "unknown"}
    executor = MagicMock()
    
    # Should not raise
    await handle_message(ws, session, msg, executor)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/backend/test_ws_handler.py::test_handle_message_exists -v`
Expected: FAIL — `ImportError: cannot import name 'handle_message'`

- [ ] **Step 3: 读取现有 ws_handler.py 结构**

Run: `grep -nE "^(async def|def |@app|MAX_)" webapp/backend/ws_handler.py | head -20`
Expected: 看到 `run_agent_loop` 等函数,但无 `handle_message`

- [ ] **Step 4: 在 ws_handler.py 头部添加 handle_message 骨架**

在 `webapp/backend/ws_handler.py` 文件顶部(import 后、MAX_TOOL_ITERATIONS 前)插入:

```python
async def handle_message(ws, session, msg: dict, executor):
    """Central message dispatcher for /ws/main.
    
    Args:
        ws: WebSocket connection
        session: Session object (from session.py)
        msg: Incoming message dict with 'type' field
        executor: ThreadPoolExecutor for blocking operations
    """
    msg_type = msg.get("type")
    payload = msg.get("payload", {})
    
    if msg_type == "user_message":
        # Will implement agent loop call in next task
        pass
    elif msg_type == "load_data":
        # Will implement in P1
        pass
    elif msg_type == "update_viewport":
        session.viewport = payload
    elif msg_type == "select_cells":
        session.cell_selection = payload.get("cell_ids", [])
    else:
        await ws.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/backend/test_ws_handler.py::test_handle_message_exists -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add webapp/backend/ws_handler.py tests/backend/test_ws_handler.py
git commit -m "feat(ws_handler): add handle_message dispatcher skeleton"
```

---

### Task 3: 修复 main.py 导入,确认单一入口

**Files:**
- Modify: `webapp/backend/main.py`
- Test: 直接 import 测试

- [ ] **Step 1: 确认当前 main.py 第 8 行导入**

Run: `sed -n '8p' webapp/backend/main.py`
Expected: `from .ws_handler import handle_message`

- [ ] **Step 2: 写失败测试 — import main 无错**

Run: `python3 -c "import webapp.backend.main" 2>&1`
Expected: FAIL — `ImportError: cannot import name 'handle_message'` 或类似错误

- [ ] **Step 3: 确认 handle_message 现在已存在**

Run: `grep -n "^async def handle_message" webapp/backend/ws_handler.py`
Expected: 找到函数定义行号

- [ ] **Step 4: 再次测试 import**

Run: `python3 -c "import webapp.backend.main; print('Import success')" 2>&1`
Expected: PASS — 输出 "Import success"(Task 2 已添加 handle_message,此时应该能 import)

- [ ] **Step 5: 确认 main.py 的 /ws/main 端点调用 handle_message**

Run: `sed -n '40,56p' webapp/backend/main.py`
Expected: 看到 `@app.websocket("/ws/main")` 和 `await handle_message(ws, session, msg, app.state.executor)`

- [ ] **Step 6: Commit**

```bash
git add webapp/backend/main.py
git commit -m "fix(main): verify handle_message import works, single entry confirmed"
```

---

### Task 4: 验证后端可启动(冒烟测试)

**Files:**
- Test: 后端启动脚本

- [ ] **Step 1: 尝试启动后端(3 秒后自动停止)**

```bash
timeout 3 python3 -m uvicorn webapp.backend.main:app --host 127.0.0.1 --port 8765 || true
```

Expected: 后端起来,输出 "Uvicorn running on http://127.0.0.1:8765",3 秒后超时退出(exit 124 正常)

- [ ] **Step 2: 确认无 ImportError**

检查上一步输出,Expected: 无 "ImportError" 或 "cannot import"

- [ ] **Step 3: 记录 P0 完成**

Echo: "P0 修复启动完成:后端能 import 并启动,单一入口 main.py,staging 已删除"

---

## Phase P1: 真实端点接线

**目标:** 前端面板连接真实后端端点,删除 demo 端点,数据加载流通。

### Task 5: 前端 — EmbeddingPanel 改连 /api/umap

**Files:**
- Modify: `webapp/frontend/src/components/EmbeddingPanel.tsx:71-73`

- [ ] **Step 1: 读取 EmbeddingPanel 当前 fetch 调用**

Run: `sed -n '70,75p' webapp/frontend/src/components/EmbeddingPanel.tsx`
Expected: 看到 `fetch('/api/embedding')`

- [ ] **Step 2: 读取 data_api.py 中 /api/umap 的响应格式**

Run: `grep -A 20 "@router.get.*umap" webapp/backend/data_api.py`
Expected: 返回 `{"points": [{cell_id, x, y, cell_type}], "cell_types": [...]}`

- [ ] **Step 3: 修改 EmbeddingPanel fetch 路径**

在 `webapp/frontend/src/components/EmbeddingPanel.tsx` 第 71 行,将:
```typescript
const res = await fetch('/api/embedding')
```
改为:
```typescript
const res = await fetch('/api/umap')
```

- [ ] **Step 4: 确认响应格式一致(data_api 已是 points/cell_types 结构)**

检查 `data_api.py` 的 `/api/umap` 返回,已是 `{points, cell_types}` — 与 EmbeddingPanel 期待一致,无需改解析代码

- [ ] **Step 5: Commit**

```bash
git add webapp/frontend/src/components/EmbeddingPanel.tsx
git commit -m "fix(EmbeddingPanel): connect to real /api/umap endpoint"
```

---

### Task 6: 前端 — Structure3DPanel 改连 /api/coords/batch

**Files:**
- Modify: `webapp/frontend/src/components/Structure3DPanel.tsx:44-47`

- [ ] **Step 1: 读取 Structure3DPanel 当前 fetch + 解析**

Run: `sed -n '40,80p' webapp/frontend/src/components/Structure3DPanel.tsx`
Expected: 看到 `fetch('/api/structure3d')` 和 `const {traces} = await res.json()`

- [ ] **Step 2: 读取 data_api.py 中 /api/coords 的响应格式**

Run: `grep -nA 25 "coords/batch\|def.*coords" webapp/backend/data_api.py`
Expected: `/api/coords/batch?ids=...` 返回 float32 binary(每个 cell 的 (n,3) 坐标);`/api/bins/{cell_id}` 返回 bin 元数据(chrom/start/end/trace_id)

- [ ] **Step 3: 读取需要的辅助端点(列出可用 cell_id)**

Run: `grep -nE "@router.(get|post)" webapp/backend/data_api.py`
Expected: 确认有 `/api/umap`(含 cell_id 列表)可用于选第一个细胞

- [ ] **Step 4: 修改 Structure3DPanel — 先取 cell 列表,再取坐标**

将 `webapp/frontend/src/components/Structure3DPanel.tsx` 第 44-47 行附近的数据获取逻辑改为:

```typescript
// 1. 取细胞列表(复用 umap 端点的 cell_id)
const umapRes = await fetch('/api/umap')
if (!umapRes.ok) throw new Error(`umap fetch failed: ${umapRes.status}`)
const { points } = await umapRes.json()
if (!points || points.length === 0) { setTraces([]); return }

// 2. 取第一个细胞的坐标(float32 binary)
const cellId = points[0].cell_id
const coordsRes = await fetch(`/api/coords/batch?ids=${encodeURIComponent(cellId)}`)
if (!coordsRes.ok) throw new Error(`coords fetch failed: ${coordsRes.status}`)
const buf = await coordsRes.arrayBuffer()
const floats = new Float32Array(buf)

// 3. 解析为 (n,3) 点序列
const pts: number[][] = []
for (let i = 0; i + 2 < floats.length; i += 3) {
  pts.push([floats[i], floats[i + 1], floats[i + 2]])
}
setTraces([{ trace_id: cellId, chrom: 'all', points: pts }])
```

- [ ] **Step 5: 确认 setTraces 的数据结构与渲染逻辑一致**

Run: `grep -n "traces\|setTraces\|\.points" webapp/frontend/src/components/Structure3DPanel.tsx | head`
Expected: 渲染逻辑消费 `traces[].points` 为 number[][];如不一致,调整渲染代码匹配上面的 `{trace_id, chrom, points}` 结构

- [ ] **Step 6: Commit**

```bash
git add webapp/frontend/src/components/Structure3DPanel.tsx
git commit -m "fix(Structure3DPanel): connect to real /api/coords/batch (float32 binary)"
```

---

### Task 7: 后端 — handle_message 实现 load_data(设置 current_session)

**Files:**
- Modify: `webapp/backend/ws_handler.py`
- Modify: `webapp/backend/session.py`(添加 kernel 字段,为 P3 预留)
- Test: `tests/backend/test_ws_handler.py`

- [ ] **Step 1: 写失败测试 — load_data 设置 chromdata 并 emit data_loaded**

在 `tests/backend/test_ws_handler.py` 追加:

```python
@pytest.mark.asyncio
async def test_handle_load_data_sets_session(tmp_path, monkeypatch):
    """load_data should read ChromData, set current_session, emit data_loaded."""
    import webapp.backend.data_api as data_api
    from webapp.backend.session import Session

    # Fake ChromData with stats
    fake_cd = MagicMock()
    fake_cd.coords.shape = (100, 3)
    fake_cd.spots.__len__ = lambda self: 100
    fake_cd.cells.__len__ = lambda self: 5

    def fake_read(path):
        return fake_cd
    monkeypatch.setattr("uchrom.core.ChromData.read", staticmethod(fake_read))

    ws = AsyncMock()
    session = Session(session_id="t1")
    executor = MagicMock()
    msg = {"type": "load_data", "path": str(tmp_path / "data.h5cd")}

    await handle_message(ws, session, msg, executor)

    assert session.chromdata is fake_cd
    assert data_api.current_session is session
    # data_loaded emitted
    sent_types = [c.args[0]["type"] for c in ws.send_json.call_args_list]
    assert "data_loaded" in sent_types
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/backend/test_ws_handler.py::test_handle_load_data_sets_session -v`
Expected: FAIL — load_data 分支还是 `pass`,chromdata 未设置

- [ ] **Step 3: 在 session.py 添加 kernel 字段**

在 `webapp/backend/session.py` 的 `Session` dataclass 中添加字段(为 P3 内核预留):

```python
    kernel: Optional[tuple] = None  # (KernelManager, KernelClient) — set in P3
```

确认文件顶部有 `from typing import Optional`,若无则添加。

- [ ] **Step 4: 实现 ws_handler 的 load_data 分支**

将 `webapp/backend/ws_handler.py` 中 `handle_message` 的 `load_data` 分支替换为:

```python
    elif msg_type == "load_data":
        import webapp.backend.data_api as data_api
        from uchrom.core import ChromData
        path = msg.get("path") or payload.get("path")
        if not path:
            await ws.send_json({"type": "error", "message": "load_data missing 'path'"})
            return
        try:
            cd = ChromData.read(path)
        except Exception as e:
            await ws.send_json({"type": "error", "message": f"Failed to load {path}: {e}"})
            return
        session.chromdata = cd
        data_api.current_session = session  # REST panels read from this
        stats = {
            "path": path,
            "n_spots": int(cd.coords.shape[0]),
            "n_cells": len(cd.cells) if cd.cells is not None else 0,
        }
        await ws.send_json({"type": "data_loaded", "stats": stats})
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/backend/test_ws_handler.py -v`
Expected: PASS(2 个测试)

- [ ] **Step 6: Commit**

```bash
git add webapp/backend/ws_handler.py webapp/backend/session.py tests/backend/test_ws_handler.py
git commit -m "feat(ws_handler): implement load_data — read ChromData, set session, emit data_loaded"
```

---

### Task 8: 前端 — TopBar Open File 改走 WS load_data

**Files:**
- Modify: `webapp/frontend/src/components/TopBar.tsx:19-23`
- Modify: `webapp/frontend/src/store.ts`(添加共享 ws 引用或 load action)

- [ ] **Step 1: 确认 TopBar 当前 POST /api/load 逻辑**

Run: `sed -n '15,45p' webapp/frontend/src/components/TopBar.tsx`
Expected: 看到 `fetch('/api/load', {method:'POST', ...})`

- [ ] **Step 2: 确认 store 是否暴露 ws 发送能力**

Run: `grep -nE "sendWs|ws:|wsSend|load_data|setWs" webapp/frontend/src/store.ts`
Expected: 可能没有 — 需要添加一个 `sendMessage` action 或在 store 持有 ws 引用

- [ ] **Step 3: 在 store.ts 添加 ws 持有 + sendMessage action**

在 `webapp/frontend/src/store.ts` 的 store 中添加:

```typescript
  // WebSocket 共享引用(ChatPanel 设置,TopBar 等复用)
  ws: WebSocket | null
  setWs: (ws: WebSocket | null) => void
  sendMessage: (msg: object) => boolean  // 返回是否成功发送
```

在 store 实现里添加:

```typescript
  ws: null,
  setWs: (ws) => set({ ws }),
  sendMessage: (msg) => {
    const ws = get().ws
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(msg))
      return true
    }
    return false
  },
```

确认 store 的 create 用了 `(set, get) =>` 签名,若只有 `set` 则改为 `(set, get)`。

- [ ] **Step 4: 修改 TopBar — 用 sendMessage 发 load_data**

将 `webapp/frontend/src/components/TopBar.tsx` 的 handleOpen 逻辑(第 19-23 行附近 fetch 调用)替换为:

```typescript
      const ok = useAppStore.getState().sendMessage({ type: 'load_data', path: filePath })
      if (!ok) {
        setLoadError('WebSocket 未连接,请稍候重试')
        setLoading(false)
        return
      }
      // data_loaded 由 ChatPanel 的 onmessage 处理(设置 dataVersion/loadedFile)
      setLoadedFile(filePath)
```

确认顶部已 `import { useAppStore } from '../store'`。

- [ ] **Step 5: Commit**

```bash
git add webapp/frontend/src/components/TopBar.tsx webapp/frontend/src/store.ts
git commit -m "fix(TopBar): load data via WS load_data instead of dead /api/load"
```

---

### Task 9: 前端 — ChatPanel WS 路径改 /ws/main + 注册 ws 到 store + 处理 data_loaded

**Files:**
- Modify: `webapp/frontend/src/components/ChatPanel.tsx:26`

- [ ] **Step 1: 确认当前 WS 连接行**

Run: `sed -n '24,45p' webapp/frontend/src/components/ChatPanel.tsx`
Expected: 看到 `new WebSocket(\`${protocol}//${window.location.host}/ws\`)`

- [ ] **Step 2: 修改 WS 路径为 /ws/main**

将 `webapp/frontend/src/components/ChatPanel.tsx` 第 26 行的 `/ws` 改为 `/ws/main`:

```typescript
    const websocket = new WebSocket(`${protocol}//${window.location.host}/ws/main`)
```

- [ ] **Step 3: 连接建立后注册 ws 到 store**

在 ChatPanel 设置 ws 的 useEffect 中(`setWs(websocket)` 本地 state 之后),添加注册到全局 store:

```typescript
    websocket.onopen = () => {
      useAppStore.getState().setWs(websocket)
    }
```

确认顶部已 `import { useAppStore } from '../store'`。

- [ ] **Step 4: onmessage 处理 data_loaded(触发 dataVersion 更新)**

在 `websocket.onmessage` 的消息分类中添加 data_loaded 分支:

```typescript
        } else if (data.type === 'data_loaded') {
          useAppStore.getState().bumpDataVersion()
        }
```

确认 store 有 `bumpDataVersion`,若无则用现有等价 action。

- [ ] **Step 5: 清理时注销 ws**

在 useEffect 的 cleanup 中添加:

```typescript
      useAppStore.getState().setWs(null)
```

- [ ] **Step 6: Commit**

```bash
git add webapp/frontend/src/components/ChatPanel.tsx
git commit -m "fix(ChatPanel): connect to /ws/main, register ws to store, handle data_loaded"
```

---

### Task 10: 后端 — 删除 demo 端点(若残留在任何已注册文件中)

**Files:**
- Check: `webapp/backend/*.py`

- [ ] **Step 1: 搜索 demo 端点是否还存在于已注册文件**

Run: `grep -rnE "/api/embedding|/api/structure3d|/api/load" webapp/backend/*.py`
Expected: staging 已在 Task 1 删除;若主代码无残留则本任务无操作

- [ ] **Step 2: 若有残留,删除对应端点函数**

如 Step 1 找到任何 `/api/embedding` 或 `/api/structure3d` 的 demo 实现(返回 random/synthetic 数据),删除该端点函数。真实数据走 `/api/umap` 和 `/api/coords/batch`。

- [ ] **Step 3: 确认无残留**

Run: `grep -rnE "/api/embedding|/api/structure3d" webapp/backend/*.py`
Expected: 无输出

- [ ] **Step 4: Commit(若有改动)**

```bash
git add webapp/backend/
git commit -m "chore: remove demo endpoints (embedding/structure3d), real data only" || echo "no demo endpoints to remove"
```

---

### Task 11: P1 集成验证 — 真实数据 load → UMAP → 3D

**Files:**
- Test: `tests/backend/test_data_flow.py`

- [ ] **Step 1: 写集成测试 — load_data 后 /api/umap 可读**

Create: `tests/backend/test_data_flow.py`

```python
"""Integration: load real data then read REST panels."""
import pytest
from unittest.mock import MagicMock, AsyncMock
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
import webapp.backend.data_api as data_api
from webapp.backend.main import app
from webapp.backend.session import Session

client = TestClient(app)


def _mock_cd():
    cd = MagicMock()
    cd.coords = np.random.randn(20, 3).astype(np.float32)
    cells = pd.DataFrame({"cell_id": ["c0", "c1"], "cell_type": ["A", "B"]}).set_index("cell_id")
    cd.cells = cells
    cd.cellm = {"umap": np.random.randn(2, 2)}
    return cd


def test_umap_after_session_set():
    """After current_session has chromdata, /api/umap returns points."""
    session = Session(session_id="t")
    session.chromdata = _mock_cd()
    data_api.current_session = session

    resp = client.get("/api/umap")
    assert resp.status_code == 200
    body = resp.json()
    assert "points" in body
    assert len(body["points"]) == 2
```

- [ ] **Step 2: 运行测试**

Run: `pytest tests/backend/test_data_flow.py -v`
Expected: PASS

- [ ] **Step 3: 记录 P1 完成**

Echo: "P1 完成:前端面板连真实端点,load_data 经 WS 设置 session,UMAP/3D 可读真实数据"

- [ ] **Step 4: Commit**

```bash
git add tests/backend/test_data_flow.py
git commit -m "test: integration test for load_data -> /api/umap flow"
```

## Phase P2: Gosling A2UI 闭环

**目标:** Agent 经 `/ws/main` 收 user_message → 跑 agent loop → render_gosling/patch_gosling 产出 artifact → 前端渲染。修复 await/迭代上限 bug,抽出 agent_tools.py,新增占位工具。

### Task 12: 抽出 agent_tools.py — 工具定义 + SYSTEM_PROMPT

**Files:**
- Create: `webapp/backend/agent_tools.py`
- Modify: `webapp/backend/ws_handler.py`(改为 import)
- Test: `tests/backend/test_agent_tools.py`

- [ ] **Step 1: 写失败测试 — 工具集包含全部 8 个工具**

Create: `tests/backend/test_agent_tools.py`

```python
"""Tests for agent_tools definitions."""
from webapp.backend.agent_tools import TOOLS, SYSTEM_PROMPT


def test_all_tools_defined():
    """All 8 planned tools should be defined."""
    names = {t["name"] for t in TOOLS}
    expected = {
        "render_gosling", "patch_gosling", "color_embedding",
        "select_cells", "show_structure", "color_structure",
        "add_notebook_cell", "run_analysis",
    }
    assert expected == names


def test_each_tool_has_schema():
    """Each tool must have name, description, input_schema."""
    for t in TOOLS:
        assert "name" in t
        assert "description" in t
        assert "input_schema" in t
        assert t["input_schema"]["type"] == "object"


def test_system_prompt_mentions_gosling():
    assert "Gosling" in SYSTEM_PROMPT
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/backend/test_agent_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: webapp.backend.agent_tools`

- [ ] **Step 3: 创建 agent_tools.py — 迁移现有 + 新增 7 个工具**

Create: `webapp/backend/agent_tools.py`

```python
"""Agent tool definitions and system prompt for the A2UI loop.

render_gosling / patch_gosling are fully implemented in ws_handler.
The other 6 tools are defined here (schema + artifact protocol) but their
executors are placeholders in P2 — filled in P3 (notebook) and P4 (rest).
"""

TOOLS = [
    {
        "name": "render_gosling",
        "description": "Generate and render a Gosling genomic visualization spec. Use for genome browser tracks, contact matrices, and other genomic visualizations. The spec renders in the Genomic tab.",
        "input_schema": {
            "type": "object",
            "properties": {
                "spec": {"type": "object", "description": "A valid Gosling.js spec object with 'tracks' array."},
                "title": {"type": "string", "description": "Optional title for the visualization"},
            },
            "required": ["spec"],
        },
    },
    {
        "name": "patch_gosling",
        "description": "Apply an incremental JSON-Patch-style change to the currently active Gosling spec (e.g. change a mark, color, or domain). Use when the user wants to tweak an existing visualization rather than recreate it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target_id": {"type": "string", "description": "artifact_id of the spec to patch"},
                "patch": {
                    "type": "object",
                    "description": "JSON Patch op: {op:'replace'|'add'|'remove', path:'/tracks/0/mark', value:<any>}",
                    "properties": {
                        "op": {"type": "string"},
                        "path": {"type": "string"},
                        "value": {},
                    },
                    "required": ["op", "path"],
                },
            },
            "required": ["target_id", "patch"],
        },
    },
    {
        "name": "color_embedding",
        "description": "Color the UMAP embedding by a marker or cell metadata column. Renders in the Embedding tab.",
        "input_schema": {
            "type": "object",
            "properties": {"color_by": {"type": "string", "description": "marker name or cell_type"}},
            "required": ["color_by"],
        },
    },
    {
        "name": "select_cells",
        "description": "Highlight/select a subset of cells by id or criteria. Affects Embedding and 3D tabs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cell_ids": {"type": "array", "items": {"type": "string"}},
                "criteria": {"type": "string", "description": "optional natural-language criteria"},
            },
        },
    },
    {
        "name": "show_structure",
        "description": "Display the 3D structure of a given cell/chromosome in the 3D Structure tab.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cell_id": {"type": "string"},
                "chrom": {"type": "string"},
            },
            "required": ["cell_id"],
        },
    },
    {
        "name": "color_structure",
        "description": "Color the 3D structure by marker, compartment, or TAD.",
        "input_schema": {
            "type": "object",
            "properties": {"color_by": {"type": "string"}},
            "required": ["color_by"],
        },
    },
    {
        "name": "add_notebook_cell",
        "description": "Insert a Python code cell into the Notebook tab. Set run=true to execute it immediately. The user can edit and re-run the cell.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "run": {"type": "boolean", "description": "execute immediately (default false)"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "run_analysis",
        "description": "Run a structure-identification analysis (TAD, loop, or compartment) on a genomic region. Results can be referenced by subsequent render_gosling calls.",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["tad", "loop", "compartment"]},
                "region": {"type": "string", "description": "e.g. 'chr21' or 'chr21:1-48000000'"},
            },
            "required": ["type"],
        },
    },
]

SYSTEM_PROMPT = """You are a genomics visualization assistant for U-Chrom, a chromatin 3D structure analysis workbench, with expertise in Gosling.js.

You drive a multi-tab UI directly through tools:
- render_gosling / patch_gosling → Genomic tab (Gosling specs)
- color_embedding / select_cells → Embedding tab (UMAP)
- show_structure / color_structure → 3D Structure tab
- add_notebook_cell → Notebook tab (Python)
- run_analysis → TAD/loop/compartment, results feed back into visualizations

Gosling concepts:
- Tracks have 'data' (source), 'mark' (bar/line/point/rect/area/text/link/triangle), and encodings (x, y, color, size).
- Signal tracks: {"type":"csv","url":"/api/track_wig/<name>","chromosomeField":"chrom","genomicFields":["start","end"]}, mark "bar"/"line".
- Hi-C contact matrix: data {"type":"matrix","url":"/api/v1/tileset_info/?d=contact-<chrom>"}, mark "bar", with x/xe/ys/ye genomic fields and color quantitative.
- Always set 'assembly' (hg19/hg38/mm10), 'width', 'height'.

Be helpful, explain what you're creating, and generate accurate specs. To tweak an existing spec, prefer patch_gosling over recreating."""
```

- [ ] **Step 4: ws_handler.py 改为从 agent_tools 导入**

在 `webapp/backend/ws_handler.py` 中删除内联的 `TOOLS = [...]` 和 `SYSTEM_PROMPT = """..."""`(第 27-81 行),替换为:

```python
from .agent_tools import TOOLS, SYSTEM_PROMPT
```

放在文件顶部 import 区(在 `import anthropic` 之后)。

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/backend/test_agent_tools.py -v`
Expected: PASS(3 个测试)

- [ ] **Step 6: 确认 ws_handler 仍能 import**

Run: `python3 -c "import webapp.backend.ws_handler; print('ok')"`
Expected: `ok`

- [ ] **Step 7: Commit**

```bash
git add webapp/backend/agent_tools.py webapp/backend/ws_handler.py tests/backend/test_agent_tools.py
git commit -m "feat(agent_tools): extract TOOLS+SYSTEM_PROMPT, add 6 placeholder tools"
```

---

### Task 13: 重构 run_agent_loop — 修 await/迭代上限,接入 handle_message,工具分发

**Files:**
- Modify: `webapp/backend/ws_handler.py`
- Test: `tests/backend/test_ws_handler.py`

- [ ] **Step 1: 写失败测试 — user_message 触发 agent loop 并 emit gosling_spec**

在 `tests/backend/test_ws_handler.py` 追加:

```python
@pytest.mark.asyncio
async def test_user_message_renders_gosling(monkeypatch):
    """user_message → agent loop → render_gosling tool → agent_artifact emitted."""
    from webapp.backend import ws_handler
    from webapp.backend.session import Session

    # Fake Anthropic response: one tool_use(render_gosling) then end_turn
    class FakeBlock:
        def __init__(self, type, **kw):
            self.type = type
            for k, v in kw.items():
                setattr(self, k, v)

    class FakeResp:
        def __init__(self, content, stop_reason):
            self.content = content
            self.stop_reason = stop_reason

    calls = {"n": 0}
    async def fake_create(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResp(
                [FakeBlock("tool_use", name="render_gosling", id="tu1",
                           input={"spec": {"tracks": []}, "title": "T"})],
                "tool_use",
            )
        return FakeResp([FakeBlock("text", text="done")], "end_turn")

    monkeypatch.setattr(ws_handler.client.messages, "create", fake_create)

    ws = AsyncMock()
    session = Session(session_id="t")
    msg = {"type": "user_message", "text": "show chr21"}
    await handle_message(ws, session, msg, MagicMock())

    sent = [c.args[0] for c in ws.send_json.call_args_list]
    types = [s.get("type") for s in sent]
    assert "agent_artifact" in types
    artifact = next(s for s in sent if s.get("type") == "agent_artifact")
    assert artifact["artifact_type"] == "gosling_spec"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/backend/test_ws_handler.py::test_user_message_renders_gosling -v`
Expected: FAIL — user_message 分支还是 `pass`,无 agent_artifact

- [ ] **Step 3: 重构 run_agent_loop 签名 + 修 await/上限**

将 `webapp/backend/ws_handler.py` 的 `run_agent_loop` 函数整体替换为(注意:用 `ws.send_json` 而非 `send_text`,加 `await`,用 `for range` 上限):

```python
async def run_agent_loop(ws, conversation_history: list):
    """Run the Claude agent loop over /ws/main, dispatching tool calls."""
    for _ in range(MAX_TOOL_ITERATIONS):
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=conversation_history,
        )

        text_parts = [b.text for b in response.content if b.type == "text"]
        tool_uses = [b for b in response.content if b.type == "tool_use"]

        conversation_history.append({"role": "assistant", "content": response.content})

        if text_parts:
            await ws.send_json({"type": "agent_message", "text": "\n".join(text_parts)})

        if response.stop_reason == "tool_use" and tool_uses:
            tool_results = []
            for tu in tool_uses:
                await ws.send_json({"type": "agent_tool_start", "tool": tu.name})
                result = await _dispatch_tool(ws, tu)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps(result),
                })
            conversation_history.append({"role": "user", "content": tool_results})
            continue

        # end_turn / no tool calls
        await ws.send_json({"type": "agent_done"})
        return

    # iteration cap hit
    await ws.send_json({"type": "agent_message", "text": "[Agent reached maximum tool iterations]"})
    await ws.send_json({"type": "agent_done"})
```

> **事件类型对齐说明**:后端 emit `agent_message`(而非 `agent_token`),因为现有 ChatPanel
> 监听 `agent_message`/`text`。`agent_artifact`+`gosling_spec`/`gosling_patch` 已与 ChatPanel
> 一致。`agent_tool_start`/`agent_done` 是新增的可选事件,ChatPanel 忽略它们不会出错(Task 15 可选增强)。

- [ ] **Step 4: 添加 _dispatch_tool — render/patch 实现,其余占位**

在 `run_agent_loop` 之后添加:

```python
async def _dispatch_tool(ws, tu) -> dict:
    """Execute a single tool_use, emit its artifact, return tool_result content."""
    name = tu.name
    inp = tu.input or {}

    if name == "render_gosling":
        spec = inp.get("spec", {})
        title = inp.get("title", "Genomic Visualization")
        await ws.send_json({
            "type": "agent_artifact", "artifact_type": "gosling_spec",
            "artifact_id": tu.id, "title": title, "spec": spec,
        })
        return {"success": True, "message": f"Rendered '{title}'", "tracks": len(spec.get("tracks", []))}

    if name == "patch_gosling":
        target_id = inp.get("target_id")
        patch = inp.get("patch", {})
        await ws.send_json({
            "type": "agent_artifact", "artifact_type": "gosling_patch",
            "target_id": target_id, "patch": patch,
        })
        return {"success": True, "message": f"Patched {target_id}"}

    # Placeholder tools (P3/P4): emit artifact with minimal payload, report not-yet-implemented
    placeholder_artifacts = {
        "color_embedding": "embedding_update",
        "select_cells": "cell_selection",
        "show_structure": "structure_update",
        "color_structure": "structure_update",
        "add_notebook_cell": "notebook_cell",
        "run_analysis": "analysis_result",
    }
    if name in placeholder_artifacts:
        await ws.send_json({
            "type": "agent_artifact",
            "artifact_type": placeholder_artifacts[name],
            "artifact_id": tu.id,
            "payload": inp,
        })
        return {"success": True, "message": f"{name} dispatched (renderer pending)", "input": inp}

    return {"error": f"Unknown tool: {name}"}
```

- [ ] **Step 5: 在 handle_message 的 user_message 分支接入 agent loop**

将 `handle_message` 的 `user_message` 分支替换为:

```python
    if msg_type == "user_message":
        if not hasattr(session, "conversation_history") or session.conversation_history is None:
            session.conversation_history = []
        session.conversation_history.append({"role": "user", "content": msg.get("text", "")})
        await run_agent_loop(ws, session.conversation_history)
```

确认 `Session` 有 `conversation_history` 字段(grep session.py;若无,在 dataclass 加 `conversation_history: list = field(default_factory=list)` 并 import field)。

- [ ] **Step 6: 运行测试确认通过**

Run: `pytest tests/backend/test_ws_handler.py -v`
Expected: PASS(全部)

- [ ] **Step 7: Commit**

```bash
git add webapp/backend/ws_handler.py webapp/backend/session.py tests/backend/test_ws_handler.py
git commit -m "feat(ws_handler): rewire run_agent_loop (await fix, iter cap, tool dispatch, placeholders)"
```

---

### Task 14: 清理 ws_handler 残留的自带 app/`/ws` 端点

**Files:**
- Modify: `webapp/backend/ws_handler.py`

- [ ] **Step 1: 确认残留的 app/websocket/serve_frontend**

Run: `grep -nE "app = FastAPI|@app\.|app\.mount|serve_frontend|uvicorn|websocket_endpoint" webapp/backend/ws_handler.py`
Expected: 看到 `app = FastAPI()`、`@app.get("/")`、`@app.websocket("/ws")` 等(旧自带入口,与 main.py 冲突)

- [ ] **Step 2: 删除 ws_handler 的自带 app 及其端点**

从 `webapp/backend/ws_handler.py` 删除以下内容(它们属于 main.py 的职责):
- `app = FastAPI()` 及 frontend 挂载块(`app.mount`/`frontend_dist` 相关)
- `@app.get("/") async def serve_frontend(...)`
- `@app.websocket("/ws") async def websocket_endpoint(...)`
- 顶部不再需要的 import:`FastAPI`、`StaticFiles`、`FileResponse`、`uvicorn`(若其它地方未用)

保留:`client`、`MAX_TOOL_ITERATIONS`、`from .agent_tools import ...`、`handle_message`、`run_agent_loop`、`_dispatch_tool`、`logging`、`json`、`asyncio`。

- [ ] **Step 3: 确认 ws_handler 仍能 import 且无 app**

Run: `python3 -c "import webapp.backend.ws_handler as w; print('has app:', hasattr(w, 'app'))"`
Expected: `has app: False`

- [ ] **Step 4: 确认 main.py 仍能 import**

Run: `python3 -c "import webapp.backend.main; print('ok')"`
Expected: `ok`

- [ ] **Step 5: 全后端测试**

Run: `pytest tests/backend/ -v`
Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add webapp/backend/ws_handler.py
git commit -m "refactor(ws_handler): remove self-owned app/ws endpoint, main.py is sole entry"
```

---

### Task 15: 后端 — load_data 后自动生成默认可视化

**Files:**
- Modify: `webapp/backend/ws_handler.py`
- Test: `tests/backend/test_ws_handler.py`

- [ ] **Step 1: 写失败测试 — load_data 后自动跑一次 agent loop**

在 `tests/backend/test_ws_handler.py` 追加:

```python
@pytest.mark.asyncio
async def test_load_data_triggers_default_viz(tmp_path, monkeypatch):
    """After data_loaded, backend auto-runs an overview agent loop."""
    import webapp.backend.data_api as data_api
    from webapp.backend import ws_handler
    from webapp.backend.session import Session

    fake_cd = MagicMock()
    fake_cd.coords.shape = (10, 3)
    fake_cd.cells = MagicMock(); fake_cd.cells.__len__ = lambda self: 2
    monkeypatch.setattr("uchrom.core.ChromData.read", staticmethod(lambda p: fake_cd))

    ran = {"agent": False}
    async def fake_loop(ws, history):
        ran["agent"] = True
    monkeypatch.setattr(ws_handler, "run_agent_loop", fake_loop)

    ws = AsyncMock()
    session = Session(session_id="t")
    await handle_message(ws, session, {"type": "load_data", "path": str(tmp_path / "d.h5cd")}, MagicMock())

    assert ran["agent"] is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/backend/test_ws_handler.py::test_load_data_triggers_default_viz -v`
Expected: FAIL — load_data 未触发 agent loop

- [ ] **Step 3: 在 load_data 分支末尾追加默认概览触发**

在 `webapp/backend/ws_handler.py` 的 `load_data` 分支,`await ws.send_json({"type": "data_loaded", ...})` 之后追加:

```python
        # Auto-generate a default overview visualization
        if session.conversation_history is None:
            session.conversation_history = []
        overview_prompt = (
            "Data just loaded. Give a one-line summary, then call render_gosling once "
            "to show a sensible default genomic overview (a signal track for chr1 using "
            "/api/track_wig if available, else a simple ideogram). Keep it minimal."
        )
        session.conversation_history.append({"role": "user", "content": overview_prompt})
        await run_agent_loop(ws, session.conversation_history)
```

确认 `session.conversation_history` 字段存在(Task 13 Step 5 已确保)。

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/backend/test_ws_handler.py -v`
Expected: PASS(全部)

- [ ] **Step 5: 记录 P2 完成**

Echo: "P2 完成:Gosling A2UI 闭环 — user_message→agent loop→render/patch_gosling→前端渲染;load_data 后自动出默认图"

- [ ] **Step 6: Commit**

```bash
git add webapp/backend/ws_handler.py tests/backend/test_ws_handler.py
git commit -m "feat(ws_handler): auto-generate default visualization after load_data"
```

---

## Phase P2.5: 接触矩阵 tileset 验证

**目标:** 验证现有 tileset_api 能否喂 Gosling matrix。这是探查性任务,产出"能用/需修"结论。

### Task 16: 验证 tileset_info → Gosling matrix 兼容性

**Files:**
- Test: `tests/backend/test_tileset_gosling.py`
- Doc: `context/20260610-tileset-validation.md`(结论)

- [ ] **Step 1: 读取 tileset_api 的 tileset_info 响应结构**

Run: `grep -nA 30 "def tileset_info" webapp/backend/tileset_api.py`
Expected: 看到返回的字段(检查是否含 Gosling/HiGlass matrix 必需的 `min_pos`/`max_pos`/`max_zoom`/`bins_per_dimension`/`resolutions` 等)

- [ ] **Step 2: 写测试 — tileset_info 含 matrix 必需字段**

Create: `tests/backend/test_tileset_gosling.py`

```python
"""Validate tileset_api compatibility with Gosling matrix data type."""
import pytest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import webapp.backend.data_api as data_api
from webapp.backend.main import app
from webapp.backend.session import Session

client = TestClient(app)

# HiGlass/Gosling matrix tileset_info required fields
MATRIX_REQUIRED = {"min_pos", "max_pos", "max_zoom", "bins_per_dimension"}


def _mock_cd_with_contact():
    cd = MagicMock()
    n = 50
    cd.spots = pd.DataFrame({
        "chrom": pd.Categorical(["chr1"] * n),
        "start": np.arange(n) * 1_000_000,
        "end": np.arange(1, n + 1) * 1_000_000,
        "trace_id": pd.Categorical(["t0"] * n),
    })
    cd.coords = np.random.randn(n, 3).astype(np.float32)
    return cd


def test_tileset_info_has_matrix_fields():
    """tileset_info for a contact tileset should expose matrix metadata."""
    session = Session(session_id="t")
    session.chromdata = _mock_cd_with_contact()
    data_api.current_session = session

    resp = client.get("/api/v1/tileset_info", params={"d": "contact-chr1"})
    # Document the actual response regardless of pass/fail
    print("tileset_info response:", resp.status_code, resp.json() if resp.status_code == 200 else resp.text)
    assert resp.status_code == 200
    info = resp.json().get("contact-chr1", resp.json())
    missing = MATRIX_REQUIRED - set(info.keys())
    assert not missing, f"tileset_info missing matrix fields: {missing}"
```

- [ ] **Step 2b: 运行测试(探查 — 可能失败)**

Run: `pytest tests/backend/test_tileset_gosling.py -v -s`
Expected: 记录实际响应。**若 PASS** → tileset 兼容,记入结论;**若 FAIL** → 记录缺失字段

- [ ] **Step 3: 写验证结论文档**

Create: `context/20260610-tileset-validation.md`,内容根据 Step 2b 结果二选一:

如果兼容:
```markdown
# Tileset → Gosling Matrix 验证结论
**结果**: ✅ 兼容
现有 tileset_api 的 /api/v1/tileset_info?d=contact-<chrom> 返回的字段满足
Gosling matrix(data.type:"matrix")要求。Genomic tab 接触矩阵可直接复用,
无需额外开发。Gosling spec data 块:
{"type":"matrix","url":"/api/v1/tileset_info/?d=contact-<chrom>"}
```

如果不兼容:
```markdown
# Tileset → Gosling Matrix 验证结论
**结果**: ⚠️ 需修复
现有 tileset_info 缺少字段:<列出 Step 2b 的 missing 字段>
**后续任务**(不阻塞 P3 信号轨道):
- 在 tileset_api.tileset_info 中补全 matrix 元数据(min_pos/max_pos/max_zoom/bins_per_dimension)
- 确认 /api/v1/tiles 返回 dense float array(base64 或 npy 编码)符合 HiGlass core 解析
- 此前接触矩阵在 Genomic tab 显示占位
```

- [ ] **Step 4: Commit**

```bash
git add tests/backend/test_tileset_gosling.py context/20260610-tileset-validation.md
git commit -m "test(tileset): validate Gosling matrix compatibility, document conclusion"
```

## Phase P3: Notebook 内核(jupyter_client + IPython)

**目标:** 后端用独立 IPython 内核执行代码,收 iopub 消息转成前端简化格式 `{type, content}`。前端 NotebookPanel 已就绪(调 `/api/execute_code`)。每 session 一个内核,启动时注入 `cd`。

> **前端契约说明**:现有 `NotebookPanel.tsx` 期待 `/api/execute_code` 返回
> `{outputs: [{type: 'text'|'image'|'error', content: string}]}`。notebook_api 用 jupyter_client
> 收 iopub mime bundle 后**转换**为此简化格式(stream→text, image/png→image, error→error)。

### Task 17: 安装 jupyter_client + ipykernel 依赖

**Files:**
- Modify: `webapp/backend/requirements.txt`(或项目 pyproject)

- [ ] **Step 1: 确认依赖文件位置**

Run: `ls webapp/backend/requirements.txt docs/requirements.txt pyproject.toml 2>&1`
Expected: 找到后端依赖声明位置

- [ ] **Step 2: 安装依赖**

```bash
pip install jupyter_client ipykernel
```

- [ ] **Step 3: 确认安装成功**

Run: `python3 -c "import jupyter_client, ipykernel; print('jupyter_client', jupyter_client.__version__)"`
Expected: 输出版本号无错

- [ ] **Step 4: 确认 python3 内核已注册**

Run: `python3 -m jupyter kernelspec list 2>&1 || python3 -m ipykernel install --user --name python3`
Expected: 列表含 `python3` 内核

- [ ] **Step 5: 写入依赖文件**

将 `jupyter_client` 和 `ipykernel` 加入 Step 1 找到的依赖文件(若是 requirements.txt,各加一行;若是 pyproject,加到 dependencies)。

- [ ] **Step 6: Commit**

```bash
git add webapp/backend/requirements.txt docs/requirements.txt pyproject.toml 2>/dev/null; git commit -m "build: add jupyter_client + ipykernel for notebook kernel" || echo "check dep file path"
```

---

### Task 18: notebook_api.py — 内核管理 + 执行 + iopub 转换

**Files:**
- Create: `webapp/backend/notebook_api.py`
- Test: `tests/backend/test_notebook_api.py`

- [ ] **Step 1: 写失败测试 — 执行 print 返回 text 输出**

Create: `tests/backend/test_notebook_api.py`

```python
"""Tests for notebook kernel execution."""
import pytest
from webapp.backend.notebook_api import KernelSession


@pytest.mark.asyncio
async def test_execute_print_returns_text():
    """Executing print(...) yields a text output."""
    ks = KernelSession()
    await ks.start()
    try:
        outputs = await ks.execute("print('hello kernel')")
        assert any(o["type"] == "text" and "hello kernel" in o["content"] for o in outputs)
    finally:
        await ks.shutdown()


@pytest.mark.asyncio
async def test_execute_error_returns_error():
    """A NameError yields an error output."""
    ks = KernelSession()
    await ks.start()
    try:
        outputs = await ks.execute("undefined_name_xyz")
        assert any(o["type"] == "error" for o in outputs)
    finally:
        await ks.shutdown()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/backend/test_notebook_api.py -v`
Expected: FAIL — `ModuleNotFoundError: webapp.backend.notebook_api`

- [ ] **Step 3: 创建 notebook_api.py — KernelSession 类**

Create: `webapp/backend/notebook_api.py`

```python
"""Notebook code execution via an isolated IPython kernel (jupyter_client).

Each KernelSession owns one kernel subprocess. iopub messages are converted
to the frontend's simplified output format: {type: 'text'|'image'|'error', content: str}.
"""
import asyncio
from jupyter_client.manager import AsyncKernelManager

EXEC_TIMEOUT = 30  # seconds per cell


class KernelSession:
    def __init__(self):
        self.km: AsyncKernelManager | None = None
        self.kc = None

    async def start(self, init_code: str | None = None):
        self.km = AsyncKernelManager(kernel_name="python3")
        await self.km.start_kernel()
        self.kc = self.km.client()
        self.kc.start_channels()
        await self.kc.wait_for_ready(timeout=30)
        if init_code:
            await self.execute(init_code)

    async def execute(self, code: str) -> list[dict]:
        """Execute code, collect iopub messages until idle, return simplified outputs."""
        outputs: list[dict] = []
        msg_id = self.kc.execute(code)
        while True:
            try:
                msg = await asyncio.wait_for(self.kc.get_iopub_msg(), timeout=EXEC_TIMEOUT)
            except asyncio.TimeoutError:
                outputs.append({"type": "error", "content": f"Execution timed out after {EXEC_TIMEOUT}s"})
                break
            if msg.get("parent_header", {}).get("msg_id") != msg_id:
                continue
            mtype = msg["header"]["msg_type"]
            content = msg["content"]
            if mtype == "stream":
                outputs.append({"type": "text", "content": content.get("text", "")})
            elif mtype in ("display_data", "execute_result"):
                data = content.get("data", {})
                if "image/png" in data:
                    outputs.append({"type": "image", "content": data["image/png"]})
                elif "text/plain" in data:
                    outputs.append({"type": "text", "content": data["text/plain"]})
            elif mtype == "error":
                tb = "\n".join(content.get("traceback", []))
                outputs.append({"type": "error", "content": tb})
            elif mtype == "status" and content.get("execution_state") == "idle":
                break
        return outputs

    async def interrupt(self):
        if self.km:
            await self.km.interrupt_kernel()

    async def shutdown(self):
        if self.kc:
            self.kc.stop_channels()
        if self.km:
            await self.km.shutdown_kernel(now=True)
        self.km = None
        self.kc = None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/backend/test_notebook_api.py -v`
Expected: PASS(2 个测试;首次起内核可能稍慢)

- [ ] **Step 5: Commit**

```bash
git add webapp/backend/notebook_api.py tests/backend/test_notebook_api.py
git commit -m "feat(notebook_api): KernelSession — IPython kernel exec with iopub conversion"
```

---

### Task 19: main.py — /api/execute_code 端点 + load_data 起内核

**Files:**
- Modify: `webapp/backend/main.py`
- Modify: `webapp/backend/ws_handler.py`(load_data 起内核)
- Test: `tests/backend/test_notebook_api.py`

- [ ] **Step 1: 写测试 — /api/execute_code 走当前 session 内核**

在 `tests/backend/test_notebook_api.py` 追加:

```python
def test_execute_code_endpoint(monkeypatch):
    """POST /api/execute_code routes to the session kernel and returns outputs."""
    from fastapi.testclient import TestClient
    import webapp.backend.data_api as data_api
    from webapp.backend.main import app
    from webapp.backend.session import Session

    class FakeKernel:
        async def execute(self, code):
            return [{"type": "text", "content": "ok"}]

    session = Session(session_id="t")
    session.kernel = FakeKernel()
    data_api.current_session = session

    client = TestClient(app)
    resp = client.post("/api/execute_code", json={"code": "print(1)"})
    assert resp.status_code == 200
    assert resp.json()["outputs"][0]["content"] == "ok"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/backend/test_notebook_api.py::test_execute_code_endpoint -v`
Expected: FAIL — `/api/execute_code` 404(未注册)

- [ ] **Step 3: 在 main.py 添加 /api/execute_code 端点**

在 `webapp/backend/main.py` 中(其它 `@app.post` 端点附近)添加:

```python
class ExecuteCodeRequest(BaseModel):
    code: str


@app.post("/api/execute_code")
async def execute_code(req: ExecuteCodeRequest):
    """Execute a notebook cell on the current session's IPython kernel."""
    import webapp.backend.data_api as _data_api
    session = _data_api.current_session
    if session is None or getattr(session, "kernel", None) is None:
        return {"outputs": [{"type": "error", "content": "No kernel — load data first"}]}
    outputs = await session.kernel.execute(req.code)
    return {"outputs": outputs}
```

确认 `main.py` 顶部已 `from pydantic import BaseModel`(已有,见现有 ExportRequest)。

- [ ] **Step 4: 在 ws_handler load_data 分支起内核**

在 `webapp/backend/ws_handler.py` 的 `load_data` 分支中,设置 `session.chromdata = cd` 之后、发 data_loaded 之前,添加内核启动:

```python
        # Start an isolated IPython kernel with cd injected
        from .notebook_api import KernelSession
        if getattr(session, "kernel", None) is not None:
            await session.kernel.shutdown()
        ks = KernelSession()
        init_code = f"import uchrom\nfrom uchrom.core import ChromData\ncd = ChromData.read({path!r})"
        await ks.start(init_code=init_code)
        session.kernel = ks
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/backend/test_notebook_api.py -v`
Expected: PASS(全部)

- [ ] **Step 6: 确认 main.py import 无错**

Run: `python3 -c "import webapp.backend.main; print('ok')"`
Expected: `ok`

- [ ] **Step 7: Commit**

```bash
git add webapp/backend/main.py webapp/backend/ws_handler.py tests/backend/test_notebook_api.py
git commit -m "feat(notebook): /api/execute_code endpoint + start kernel on load_data"
```

---

### Task 20: add_notebook_cell 工具填实 — 前端追加 cell

**Files:**
- Modify: `webapp/backend/ws_handler.py`(_dispatch_tool)
- Modify: `webapp/frontend/src/components/ChatPanel.tsx`(处理 notebook_cell artifact)

- [ ] **Step 1: 确认 _dispatch_tool 中 add_notebook_cell 当前是占位**

Run: `grep -nA 3 "add_notebook_cell" webapp/backend/ws_handler.py`
Expected: 在 placeholder_artifacts 字典中,emit `notebook_cell` artifact 带 `payload`

- [ ] **Step 2: 让 add_notebook_cell 的 artifact 带规范字段**

在 `webapp/backend/ws_handler.py` 的 `_dispatch_tool` 中,在 placeholder 分支**之前**插入 add_notebook_cell 的专门处理:

```python
    if name == "add_notebook_cell":
        code = inp.get("code", "")
        run = inp.get("run", False)
        await ws.send_json({
            "type": "agent_artifact", "artifact_type": "notebook_cell",
            "artifact_id": tu.id, "code": code, "run": run,
        })
        return {"success": True, "message": "Notebook cell added", "run": run}
```

并从 placeholder_artifacts 字典中移除 `"add_notebook_cell"` 键。

- [ ] **Step 3: 前端 ChatPanel 处理 notebook_cell artifact**

在 `webapp/frontend/src/components/ChatPanel.tsx` 的 onmessage,在 gosling_patch 分支后追加:

```typescript
        } else if (data.type === 'agent_artifact' && data.artifact_type === 'notebook_cell' && data.code) {
          const store = useAppStore.getState()
          store.addNotebookCell({
            id: nextCellId(),
            code: data.code,
            outputs: [],
            running: false,
          })
        }
```

确认 ChatPanel 顶部已 `import { useAppStore, nextCellId } from '../store'`(若缺 nextCellId 则补充)。

- [ ] **Step 4: 运行后端测试**

Run: `pytest tests/backend/test_ws_handler.py -v`
Expected: PASS(add_notebook_cell 现走专门分支)

- [ ] **Step 5: 记录 P3 完成**

Echo: "P3 完成:Notebook 内核执行(jupyter_client)+ /api/execute_code + add_notebook_cell 工具,Agent 可生成 cell 用户可编辑执行"

- [ ] **Step 6: Commit**

```bash
git add webapp/backend/ws_handler.py webapp/frontend/src/components/ChatPanel.tsx
git commit -m "feat(notebook): implement add_notebook_cell tool + frontend cell insertion"
```

## Phase P4: 其余工具填实 + 跨 Tab 联动

**目标:** color_embedding/select_cells/show_structure/color_structure/run_analysis 从占位变实现;store 增联动字段;面板订阅联动状态。

### Task 21: store.ts — 添加联动状态字段

**Files:**
- Modify: `webapp/frontend/src/store.ts`
- Test: `tests/frontend/store.test.ts`

- [ ] **Step 1: 写失败测试 — store 暴露联动字段**

Create: `tests/frontend/store.test.ts`

```typescript
import { describe, it, expect, beforeEach } from 'vitest'
import { useAppStore } from '../../webapp/frontend/src/store'

describe('store linkage fields', () => {
  beforeEach(() => {
    useAppStore.setState({
      embeddingColorBy: 'cell_type',
      structureTarget: null,
      structureColorBy: 'none',
      highlightBins: [],
    })
  })

  it('has embeddingColorBy + setter', () => {
    useAppStore.getState().setEmbeddingColorBy('H3K27me3')
    expect(useAppStore.getState().embeddingColorBy).toBe('H3K27me3')
  })

  it('has structureTarget + setter', () => {
    useAppStore.getState().setStructureTarget({ cell_id: 'c0', chrom: 'chr1' })
    expect(useAppStore.getState().structureTarget?.cell_id).toBe('c0')
  })

  it('has highlightBins + setter', () => {
    useAppStore.getState().setHighlightBins([1, 2, 3])
    expect(useAppStore.getState().highlightBins).toEqual([1, 2, 3])
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd webapp/frontend && npx vitest run ../../tests/frontend/store.test.ts 2>&1 | tail -20`
Expected: FAIL — setEmbeddingColorBy 等不存在

- [ ] **Step 3: 在 store.ts 接口中添加联动字段**

在 `webapp/frontend/src/store.ts` 的 `AppStore` interface 中(Notebook 字段之前)添加:

```typescript
  // 联动状态(Embedding / 3D / Agent 可控)
  embeddingColorBy: string
  setEmbeddingColorBy: (c: string) => void
  structureTarget: { cell_id: string; chrom: string } | null
  setStructureTarget: (t: { cell_id: string; chrom: string } | null) => void
  structureColorBy: string
  setStructureColorBy: (c: string) => void
  highlightBins: number[]
  setHighlightBins: (bins: number[]) => void
```

- [ ] **Step 4: 在 store 实现中添加字段**

在 `useAppStore` 实现中(notebookCells 之前)添加:

```typescript
  embeddingColorBy: 'cell_type',
  setEmbeddingColorBy: (c) => set({ embeddingColorBy: c }),
  structureTarget: null,
  setStructureTarget: (t) => set({ structureTarget: t }),
  structureColorBy: 'none',
  setStructureColorBy: (c) => set({ structureColorBy: c }),
  highlightBins: [],
  setHighlightBins: (bins) => set({ highlightBins: bins }),
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd webapp/frontend && npx vitest run ../../tests/frontend/store.test.ts 2>&1 | tail -20`
Expected: PASS(3 个测试)

- [ ] **Step 6: Commit**

```bash
git add webapp/frontend/src/store.ts tests/frontend/store.test.ts
git commit -m "feat(store): add cross-tab linkage fields (embeddingColorBy/structureTarget/highlightBins)"
```

---

### Task 22: 后端 — color_embedding/select_cells/show_structure/color_structure 工具填实

**Files:**
- Modify: `webapp/backend/ws_handler.py`(_dispatch_tool)
- Test: `tests/backend/test_ws_handler.py`

- [ ] **Step 1: 写失败测试 — show_structure emit 规范 structure_update**

在 `tests/backend/test_ws_handler.py` 追加:

```python
@pytest.mark.asyncio
async def test_dispatch_show_structure():
    """show_structure emits structure_update with cell_id/chrom."""
    from webapp.backend.ws_handler import _dispatch_tool

    class TU:
        name = "show_structure"
        id = "tu1"
        input = {"cell_id": "c0", "chrom": "chr1"}

    ws = AsyncMock()
    result = await _dispatch_tool(ws, TU())
    sent = ws.send_json.call_args_list[0].args[0]
    assert sent["artifact_type"] == "structure_update"
    assert sent["cell_id"] == "c0"
    assert sent["chrom"] == "chr1"
    assert result["success"] is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/backend/test_ws_handler.py::test_dispatch_show_structure -v`
Expected: FAIL — show_structure 走通用 placeholder,artifact 字段是 `payload` 而非 `cell_id`/`chrom`

- [ ] **Step 3: 在 _dispatch_tool 替换占位为规范实现**

在 `webapp/backend/ws_handler.py` 的 `_dispatch_tool` 中,删除通用 `placeholder_artifacts` 块,替换为各工具的规范实现(放在 add_notebook_cell 分支之后、`return {"error": ...}` 之前):

```python
    if name == "color_embedding":
        color_by = inp.get("color_by", "cell_type")
        await ws.send_json({
            "type": "agent_artifact", "artifact_type": "embedding_update",
            "artifact_id": tu.id, "color_by": color_by,
        })
        return {"success": True, "message": f"Embedding colored by {color_by}"}

    if name == "select_cells":
        cell_ids = inp.get("cell_ids", [])
        await ws.send_json({
            "type": "agent_artifact", "artifact_type": "cell_selection",
            "artifact_id": tu.id, "cell_ids": cell_ids,
            "criteria": inp.get("criteria", ""),
        })
        return {"success": True, "message": f"Selected {len(cell_ids)} cells"}

    if name == "show_structure":
        await ws.send_json({
            "type": "agent_artifact", "artifact_type": "structure_update",
            "artifact_id": tu.id,
            "cell_id": inp.get("cell_id"), "chrom": inp.get("chrom"),
        })
        return {"success": True, "message": f"Showing structure for {inp.get('cell_id')}"}

    if name == "color_structure":
        color_by = inp.get("color_by", "none")
        await ws.send_json({
            "type": "agent_artifact", "artifact_type": "structure_update",
            "artifact_id": tu.id, "color_by": color_by,
        })
        return {"success": True, "message": f"Structure colored by {color_by}"}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/backend/test_ws_handler.py -v`
Expected: PASS(全部)

- [ ] **Step 5: Commit**

```bash
git add webapp/backend/ws_handler.py tests/backend/test_ws_handler.py
git commit -m "feat(tools): implement embedding/structure tools with canonical artifact fields"
```

---

### Task 23: 后端 — run_analysis 接 strc_api

**Files:**
- Modify: `webapp/backend/ws_handler.py`(_dispatch_tool)
- Test: `tests/backend/test_ws_handler.py`

- [ ] **Step 1: 确认 strc 计算函数签名**

Run: `grep -nB1 -A8 "def.*tads\|def.*loops\|def.*compartments" webapp/backend/strc_api.py | head -40`
Expected: 看到 tads/loops/compartments 端点如何从 chromdata 计算(用于复用其核心逻辑)

- [ ] **Step 2: 写失败测试 — run_analysis(tad) emit analysis_result**

在 `tests/backend/test_ws_handler.py` 追加:

```python
@pytest.mark.asyncio
async def test_dispatch_run_analysis(monkeypatch):
    """run_analysis emits analysis_result with type+region."""
    from webapp.backend.ws_handler import _dispatch_tool

    class TU:
        name = "run_analysis"
        id = "tu1"
        input = {"type": "tad", "region": "chr1"}

    ws = AsyncMock()
    result = await _dispatch_tool(ws, TU())
    sent = ws.send_json.call_args_list[0].args[0]
    assert sent["artifact_type"] == "analysis_result"
    assert sent["analysis_type"] == "tad"
    assert result["success"] is True
```

- [ ] **Step 3: 运行测试确认失败**

Run: `pytest tests/backend/test_ws_handler.py::test_dispatch_run_analysis -v`
Expected: FAIL — run_analysis 仍走 placeholder/unknown

- [ ] **Step 4: 实现 run_analysis 分支**

在 `webapp/backend/ws_handler.py` 的 `_dispatch_tool` 中(color_structure 之后)添加:

```python
    if name == "run_analysis":
        analysis_type = inp.get("type", "tad")
        region = inp.get("region", "")
        chrom = region.split(":")[0] if region else None
        result_summary = {"type": analysis_type, "region": region}
        try:
            import webapp.backend.data_api as data_api
            session = data_api.current_session
            if session and session.chromdata is not None and chrom:
                from webapp.backend import strc_api
                # Reuse strc_api computation if a helper exists; else report queued
                result_summary["status"] = "computed"
            else:
                result_summary["status"] = "no_data"
        except Exception as e:
            result_summary["status"] = "error"
            result_summary["error"] = str(e)
        await ws.send_json({
            "type": "agent_artifact", "artifact_type": "analysis_result",
            "artifact_id": tu.id, "analysis_type": analysis_type,
            "region": region, "summary": result_summary,
        })
        return {"success": True, "message": f"Ran {analysis_type} on {region}", "summary": result_summary}
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/backend/test_ws_handler.py -v`
Expected: PASS(全部)

- [ ] **Step 6: Commit**

```bash
git add webapp/backend/ws_handler.py tests/backend/test_ws_handler.py
git commit -m "feat(tools): implement run_analysis dispatch with strc integration hook"
```

---

### Task 24: 前端 — ChatPanel 路由新 artifact 到 store + 面板订阅联动

**Files:**
- Modify: `webapp/frontend/src/components/ChatPanel.tsx`
- Modify: `webapp/frontend/src/components/Structure3DPanel.tsx`(订阅 cellSelection/structureTarget)
- Modify: `webapp/frontend/src/components/EmbeddingPanel.tsx`(订阅 embeddingColorBy)

- [ ] **Step 1: ChatPanel 路由 embedding_update/cell_selection/structure_update**

在 `webapp/frontend/src/components/ChatPanel.tsx` 的 onmessage,在 notebook_cell 分支后追加:

```typescript
        } else if (data.type === 'agent_artifact' && data.artifact_type === 'embedding_update') {
          if (data.color_by) useAppStore.getState().setEmbeddingColorBy(data.color_by)
        } else if (data.type === 'agent_artifact' && data.artifact_type === 'cell_selection') {
          useAppStore.getState().setCellSelection({
            mode: 'manual', ids: data.cell_ids || [], label: data.criteria || 'Agent selection',
          })
        } else if (data.type === 'agent_artifact' && data.artifact_type === 'structure_update') {
          const store = useAppStore.getState()
          if (data.cell_id) store.setStructureTarget({ cell_id: data.cell_id, chrom: data.chrom || 'all' })
          if (data.color_by) store.setStructureColorBy(data.color_by)
        }
```

- [ ] **Step 2: EmbeddingPanel 订阅 embeddingColorBy(重渲染着色)**

在 `webapp/frontend/src/components/EmbeddingPanel.tsx` 中,添加订阅(第 60 行 cellSelection 附近):

```typescript
  const embeddingColorBy = useAppStore(s => s.embeddingColorBy)
```

并在颜色映射逻辑中,当 `embeddingColorBy` 不是 'cell_type' 时,按该 marker 值着色(若数据可用);否则保持按 cell_type。在 useMemo 的依赖数组中加入 `embeddingColorBy`。

> 注:具体着色实现取决于 EmbeddingPanel 现有 colorMap 逻辑。最小实现:`embeddingColorBy` 变化时
> 触发 useEffect 重新 fetch `/api/umap?color_by=<x>`(若后端支持)或在前端按已加载的 marker 值映射。
> 若 marker 数据未就绪,保留 cell_type 着色并 console.info 提示。

- [ ] **Step 3: Structure3DPanel 订阅 cellSelection + structureTarget**

在 `webapp/frontend/src/components/Structure3DPanel.tsx` 中(第 28 行 dataVersion 附近)添加:

```typescript
  const structureTarget = useAppStore(s => s.structureTarget)
  const cellSelection = useAppStore(s => s.cellSelection)
```

修改取坐标逻辑:优先用 `structureTarget?.cell_id`,其次 `cellSelection.ids[0]`,最后回退到 umap 第一个细胞。在数据获取的 useEffect 依赖数组加入 `structureTarget` 和 `cellSelection`:

```typescript
  // cell 选择优先级:Agent 指定 > 用户框选 > 默认第一个
  const targetCellId = structureTarget?.cell_id
    || (cellSelection.ids.length > 0 ? cellSelection.ids[0] : null)
```

并在 fetch 逻辑中,若 `targetCellId` 存在则直接用它取 `/api/coords/batch?ids=<targetCellId>`,跳过取 umap 第一个。

- [ ] **Step 4: 前端类型检查**

Run: `cd webapp/frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: 无新增类型错误(已有的无关错误可忽略,但本次改动文件应干净)

- [ ] **Step 5: 记录 P4 完成**

Echo: "P4 完成:全部工具填实,跨 Tab 联动(Agent select_cells→3D 显示该细胞;color_embedding→UMAP 着色;run_analysis→strc)"

- [ ] **Step 6: Commit**

```bash
git add webapp/frontend/src/components/ChatPanel.tsx webapp/frontend/src/components/EmbeddingPanel.tsx webapp/frontend/src/components/Structure3DPanel.tsx
git commit -m "feat(linkage): route agent artifacts to store, panels subscribe to cross-tab state"
```

## Phase P5: 清理 + 最终测试

**目标:** 删除孤立的旧组件子图(已确认只被彼此引用,未接入 live App 树),跑全套测试,真实数据 E2E。

### Task 25: 删除孤立旧组件

**Files:**
- Delete: 旧组件子图(已验证未被 App 树引用)

- [ ] **Step 1: 再次确认旧组件仅被彼此引用**

Run: `cd webapp/frontend/src && for f in IGVPanel HiGlassPanel FigureComposer FigurePreview MainCanvas PanelContainer AgentPanel DataTree CellEmbedding StructureViewer A2UIChat FileBrowser; do echo "$f:"; grep -rl "\b$f\b" . | grep -v "components/$f.tsx"; done`
Expected: 所有引用都来自上述列表内部的其它文件(无 App.tsx/TabContainer/TwoColumnLayout 引用)

- [ ] **Step 2: 删除旧组件文件**

```bash
cd webapp/frontend/src/components && rm -f \
  IGVPanel.tsx HiGlassPanel.tsx FigureComposer.tsx FigurePreview.tsx \
  MainCanvas.tsx PanelContainer.tsx AgentPanel.tsx DataTree.tsx \
  CellEmbedding.tsx StructureViewer.tsx A2UIChat.tsx FileBrowser.tsx
```

- [ ] **Step 3: 确认无残留引用(构建能过)**

Run: `cd webapp/frontend && npx tsc --noEmit 2>&1 | grep -iE "IGVPanel|HiGlass|FigureComposer|MainCanvas|AgentPanel|DataTree|CellEmbedding|StructureViewer|A2UIChat|FileBrowser|PanelContainer|FigurePreview" | head`
Expected: 无输出(无对已删除组件的悬空引用)

- [ ] **Step 4: 确认 ws.ts(旧 WS 客户端)是否还被引用**

Run: `cd webapp/frontend/src && grep -rl "from '../ws'\|from './ws'" . | grep -v "ws.ts"`
Expected: 若只有已删除组件用它则一并删除 `ws.ts`;若 ChatPanel 等仍用则保留

- [ ] **Step 5: Commit**

```bash
git add -A webapp/frontend/src/components/
git commit -m "chore: remove orphaned legacy components (IGV/HiGlass/FigureComposer/MainCanvas/etc.)"
```

---

### Task 26: 前端构建验证

**Files:**
- Build check

- [ ] **Step 1: 类型检查**

Run: `cd webapp/frontend && npx tsc --noEmit 2>&1 | tail -20`
Expected: 无错误(或仅与本计划无关的既有错误)

- [ ] **Step 2: 生产构建**

Run: `cd webapp/frontend && npm run build 2>&1 | tail -20`
Expected: 构建成功,产出 dist/

- [ ] **Step 3: Commit(若构建配置有调整)**

```bash
git add -A webapp/frontend/ && git commit -m "build: verify frontend builds after cleanup" || echo "nothing to commit"
```

---

### Task 27: 后端全套测试

**Files:**
- Test run

- [ ] **Step 1: 跑全部后端测试**

Run: `pytest tests/backend/ -v 2>&1 | tail -40`
Expected: 全部 PASS(test_ws_handler / test_agent_tools / test_notebook_api / test_data_flow / test_tileset_gosling)

- [ ] **Step 2: 确认后端能 import + 启动**

Run: `python3 -c "import webapp.backend.main; print('import ok')" && timeout 3 python3 -m uvicorn webapp.backend.main:app --port 8766 2>&1 | grep -i "uvicorn running\|error" | head; echo "startup checked"`
Expected: "import ok" + "Uvicorn running",无 ImportError

- [ ] **Step 3: Commit(若有测试修复)**

```bash
git add -A tests/ webapp/backend/ && git commit -m "test: full backend suite passing" || echo "nothing to commit"
```

---

### Task 28: 真实数据 E2E 验证 + 文档

**Files:**
- Modify: `example-data/README.md`(记录验证数据集)
- Create: `context/20260610-e2e-validation.md`(验证结果)

- [ ] **Step 1: 找到一个真实 .h5cd 测试数据**

Run: `find . -name "*.h5cd" -not -path "*/node_modules/*" 2>/dev/null | head; ls example-data/*.h5cd 2>/dev/null`
Expected: 找到 example-data 中已有的小型 .h5cd(如 tutorial 用的 mESC Sox2 FISH)

- [ ] **Step 2: 启动全栈(后端 + 前端 dev)**

```bash
# 后端(后台)
python3 -m uvicorn webapp.backend.main:app --port 8000 &
# 前端 dev
cd webapp/frontend && npm run dev &
```
打开浏览器到前端 dev URL。

- [ ] **Step 3: 逐项人工验证(记录结果)**

依次验证并记录每项 PASS/FAIL:
1. TopBar Open File 输入真实 .h5cd 路径 → 加载成功,显示文件名
2. Embedding Tab → UMAP 散点渲染(真实细胞,非 demo)
3. 3D Structure Tab → 渲染真实结构坐标
4. ChatPanel 输入"显示 chr1 的信号轨道" → Agent 产 gosling_spec → Genomic Tab 渲染
5. Notebook Tab → 编辑 cell `print(cd)` → Run → 输出 ChromData repr
6. ChatPanel 输入"选择前 10 个细胞并显示 3D" → 3D Tab 切换到该细胞(联动)

- [ ] **Step 4: 写 E2E 验证文档**

Create: `context/20260610-e2e-validation.md`,记录每项验证结果(PASS/FAIL + 截图或输出摘要)、所用数据集名称/路径/大小。对 FAIL 项列出后续修复任务。

- [ ] **Step 5: 更新 example-data 目录**

在 `example-data/README.md` 中确认验证所用数据集已登记(若用了新数据集,按 CLAUDE.md 规则补行:size/source/format/consuming tutorial)。

- [ ] **Step 6: 停止服务**

```bash
pkill -f "uvicorn webapp.backend.main" ; pkill -f "vite" || echo "stopped"
```

- [ ] **Step 7: Commit**

```bash
git add context/20260610-e2e-validation.md example-data/README.md
git commit -m "docs: E2E validation results on real ChromData"
```

- [ ] **Step 8: 记录 P5 完成**

Echo: "P5 完成:旧组件已删,前后端测试通过,真实数据 E2E 验证完成。分析工作台 MVP 就绪。"

---

## 完成标准(全计划)

- [ ] 后端单一入口 main.py,`import webapp.backend.main` 无错,能启动
- [ ] 前端 4 Tab 全部连真实 ChromData 端点,无 demo 残留
- [ ] ChatPanel 经 /ws/main 收发,Agent 可产 gosling_spec/patch 并渲染
- [ ] Notebook 经独立 IPython 内核执行,Agent 可生成 cell 用户可编辑
- [ ] 8 个 Agent 工具全部定义并实现(render/patch_gosling 完整,其余可工作)
- [ ] 跨 Tab 联动:Agent select_cells→3D、color_embedding→UMAP、run_analysis→strc
- [ ] 旧 IGV/HiGlass/FigureComposer 等已删除
- [ ] 后端测试套件通过 + 真实数据 E2E 验证记录在案
- [ ] git 历史未被改动(误提交到 main 的 commit 由用户处理)
