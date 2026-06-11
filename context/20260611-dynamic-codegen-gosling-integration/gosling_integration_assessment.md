# U-Chrom Webapp Gosling.js 集成现状评估与增强方案

**文档版本**: v1.0  
**日期**: 2026-06-11  
**基线代码**: `.claude/worktrees/webapp/webapp/` @ `43cfb549c` (`feat/phase0-viewer-integration`)

---

## 一、现状评估

### 1.1 渲染链路图（端到端已通）

```
用户输入 (ChatPanel.tsx:116 ws.send('user_message'))
  ↓ WebSocket /ws/main
ws_handler.handle_message → run_agent_loop (ws_handler.py:107)
  ↓ Claude API (claude-sonnet-4-6) + TOOLS/SYSTEM_PROMPT (agent_tools.py)
  ↓ tool_use: render_gosling
后端转发 agent_artifact{artifact_type:'gosling_spec', spec} (ws_handler.py:166)
  ↓ WebSocket（flat 消息，ws.ts:30 按 type 分发）
ChatPanel.onMessage('agent_artifact') (ChatPanel.tsx:23)
  ↓ addGoslingArtifact + setActiveGoslingSpec (store.ts:114)
GenomicPanel 读取 activeGoslingSpec (GenomicPanel.tsx:40,48)
  ↓ specToRender = activeSpec ?? LOCAL_CONTACT_MAP_SPEC
GoslingRenderer <GoslingComponent spec=.../> (GoslingRenderer.tsx:100)
```

**结论**: 这条链路**端到端是通的、真实工作的**，不是 stub。

---

### 1.2 已完成能力清单（有代码证据）

| 能力 | 证据文件:行号 | 状态 |
|------|-------------|------|
| `render_gosling` 全链路 | ws_handler.py:161-182；ChatPanel.tsx:24-38 | ✅ 工作 |
| `patch_gosling` 增量更新 | ws_handler.py:183-213；store.ts:118-136 | ✅ 工作（仅限当前 active spec） |
| 结构分析 REST 端点 (TAD/loop/comp) | strc_api.py:94-191，调用真实 `uchrom.strc.*` | ✅ 工作 |
| `format=gosling` 裸数组响应 | strc_api.py:79-87 `_respond()` | ✅ 工作 |
| ANALYSIS_REGISTRY + 分析→渲染交接 | strc_api.py:211-299；ws_handler.py:258-306 | ✅ 工作 |
| HiGlass tileset 协议 (info/tiles) | tileset_api.py 全文；test_gosling_compat.py 全绿 | ✅ 协议层工作（渲染存疑） |
| 真实 256×256 float32 tile 编码 | tileset_api.py:132-172；test 95-122 验证值=距离矩阵 | ✅ 工作 |
| HiGlass 重复参数 `?d=a&d=b` 批量 | tileset_api.py:59-72；test 129-143 | ✅ 工作（曾回归，已修） |
| WIG signal track 端点 | track_wig.py:40-90 | ✅ 工作（格式存疑，见 1.4） |
| viewport 双向同步 | GoslingRenderer.tsx:23-75 | ⚠️ 工作但有竞态隐患 |
| export_view (PNG/PDF) | ws_handler.py:361-375；GoslingRenderer.tsx:80-96 | ⚠️ 依赖 Gosling API 版本，静默降级 |
| 默认 contact map + TAD overlay spec | localContactMapSpec.ts 全文 | ⚠️ 见 1.6 矩阵渲染存疑 |

---

### 1.3 支持的 mark / data source 类型

#### Mark 类型
system prompt 列出 8 种（agent_tools.py:15-23）:
- `rect`, `bar`, `rule`, `link`, `text`, `area`, `line`, `point`

后端**不做校验**——agent 自由生成，前端 Gosling 原样渲染。即"支持" = Gosling 自身支持，无后端约束。

#### Data Source 类型
| 类型 | 支持状态 | 证据 |
|------|---------|------|
| `json` (inline/url) | ✅ 工作 | 结构分析结果（strc 端点返回裸数组） |
| `csv` | ⚠️ 格式不匹配 | track_wig 实际返回 WIG 文本，不是 CSV（见 E1） |
| `matrix` (HiGlass tileset) | ✅协议 / ⚠️渲染 | localContactMapSpec.ts:17-23 |
| `beddb` | ✅ 外部 | 仅 REMOTE_DEMO_SPEC 用外部 URL (GenomicPanel.tsx:20) |
| `multivec` | ❌ 未实现 | Phase3 文档提到，但代码中无 |

---

### 1.4 Viewport 同步机制

#### 三方同步现状
| 方向 | 实现位置 | 状态 |
|------|---------|------|
| **Gosling → store** | GoslingRenderer.tsx:38 `gos.subscribe('location')` | ✅ 带 `suppressingRef` 防回环 |
| **store → Gosling** | GoslingRenderer.tsx:70 `gos.zoomTo()` | ✅ suppressingRef + 500ms 超时复位 |
| **store → 后端** | store.ts:83 `ws.send('update_viewport')` | ✅ 发送成功 |
| **后端存储** | ws_handler.py:96-97 `session.viewport = payload` | ✅ 存储成功 |
| **后端 → agent** | ❌ **缺失** | 后端只存不传，agent 无法感知 |

**缺口**: 后端从不回传 viewport 给 agent——agent 无法感知用户当前在看哪里（system prompt 也没注入 viewport）。所谓"前端↔后端↔agent"的 agent 环节是**断的**。

---

### 1.5 TAD/loop/compartment Overlay 渲染

| 分析类型 | 渲染实现 | 状态 |
|---------|---------|------|
| **TAD** | localContactMapSpec.ts:36-82，两个 `rule` track（start/end 边界）叠在 heatmap 上，数据来自 `/api/tads/chr21?format=gosling` | ✅ 预置 overlay |
| **loop** | 无默认 overlay spec，完全依赖 agent 在 run_analysis 后手动调 render_gosling (ws_handler.py:291-296) | ⚠️ 能做但未预置 |
| **compartment** | 同 loop | ⚠️ 能做但未预置 |

---

### 1.6 Stub / 未完成 / 存疑清单

| 项目 | 证据 | 判定 |
|------|------|------|
| **E1: signal track 格式不匹配** | track_wig.py:84-90 返回 `variableStep WIG` 文本；但 system prompt (agent_tools.py:93) 和 Phase3 都让 agent 用 `data.type:'csv'` | ❌ **csv loader 无法解析 WIG**，signal track 大概率不渲染 |
| **E2: contact map 矩阵渲染未验证** | localContactMapSpec.ts:20 `url:/api/tileset_info?d=...` + `server:window.location.origin`；main.py:37-38 只 alias 了 `/api/v1/tileset_info`（无尾斜杠）和 `/api/v1/tiles/`；**URL 拼接路径与 alias 不一致** | ⚠️ 实际能否在浏览器渲染**未经端到端验证**（后端协议测试全绿 ≠ 前端能画出来） |
| **E3: loop 跨染色体字段映射错误** | 注册表 `chromosome_field:"chrom1"`, `genomic_fields:["start1","end1","start2","end2"]` (strc_api.py:224-225)；但 loop 数据还有 chrom2；link mark 需 x/xe + x1/x1e，单一 chromosomeField 对跨 chrom2 的锚点不正确 | ❌ **跨染色体 loop 渲染不正确**（同染色体内可用） |
| **patch 路径假设** | store.ts:124 按 `/` split，注释只处理 `/views/N/tracks/M/...`；agent_tools.py:128 示例却给 `/tracks/0/mark`（顶层 tracks） | ⚠️ 对部分 spec 形态会静默失败 |
| **多数 agent 工具为 stub** | agent_tools.py:1-6 注释明说 "executors are placeholders"；ws_handler 里 `color_embedding`/`select_cells`/`show_structure` 等只 `send_json` artifact + 返回固定字符串，**不真正操作数据** | ℹ️ 多数为 UI 信号 stub |
| **历史/撤销** | 设计文档提到 `specHistory`（撤销），store.ts 无此字段 | ❌ 未实现 |
| **`/api/gosling/datasources`** | 两份设计文档都要求，代码中**不存在** | ❌ 未实现 |

---

### 1.7 HiGlass Tileset 协议完成度

#### 协议层（✅ 完成度高）
- `tileset_info` 返回 HiGlass 必需字段：`max_zoom`, `min_pos`, `max_pos`, `bins_per_dimension`, `datatype` (test 66-80 断言)
- `tiles` 返回真实下采样的距离矩阵 tile（test 106-122 断言 `tile.max == matrix.max`）
- 矩阵由 coords 实时算 pairwise 距离并跨 trace 平均 (tileset_api.py:75-111)

#### 渲染层（⚠️ 未验证）
**唯一存疑**: 前端 HiGlass 客户端能否正确按 `server` / `url` 约定取到这些 tile 并渲染？这是 **E2 的核心存疑点**。

---

## 二、增强方案（按优先级）

### P0 — 修正会导致"看起来支持其实画不出来"的缺陷

#### **E1. 修复 signal track 数据格式不匹配**（中等工作量）

**问题**: track_wig.py 返回 WIG 文本，但 agent prompt 说用 `data.type:'csv'`，Gosling csv loader 无法解析 WIG。

**方案 A**（推荐）: 新增真正的 CSV 端点
- 文件: 新增 `track_api.py`
- 端点: `/api/tracks/{name}/csv?chrom={chrom}`
- 返回: `chrom,start,end,value\nchr1,1000,1001,0.5\n...`
- 同步改: system prompt (agent_tools.py:93,245) 示例 URL

**方案 B**: 让 agent 使用 WIG-aware data type
- 修改: system prompt 改为 `data: {type: 'wig', url: ...}`
- 风险: Gosling 是否原生支持 WIG type 需验证

**依赖**: 无  
**验收**: agent 生成 signal track → 浏览器实际画出曲线

---

#### **E2. 端到端验证 contact map 渲染并对齐 HiGlass URL 约定**（中等工作量）

**问题**: 
- spec 的 `server: window.location.origin` + `url: /api/tileset_info?d=...`
- main.py alias: `/api/v1/tileset_info` / `/api/v1/tiles/`
- HiGlass 客户端可能拼接 `${server}/tileset_info/?d=` 或 `${server}/api/v1/...`
- **三者路径不一致**，后端协议测试全绿但前端渲染未验证

**方案**: 实测 + 对齐
1. 启动后端 + 前端，浏览器 DevTools Network 看 HiGlass 实际请求什么 URL
2. 对齐三者：
   - **选项 A**: spec 改 `server: "${origin}/api/v1"`，保持现有 alias
   - **选项 B**: main.py 补齐 `/api/tileset_info/` 和 `/api/tiles/`（带尾斜杠）路由
3. 加 Playwright/前端 e2e 断言 canvas 非空（真正画出热图）

**依赖**: 无  
**验收**: localContactMapSpec 默认视图在浏览器显示热图 + TAD overlay

---

#### **E3. 修正 loop 跨染色体字段映射**（小工作量）

**问题**: link mark 需要 `chrom2` 走 x1 通道；当前注册表只给单 `chromosomeField`，trans loop 数据有 chrom1/chrom2 两列。

**方案**:
- 文件: strc_api.py:220-227 ANALYSIS_REGISTRY loop 条目
- 改动: `next_step` 里指明 x1/x1e 映射到 chrom2/start2/end2，或返回专门的 `chromosome_field_x1: "chrom2"`
- 或: agent prompt 里明确 trans loop 需要手动指定 x1 通道

**依赖**: 无  
**验收**: trans loop（chrom1 ≠ chrom2）渲染为 link 弧线，端点正确

---

### P1 — 补齐设计文档承诺但缺失的能力

#### **E4. 新增 `/api/gosling/datasources` 端点 + 注入 agent**（中等工作量）

**目标**: 让 agent 构 spec 时不再"猜"字段名（呼应 prompt "DO NOT HALLUCINATE" agent_tools.py:106）

**方案**:
- 文件: 新增 `gosling_api.py`
- 端点: `GET /api/gosling/datasources` 返回:
  ```json
  {
    "chromosomes": ["chr1", "chr2", ...],
    "signal_tracks": [{"name": "ATAC", "url": "/api/tracks/ATAC/csv?chrom={chrom}"}],
    "contact_maps": [{"name": "contact-chr1", "tileset_uid": "..."}],
    "available_fields": {"chrom": "string", "start": "int", ...}
  }
  ```
- 注入: 在 system prompt 添加"调用 datasources 端点获取可用数据源"，或作为独立 tool

**依赖**: E1（signal track URL 要先正确）  
**验收**: agent 调 datasources → 使用正确的 track 名称和字段

---

#### **E5. viewport 回传 agent**（中等工作量）

**目标**: 打通 1.4 的断点——agent 能感知"用户现在看 chr1:1000-5000"

**方案**:
- 文件: ws_handler.py `handle_message('user_message')` 处理前
- 改动: 把 `session.viewport` 拼进上下文（system 或 user message 附加段）
  ```python
  if session.viewport:
      context_msg = f"[Current view: {session.viewport}]"
      # 注入到 history 或 system param
  ```
- store.ts 已发送，后端已存储，只需"读出来给 agent"

**依赖**: 无  
**验收**: 用户 pan/zoom 到某区域 → agent 回答"你现在看的区域的 TAD 有..."

---

#### **E6. 预置 loop/compartment overlay spec builder**（中等工作量）

**目标**: 像 TAD 那样给 loop（link）和 compartment（bar）预置 overlay

**方案**:
- 文件: 新增 `specBuilders.ts`（Phase3 Task2 已设计）
- 函数: `buildLoopOverlay(baseSpec, loopDataUrl)`, `buildCompartmentOverlay(...)`
- 集成: run_analysis 后自动叠加，而非全靠 agent 手搓

**依赖**: E3（loop 字段映射先修正）  
**验收**: run_analysis("loop") → 前端自动显示 link overlay

---

### P2 — 体验 / 健壮性

#### **E7. patch 路径健壮化 + spec 结构统一**（小工作量）
- 文件: store.ts:118-136、agent_tools.py 示例
- 改动: 统一 spec 顶层结构（views[] vs tracks[]），patch 失败时回传错误给 agent 而非静默

#### **E8. spec 历史 / 撤销**（小工作量）
- 文件: store.ts（加 specHistory）、GenomicPanel.tsx artifact 列表已有雏形 (tsx:96-113)

#### **E9. 真正实现 stub 工具**（大工作量）
- 文件: ws_handler.py:307-360 的 `color_embedding` / `select_cells` / `show_structure` / `color_structure`
- 改动: 让它们真正驱动 EmbeddingPanel / Structure3DPanel 的数据着色，而非只切 tab
- **注**: 属 Phase0 之外的范围

---

## 三、MVP 推荐

**只做一件事：E2 —— 端到端验证并修通 contact map 矩阵渲染**

### 理由

Gosling 集成对 U-Chrom 的**独有价值**就是:
- 把 3D 重建结果反算的**距离矩阵**当 Hi-C 热图画出来
- tileset_api.py 已实时算好真实矩阵（后端扎实）
- 其余 mark（rule/bar/link）外部工具也能做

但"从 coords 实时生成 HiGlass tile 并在 Gosling 里画热图 + TAD overlay"是这套栈的**差异化**。

**唯一卡点**: 前端 HiGlass URL 约定是否对齐——这是**低工作量、高杠杆**的一环。如果它实际画不出来，整个 Gosling 卖点是空的；修通它即可让 localContactMapSpec 这个默认视图真正可用。

### 实施步骤

1. **实测**（30 分钟）
   - 启动 webapp 后端: `cd .claude/worktrees/webapp && python -m webapp.backend.main`
   - 启动前端: `cd .claude/worktrees/webapp/webapp/frontend && npm run dev`
   - 浏览器访问，加载数据 + 打开 Genomic tab
   - DevTools Network → 看 HiGlass 请求什么 URL（`tileset_info` / `tiles`）
   - 看响应状态（200 vs 404）

2. **对齐**（1-2 小时）
   - 根据实测结果调整 spec 的 `server` 或 main.py 的 alias
   - 保证 URL 一致

3. **E2E 测试**（2 小时）
   - 新增 Playwright 测试: 加载数据 → 等待 canvas 渲染 → 断言 canvas 非空
   - 或手动验收: 肉眼看到热图 + TAD overlay

**总工作量**: 半天  
**价值**: 验证核心卖点真实性

---

## 四、风险点

### 1. HiGlass tileset 协议 URL 约定不一致（最高风险）

**现状**: 
- spec: `server: origin` + `/api/tileset_info`
- main.py: `/api/v1/tileset_info` / `/api/v1/tiles/`
- HiGlass 客户端拼接逻辑: 未知

**影响**: 后端协议测试全绿，但前端可能 404  
**缓解**: E2 实测 + 对齐

---

### 2. 大数据渲染性能

**现状**: `_build_matrix` 对每条 trace 做 O(k²) pairwise (tileset_api.py:99-104)，全 chrom 矩阵缓存在内存 (tileset_api.py:33)

**影响**: 
- 大基因组/多 trace 下首个 tile 请求会卡
- 内存占用高
- tile cache 无淘汰机制

**缓解**: 
- 限制单 trace 显示
- 实现 LRU cache
- 预计算常用矩阵

---

### 3. Viewport 同步竞态

**现状**: 靠 `suppressingRef` + 固定 500ms 超时 (GoslingRenderer.tsx:71-72) 抑制回环

**影响**: 
- 快速连续 pan/zoom 或 zoomTo 动画超 500ms 时
- 超时复位早于动画结束
- 触发反向回写造成抖动

**缓解**: 
- 增加序号/时间戳仲裁
- 或使用 Gosling 的动画完成回调

---

### 4. Agent 幻觉字段

**现状**: 后端对 render_gosling 的 spec **零校验** (ws_handler.py:161 直接转发)，全靠 prompt 约束

**影响**: 
- 字段名错（如 track_wig 用 csv）只在前端静默不渲染
- 无错误反馈回 agent，难自纠

**缓解**: E4（datasources 端点）能部分缓解

---

### 5. Tile cache 跨数据集

**现状**: `clear_cache()` 在 load_data 时调用 (ws_handler.py:71)，但 `_matrix_cache` 按 chrom 名 key (tileset_api.py:77)

**影响**: 若两次加载的数据集 chrom 名相同会命中旧矩阵

**缓解**: 已有 clear 兜底，但任何绕过 load_data 的路径有隐患

---

### 6. Export 静默降级

**现状**: exportPng/Pdf 依赖 Gosling 版本 API，try/catch 全吞 (GoslingRenderer.tsx:93)

**影响**: 用户点导出可能无任何反馈

**缓解**: catch 块里发 toast 通知或 console.warn

---

## 五、下一步行动

### 立即执行（验证地基）
1. **实测 E2**: 启动后端 + 前端，用浏览器 DevTools 看 HiGlass 实际请求 URL
2. **对齐 URL**: 根据实测调整 spec 或 main.py alias
3. **验收**: 肉眼看到热图 + TAD overlay，或加 Playwright 断言

### 短期（1-2 周）
4. **E1**: 修复 signal track 格式（新增 CSV 端点）
5. **E3**: 修正 loop 跨染色体字段
6. **E4**: 实现 datasources 端点

### 中期（1 个月）
7. **E5**: viewport 回传 agent
8. **E6**: 预置 loop/compartment overlay
9. **E7-E8**: 健壮性改进

---

## 六、参考设计文档

- `/Volumes/sandisk/Coding/U-Chrom/context/20260610-phase3-gosling-plan.md`
- `/Volumes/sandisk/Coding/U-Chrom/context/20260610-gosling-agui-design.md`
- `/Volumes/sandisk/Coding/U-Chrom/docs/e2e_test_summary.md`
