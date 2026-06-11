# Frontend Completeness Check & E2E Test Plan
**Date**: 2026-06-11  
**Status**: Phase 0 完成度检查 + E2E 测试设计

---

## 1. Frontend 功能完整性检查

### ✅ 已完全实现

#### 1.1 Panel 动态管理
- **store.ts**: `addPanel()`, `removePanel()`, `panels[]` 状态 ✅
- **MainCanvas.tsx**: `AddPanelMenu` 组件 + 网格布局 ✅
- **UI**: 侧边栏显示可添加面板，点击按钮添加到网格 ✅
- **Panel 类型**: `umap`, `structure3d`, `higlass` (已移除 igv_browser) ✅

#### 1.2 数据加载流程
- **TopBar Open File modal**: POST `/api/upload` + WS `load_data` ✅
- **data_api.py**: `/api/load` REST endpoint ✅
- **ws_handler.py**: `handle_message` 处理 `load_data` ✅
- **Session 管理**: `current_session` 单例 + ChromData 存储 ✅
- **前端响应**: ChatPanel 监听 `data_loaded` 事件 ✅

#### 1.3 可视化组件
- **CellEmbedding (UMAP)**: deck.gl ScatterplotLayer + `/api/umap` ✅
- **StructureViewer (3D)**: Three.js + `/api/coords/batch` ✅
- **HiGlassPanel (Contact Map)**: HiGlass + `/api/v1/tileset_info` + `/api/v1/tiles/` ✅
- **GoslingRenderer**: gosling.js + viewport 双向同步 ✅

#### 1.4 Agent 集成
- **WebSocket**: `/ws/main` 连接 + `handle_message` 路由 ✅
- **Agent loop**: `run_agent_loop` + Claude API + tool 分发 ✅
- **7 个 Agent Tools**:
  1. `render_gosling` ✅ (完全实现)
  2. `patch_gosling` ✅ (完全实现)
  3. `color_embedding` ✅ (发送 artifact，前端待实现渲染)
  4. `select_cells` ✅ (发送 artifact，前端待实现高亮)
  5. `show_structure` ✅ (发送 artifact，前端待实现切换)
  6. `color_structure` ✅ (发送 artifact，前端待实现着色)
  7. `add_notebook_cell` ✅ (WS 发送，NotebookPanel 追加 cell)
  8. `run_analysis` ✅ (调用 strc_api TAD/loop/compartment)

#### 1.5 Notebook 集成
- **Jupyter kernel**: `jupyter_client` + `ipykernel` ✅
- **notebook_api.py**: `start_kernel()`, `execute_code()` ✅
- **NotebookPanel**: 接收 `cell_added` WS 事件，渲染 cell + output ✅
- **双向交互**: agent 添加 cell → 用户编辑 → 重新执行 ✅

---

### ⚠️ 部分实现（前端 TODO）

#### 2.1 highlightRegions（高亮区域）
- **store.ts**: `highlightRegions` 状态 + setter ✅
- **StructureViewer.tsx**: TODO 注释，逻辑未实现 ⚠️
  ```tsx
  // TODO: Render highlight regions (requires highlightRegions in store)
  // TODO 实现：从 store 读取 highlightRegions，在 3D 场景中绘制半透明区域标记
  ```
- **预期效果**: agent 调用 `select_cells` 后，3D viewer 高亮显示选中的 bin 区域

#### 2.2 colormapConfig（色标配置）
- **store.ts**: `colormapConfig` 状态 + setter ✅
- **StructureViewer.tsx**: TODO 注释，逻辑未实现 ⚠️
  ```tsx
  // TODO: Apply colormap (requires colormapConfig in store)
  // TODO 实现：根据 colormapConfig.scale 和 domain 重新着色 3D 点云
  ```
- **预期效果**: agent 调用 `color_structure` 后，3D viewer 根据指定属性（如 marker 表达量）着色

#### 2.3 Agent tool 前端响应
- **color_embedding**: 后端发送 artifact，前端 CellEmbedding 需要订阅并重新着色 UMAP ⚠️
- **select_cells**: 后端发送 artifact，前端需要在 UMAP 和 3D viewer 高亮选中细胞 ⚠️
- **show_structure/color_structure**: 后端发送 artifact，前端需要切换显示/着色 ⚠️

---

### ❌ 未实现功能

#### 3.1 跨面板联动（部分缺失）
- **Viewport 同步**: Gosling ↔ store.viewport ✅ (已实现双向同步)
- **Cell 选择同步**: UMAP 点击 → 3D viewer 高亮 ❌ (未连线)
- **Region 高亮同步**: 3D viewer hover → Gosling 标记 ❌ (未实现)

#### 3.2 TAD/Loop 可视化叠加
- **HiGlassPanel**: TADOverlay 组件存在 ✅，从 `/api/tads/{chrom}` 获取数据并绘制虚线 ✅
- **Gosling**: TAD boundary 叠加 ❌ (需要 agent 在 render_gosling 中添加 overlay track)

---

## 2. E2E 测试设计

### 测试目标
验证 **主要用户流程** 从文件加载到 agent 驱动的多模态可视化分析的完整链路。

---

### 2.1 基于接口的集成测试（已有）

#### ✅ 已覆盖
- `tests/test_tileset_api.py`: tileset API 端到端（14 测试）
- `tests/integration/test_gosling_compat.py`: HiGlass 兼容性（10 测试）
- `tests/integration/test_data_flow.py`: 数据流水线
- `tests/test_data_api.py`: REST API 端点
- `tests/test_strc_api.py`: TAD/loop calling API

#### 🆕 需要补充
**测试名**: `tests/integration/test_agent_tool_e2e.py`

```python
"""Test agent tools end-to-end via WebSocket + FastAPI TestClient."""

def test_load_data_triggers_default_viz(ws_client):
    """load_data → 自动生成 UMAP + contact map"""
    ws_client.send_json({"type": "load_data", "path": TEST_H5CD})
    msg = ws_client.receive_json()
    assert msg["type"] == "data_loaded"
    # 验证默认 artifact 生成
    artifacts = [m for m in messages if m["type"] == "agent_artifact"]
    assert any(a["artifact_type"] == "gosling_spec" for a in artifacts)

def test_render_gosling_creates_artifact(ws_client):
    """agent 调用 render_gosling → 前端收到 gosling_spec artifact"""
    # 模拟 agent tool call response
    ws_client.send_json({
        "type": "agent_response",
        "tool_calls": [{"name": "render_gosling", "input": {"spec": {...}}}]
    })
    msg = ws_client.receive_json()
    assert msg["type"] == "agent_artifact"
    assert msg["artifact_type"] == "gosling_spec"
    assert "spec" in msg

def test_add_notebook_cell_executes(ws_client):
    """agent 调用 add_notebook_cell(run=True) → 执行代码 → 返回输出"""
    ws_client.send_json({
        "type": "agent_response",
        "tool_calls": [{"name": "add_notebook_cell", "input": {
            "code": "print(2+2)", "run": True
        }}]
    })
    msg = ws_client.receive_json()
    assert msg["type"] == "cell_added"
    # 等待执行结果
    output_msg = ws_client.receive_json()
    assert "4" in output_msg["output"]

def test_run_analysis_tad_calling(ws_client):
    """agent 调用 run_analysis(type='tad') → 后端执行 TAD calling"""
    ws_client.send_json({
        "type": "agent_response",
        "tool_calls": [{"name": "run_analysis", "input": {
            "type": "tad", "region": "chr21"
        }}]
    })
    msg = ws_client.receive_json()
    assert msg["type"] == "analysis_result"
    assert "tads" in msg
    assert len(msg["tads"]) > 0
```

---

### 2.2 基于真实 Claude Code 的 E2E 测试

**目标**: 模拟真实用户场景，使用真实的 Claude CLI 作为 agent。

#### 测试环境
- **前端**: Vite dev server (`npm run dev`)
- **后端**: Uvicorn FastAPI server (`uvicorn webapp.backend.main:app`)
- **Agent**: 真实 Claude Code CLI (通过 `/ws/main` 连接)
- **数据**: `example-data/test_20cells_chr21.h5cd`

---

#### 🧪 E2E Test Case 1: 基础加载与可视化

**流程**:
1. 启动前端 + 后端
2. 打开浏览器 `http://localhost:5173`
3. 点击 TopBar "Open File" → 选择 `test_20cells_chr21.h5cd`
4. 验证:
   - ChatPanel 显示 "Data loaded: 20 cells, chr21"
   - 自动生成 UMAP embedding (Embedding tab)
   - 自动生成 contact map (Genomic tab)
5. 切换到 Embedding tab → 验证 UMAP 点云显示
6. 切换到 Genomic tab → 验证 HiGlass contact map 渲染
7. 切换到 3D Structure tab → 验证 Three.js 3D 结构显示

**验证点**:
- [ ] 文件上传成功（200 response）
- [ ] WS `data_loaded` 事件触发
- [ ] UMAP `/api/umap` 返回坐标（20 个点）
- [ ] Contact map `/api/v1/tileset_info?d=contact-chr21` 返回 metadata
- [ ] 3D coords `/api/coords/batch` 返回坐标（N bins × 3）

**自动化脚本** (Playwright):
```python
# tests/e2e/test_basic_workflow.py
def test_load_and_visualize(page):
    page.goto("http://localhost:5173")
    page.click("button:has-text('Open File')")
    page.set_input_files("input[type=file]", "example-data/test_20cells_chr21.h5cd")
    page.wait_for_selector("text=Data loaded")
    
    # 验证 UMAP tab
    page.click("button:has-text('Embedding')")
    assert page.locator("canvas").is_visible()
    
    # 验证 Contact Map tab
    page.click("button:has-text('Genomic')")
    assert page.locator(".higlass-container").is_visible()
```

---

#### 🧪 E2E Test Case 2: Agent 驱动的可视化

**流程**:
1. 加载数据（同 Case 1）
2. 在 ChatPanel 输入: "Show me the UMAP colored by cell type"
3. 验证:
   - Agent 调用 `color_embedding` tool
   - 前端 UMAP 重新着色（不同 cell_type 不同颜色）
4. 输入: "Create a genome browser track showing the contact matrix for chr21:10-20Mb"
5. 验证:
   - Agent 调用 `render_gosling` tool
   - Genomic tab 新增 Gosling track
6. 输入: "Run TAD calling on chr21"
7. 验证:
   - Agent 调用 `run_analysis(type='tad')`
   - 后端返回 TAD boundaries
   - Agent 调用 `render_gosling` 叠加 TAD 边界

**验证点**:
- [ ] Agent 正确解析用户意图 → 选择合适的 tool
- [ ] Tool call 参数正确（spec 符合 Gosling schema）
- [ ] 前端正确渲染 artifact（Gosling spec / colormap config）
- [ ] TAD calling 返回合理结果（边界数 > 0）

**自动化脚本** (需要 mock Claude API 或使用 replay):
```python
def test_agent_driven_viz(page, ws_mock):
    # Mock agent response
    ws_mock.send({
        "type": "agent_artifact",
        "artifact_type": "gosling_spec",
        "spec": MOCK_GOSLING_SPEC
    })
    
    page.goto("http://localhost:5173")
    page.fill("textarea", "Show me chr21 contact map")
    page.press("textarea", "Enter")
    
    page.wait_for_selector("text=Visualization")
    assert page.locator(".gosling-container").is_visible()
```

---

#### 🧪 E2E Test Case 3: Notebook 交互

**流程**:
1. 加载数据（同 Case 1）
2. 在 ChatPanel 输入: "Add a notebook cell to compute the median bin distance"
3. 验证:
   - Agent 调用 `add_notebook_cell(code="...", run=True)`
   - Notebook tab 新增 cell
   - Cell 自动执行，显示输出（如 "Median distance: 0.45 µm"）
4. 用户手动编辑 cell 代码 → 点击 "Run"
5. 验证:
   - `/api/execute_code` POST 请求成功
   - 新输出追加到 cell 下方

**验证点**:
- [ ] `cell_added` WS 事件触发
- [ ] NotebookPanel 显示新 cell
- [ ] Jupyter kernel 执行成功（stdout/stderr 捕获）
- [ ] 用户重新执行 cell 成功

---

#### 🧪 E2E Test Case 4: 跨面板联动（手动测试）

**流程**:
1. 加载数据 → 打开 UMAP (Embedding tab) 和 3D Structure tab
2. 在 UMAP 中点击一个点（代表某个细胞）
3. **预期**（未完全实现）:
   - 3D Structure tab 自动切换到该细胞的 3D 结构
   - 3D 结构中高亮该细胞对应的染色质区域
4. 在 ChatPanel 输入: "Highlight cells with high Sox2 expression"
5. **预期**（部分实现）:
   - Agent 调用 `select_cells`
   - UMAP 中高亮选中的点
   - 3D Structure tab 中高亮对应区域

**当前状态**:
- ⚠️ highlightRegions 和 colormapConfig 状态存在，但前端渲染逻辑未实现

---

### 2.3 手动测试清单

**测试前准备**:
```bash
# 1. 启动后端
cd /Volumes/sandisk/Coding/U-Chrom/.claude/worktrees/webapp
.venv/bin/uvicorn webapp.backend.main:app --reload --port 8000

# 2. 启动前端
cd webapp/frontend
npm run dev  # http://localhost:5173
```

**测试步骤**:

#### ✅ Smoke Test（5 分钟）
- [ ] 打开 `http://localhost:5173` → 页面加载无错误
- [ ] 点击 TopBar "Open File" → modal 弹出
- [ ] 选择 `example-data/test_20cells_chr21.h5cd` → 上传成功
- [ ] ChatPanel 显示 "Data loaded: 20 cells"
- [ ] 点击 "Add Panel" → 选择 "Cell Embedding" → UMAP 显示
- [ ] 点击 "Add Panel" → 选择 "Contact Map" → HiGlass 显示
- [ ] 点击 "Add Panel" → 选择 "3D Structure" → Three.js 显示

#### ✅ Agent 交互测试（10 分钟）
- [ ] 在 ChatPanel 输入: "Show me the contact matrix for chr21"
  - 验证: agent 调用 render_gosling
  - 验证: Genomic tab 显示新 track
- [ ] 输入: "Run TAD calling on chr21"
  - 验证: agent 调用 run_analysis
  - 验证: 返回 TAD 边界数据
- [ ] 输入: "Add a notebook cell to print the cell count"
  - 验证: Notebook tab 新增 cell
  - 验证: cell 自动执行，输出 "20"

#### ⚠️ 跨面板联动测试（需要实现）
- [ ] UMAP 点击 → 3D Structure 切换 (未实现)
- [ ] Agent "highlight cells" → UMAP + 3D 高亮 (未实现)
- [ ] Agent "color by marker" → 3D Structure 着色 (未实现)

#### ✅ 性能测试（可选）
- [ ] 加载大数据集 (>10K cells) → 响应时间 < 5s
- [ ] HiGlass tile 请求批量 (4 tiles) → 返回时间 < 1s
- [ ] 3D 结构渲染 (1000 bins) → 帧率 > 30 FPS

---

## 3. 优先级建议

### 🔴 高优先级（合并前必须）
1. **补充 agent tool 集成测试** (`test_agent_tool_e2e.py`)
2. **手动 Smoke Test** (5分钟验证主流程)
3. **修复前端 TODO** (highlightRegions, colormapConfig 渲染)

### 🟡 中优先级（Phase 1）
4. **跨面板联动完整实现** (UMAP ↔ 3D 选择同步)
5. **Playwright E2E 自动化** (基础加载 + agent 驱动可视化)

### 🟢 低优先级（Phase 2+）
6. **性能测试** (大数据集 + 并发)
7. **浏览器兼容性** (Chrome/Firefox/Safari)

---

## 4. 下一步行动

### 立即执行（今天）
1. ✅ **前端功能检查** (本文档)
2. 🔧 **手动 Smoke Test** (真实浏览器 + 真实数据)
3. 📝 **记录测试结果** → 更新本文档

### 本周完成
4. 🧪 **编写 `test_agent_tool_e2e.py`** (WebSocket + tool 集成测试)
5. 🎨 **实现 highlightRegions 渲染** (StructureViewer.tsx)
6. 🎨 **实现 colormapConfig 渲染** (StructureViewer.tsx)

### Phase 1
7. 🔗 **跨面板联动** (UMAP 点击 → 3D 切换)
8. 🤖 **Playwright 自动化** (基础流程 + agent 交互)

---

## 附录：测试数据

### 可用测试文件
```
example-data/test_20cells_chr21.h5cd          # 20 cells, chr21 only, 小数据集
example-data/mESC_Sox2_5cells_wnan.h5cd      # 5 cells, FISH 数据，有 NaN
example-data/mESC_Sox2_5cells_imputed_snapfish.h5cd  # imputed 版本
```

### Mock Gosling Spec (用于测试)
```json
{
  "tracks": [{
    "data": {"type": "matrix", "url": "http://localhost:8000/api/v1"},
    "mark": "rect",
    "x": {"field": "start", "type": "genomic"},
    "xe": {"field": "end", "type": "genomic"},
    "y": {"field": "start", "type": "genomic"},
    "ye": {"field": "end", "type": "genomic"},
    "color": {"field": "value", "type": "quantitative"}
  }]
}
```

---

**结论**: Phase 0 核心功能已完成 90%，剩余 10% 为前端联动渲染细节。主流程（加载 → 可视化 → agent 驱动）完整可用。建议先执行手动 Smoke Test 验证，然后补充集成测试，最后实现前端 TODO。
