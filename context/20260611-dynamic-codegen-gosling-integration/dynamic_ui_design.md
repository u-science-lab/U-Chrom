# U-Chrom 动态 UI 设计方案

> 目标:让 Claude agent 不仅能写后端分析代码,还能**驱动前端渲染与交互**——
> 基于 uchrom 数据结构和接口,agent 自己组织 UI,在前端渲染并把用户交互回流给 agent,形成闭环。
>
> 本方案综合两份调研:
> - **pantheon-agents LiveView**(同仓 `../pantheon` 的服务端驱动 UI 实现)
> - **A2UI 业界实践**(Google A2UI / AG-UI / Vercel Generative UI / MCP-UA / OpenAI Apps SDK / assistant-ui / Adaptive Cards)
>
> 日期:2026-06-11

---

## 0. TL;DR

业界已收敛到**两个安全极**,并刻意回避"在主页面 realm 里执行 agent 生成的代码"这个危险中间地带:

1. **声明式组件树 + 宿主拥有的白名单 catalog**(A2UI、assistant-ui、Adaptive Cards、Thesys DSL)
2. **agent 写的 HTML/JS 隔离在 sandboxed iframe**(MCP Apps、OpenAI Apps SDK、pantheon 的 `view_type="custom"`)

U-Chrom 现有的 `ARTIFACT_HANDLERS` + Gosling 声明式 spec **已经站在第一个安全极上**,方向正确。本方案不推翻现状,而是按"声明式优先、iframe 逃生舱兜底"的**三层模型**扩展:

| 层 | 能力 | 安全性 | 状态 |
|----|------|--------|------|
| **Tier 1 领域声明式 spec** | Gosling/embedding/structure 等领域可视化 | 安全(无代码执行) | 已有,继续扩展 |
| **Tier 2 可组合组件树** | agent 用白名单组件拼装新布局(`render_component`) | 安全(叶子节点都是受信 React 组件) | **新增** |
| **Tier 3 sandboxed iframe** | agent 写任意 HTML/JS 的逃生舱 | 浏览器沙箱隔离(独立 origin + CSP) | **新增,慎用** |

**最高优先级补的洞:状态回环**。当前 agent 对 UI 是"只写"——用户在前端的刷选、点击、区域选择无法回流给 agent。这是与 pantheon LiveView 和整个业界差距最大的一项。

---

## 1. 现状分析

### 1.1 已有(且正确)的基础

- **传输**:FastAPI + WebSocket `/ws/main`,Claude tool-calling loop(`ws_handler.run_agent_loop`)。
- **A2UI 协议**:agent 调工具 → 每个工具 executor 发一条 `agent_artifact`(带类型的 JSON UI 效果)+ 返回 `tool_result` 字符串给模型。
- **后端注册表**(本轮重构 B 已完成):`TOOL_EXECUTORS` dict,`run_agent_loop` 完全工具无关,加工具不改循环。
- **前端注册表**(本轮重构 B 已完成):`ARTIFACT_HANDLERS` map,按 `artifact_type` 分发。
- **10 个工具**:render_gosling、patch_gosling、color_embedding、select_cells、show_structure、color_structure、add_notebook_cell、run_analysis、write_analysis_function、export_view。
- **动态代码生成 MVP**(本轮 A 已闭环):`write_analysis_function` → AST 白名单沙箱 + 受限 builtins + 守护线程超时 → 运行时 endpoint `/api/custom/{analysis_id}/{chrom}` → 产出 DataFrame → Gosling track;前端 `custom_analysis_deployed` artifact 已接住。

### 1.2 业界视角下,我们做对了什么

`ARTIFACT_HANDLERS` map **在功能上等同于** A2UI 的 Catalog/Widget Registry 与 assistant-ui 的组件 allowlist——这是被反复验证的安全边界。"agent 只能命名你实现过的效果"正是 A2UI 明确强调的"catalog 编译进服务端而非运行时下载,以防 UI 被 prompt 注入"这一最重要的安全属性。

Gosling.js 声明式 spec 是我们栈里最强的一环,且**正好踩在业界方向上**:agent 发声明式 JSON,客户端(Gosling 渲染器)是渲染权威。恶意/畸形的 Gosling spec 最多画出一张烂图,不能执行代码。`render_gosling` + `patch_gosling` 本质上就是 A2UI 的 `surfaceUpdate` + JSON-Patch `dataModelUpdate`。

### 1.3 缺什么(本方案要补的)

| 缺口 | 现状 | 对标 | 影响 |
|------|------|------|------|
| **状态回环** | agent 对 UI 只写;用户刷选/点击/选区不回流 | A2UI `userAction` 通道;pantheon `report_state` + `Future`;OpenAI `ui/update-model-context` | agent 看不到用户做了什么,无法"接着用户的操作往下分析" |
| **后端非状态权威** | view 状态散在前端 Zustand,刷新/重连即丢,agent 读不到 | pantheon:后端 `LiveViewSession.state` 是唯一真相源 | agent 无法 `get_state` 查看当前视图;重连丢状态 |
| **固定 artifact 词汇** | 每个新 UI 想法都要加一个 artifact_type + handler | A2UI/assistant-ui:一个声明式组件树 over 白名单组件集 | 无法"组合现有组件拼出新布局";扩展性受限 |
| **patch 格式不统一** | 只有 `gosling_patch` 一处增量更新 | AG-UI:全量统一用 RFC 6902 JSON-Patch | 增量更新无统一协议,无 snapshot/delta 对账 |
| **无前端自检回灌** | agent 发完 artifact 不知道前端有没有渲染成功 | pantheon:diagnostics + 截图 inline 回 tool_result | agent 无法发现"画崩了"并自我纠正 |
| **codegen 仅限后端数据** | `write_analysis_function` 只产出后端 DataFrame endpoint | MCP Apps/OpenAI:agent 写的 UI 跑在 sandboxed iframe | agent 不能产出"后端 catalog 表达不了的全新可视化" |

---

## 2. 调研发现总结

### 2.1 Pantheon LiveView 的 6 条具体借鉴

来自代码阅读 `pantheon-agents/pantheon/toolsets/live_view/` + `pantheon-ui/src/components/live-view/`:

1. **后端是 view state 的单一真相源;agent 和 UI 都是它的客户端。**
   - `LiveViewSession.state`(`toolset.py:60-93`)保存权威状态字典。agent 用 `live_view_update`/`set_state` 改它 + 广播 delta;用户交互的新状态 POST 回 `report_view_state` 覆写它(`toolset.py:638-658`);agent 用 `get_state` 查看(`toolset.py:418-444`)。
   - **对 U-Chrom**:不能让 Zustand 是真相源——它重连就丢,agent 读不到。要在后端 ws_handler 持有每个 view 的 state dict。

2. **"不透明 state + 可加载 JS 模块"取代固定组件枚举。**
   - agent 调 `open_live_view(view_type="vitessce")`→解析 `skills/live_view/vitessce/adapter.js`;或 `view_type="custom" + module_url=...`→agent 自己写的 JS。state 是该模块定义的不透明 JSON(Vitessce 的 state 是 Vitessce view config,RDKit 的是 `{molecules, draw_options}`)。后端只知道 deep-merge,不解释语义。
   - **对 U-Chrom**:保留一个小 registry(gosling/embedding/structure 等受信 viewer,各自消费特定 JSON state schema);同时开逃生舱(`view_type="custom"`)让 agent 发自己写的 JS module。结构表本身是天然的"不透明 state payload"。

3. **统一的递归 deep-merge patch 原语,三处字节级一致。**
   - `_deep_merge`(backend `toolset.py:48-56`)+ `deepMerge`(SDK `live-view-sdk.js:46-57`)+ `deepMerge`(store `liveView.ts:22-35`)。`live_view_update(patch)` 语义无歧义。
   - **对 U-Chrom**:把 `gosling_patch` 推广到所有 view,统一用 RFC 6902 JSON-Patch(AG-UI 的选择)+ 一个后端/前端都实现的 `applyPatch` 函数。

4. **复用同一条流通道,按事件类型前缀分流。**
   - `live_view.*` 和聊天 token chunks 走同一条 NATS `chat_<chat_id>` subject,`StreamingManager.ts:180` 按 `type.startsWith('live_view.')` 分支(`toolset.py:121-133`发布时加前缀)。不开第二条 socket。
   - **对 U-Chrom**:在现有 WebSocket 上加 `{type: "view.open"|"view.patch"|"view.event", ...}` 消息族,与 `agent_message`/`agent_artifact` 共享一条连接。

5. **action/screenshot 用 pending-futures map + request_id,让工具能"阻塞等 UI 结果"。**
   - `live_view_call`/`screenshot`(`toolset.py:374-416`, `446-495`)创建 `asyncio.Future`,发带 `action_id`/`request_id` 的消息,`await asyncio.wait_for(future, 30s)`;UI 的 `report_action_result`/`report_snapshot` resolve 它(`toolset.py:660-713`)。
   - **对 U-Chrom**:新增工具 `query_user_selection(prompt)` / `capture_view_snapshot(view_id)`,用 `dict[str, Future]` + 超时等待。让 agent 能"问用户选了哪块区域"→阻塞等回答→拿 tool_result。

6. **前端 diagnostics + 截图回灌 tool_result,让 agent 自检。**
   - iframe 的 console 错误、uncaught exception 转成 `{t:'diag', level, message}`(`app-host.html:82-116`)回传;WebGL/canvas 视图自己 hook `lv.onSnapshot()` 把 `toDataURL()` 返回(`live-view-sdk.js:180-188`)。`open_live_view` 的 tool_result 包括 `status: "ready"|"error"` + `diagnostics`(`toolset.py:290-307`);`screenshot` 的 tool_result 内联 data URL(`toolset.py:525-546`)。
   - **对 U-Chrom**:React error boundary 的错误 + Gosling 渲染失败转成消息回传;3D structure viewer(PyVista/WebGL)的截图回灌。对 vision 模型(Opus 4.8)用处巨大:agent 真的"看到"它画的染色质结构,发现歪了能自己改。

### 2.2 A2UI 业界实践的关键收敛

来自 web 调研 A2UI/AG-UI/Vercel/MCP/OpenAI/assistant-ui/Adaptive Cards:

**核心共识**:

- 业界站在两个安全极,**刻意不做"在主 realm 里 eval agent 代码"**。极1 = 声明式组件树 + 宿主 catalog(A2UI、assistant-ui、Adaptive Cards);极2 = agent 代码隔离 iframe(MCP Apps、OpenAI)。
- **agent 不写直接操作 DOM 的 markup**。声明式阵营中,agent 发的是"描述意图的数据",客户端拥有 widget registry 并是渲染权威。A2UI spec 明确说 catalog 编译进服务器"to prevent malicious content being injected into the prompt dynamically"——这是最重要的安全属性。
- **allowlist/catalog 是安全边界**。assistant-ui 遇到未知组件名直接 reject + 类型化报错;A2UI 用 `catalogId` 版本化 catalog;Adaptive Cards 校验 schema。未知→抛出,绝不渲染。
- **codegen 灵活性=iframe 隔离成本**。愿意让 agent 写任意 UI 的(MCP Apps、OpenAI)都用**独立 origin sandboxed iframe + 严格 CSP + 窄 postMessage/JSON-RPC 桥**。没有生产系统在自己 app context 里 `eval()` agent 的 React——代价(XSS、token 泄漏、DOM 访问)太高。
- **声明式故意限制表达力**。A2UI 的 bindings **刻意无 transformers/conditionals/formatters**,所有逻辑在服务端算完再发 `dataModelUpdate`。这让渲染器保持"笨"和安全。代价:catalog 外的新奇 UI 表达不了,除非扩展 catalog(改代码)。
- **状态回流模式:交互→结构化事件→agent 工具/turn**,绝不共享可变状态。A2UI 用独立 `userAction` 通道;AG-UI 用 JSON-Patch state delta + tool results;MCP/OpenAI 把 UI 发起的调用路由成 **UI-initiated tool calls** 回 host。对 tool-loop agent,正确模式是:**用户交互变成合成的 tool result 或新 user message**,让模型留在环里。
- **streaming:ID-referenced 平铺 list 或 RSC**。A2UI 用平铺邻接表 + `beginRendering` gate,组件可以乱序流入不 flash;Vercel 流真正的 RSC。避免逐 token 生成嵌套树(LLM 产出畸形 partial JSON)。
- **hybrid = emerging norm**。A2UI 明确定义了"MCP Apps in A2UI surface"([guide](https://a2ui.org/guides/mcp-apps-in-a2ui-surface/))——声明式覆盖 90% 常见场景,sandboxed iframe 逃生舱应对任意的 10%。**这个两层模型最贴合我们需求**。

**对 U-Chrom 的直接建议**(业界调研报告原文):

> 你现有设计已对齐安全声明极。**不要转向在主 realm 里跑 agent 写的 React/JS**。采纳"声明式优先 + sandboxed iframe 逃生舱"两层模型。
>
> **KEEP**:(1) typed-artifact + `ARTIFACT_HANDLERS` dispatch map(就是 A2UI Catalog/assistant-ui allowlist);(2) Gosling/Vega-Lite 声明式 spec 做主力 UI 词汇;(3) tool-loop / WebSocket 往返。
>
> **ADD**:
> 1. **正式的状态往返**(最高优先级,当前最大缺口)。用户在渲染 UI 里的交互回流成**结构化事件→tool result 或合成 turn**。定义一个入站消息类型 `ui_event { source_artifact_id, event_name, payload }`(embedding 上的刷选/套索、点击的 TAD、选中的基因组区间)。后端把它注入成 pending tool call 的结果或作为下轮模型 turn 的上下文。这是 A2UI `userAction` 通道 + OpenAI `ui/update-model-context`。没这条 agent 对 UI 就是"只写"。
> 2. **从 N 个硬编码 artifact 类型泛化到一个小的声明式"布局/组件" artifact**。不再每个 UI 想法加一个 artifact 类型,而是加**一个** `render_component` artifact,携带约束的**声明式节点树**(仿 assistant-ui `GenerativeUISpec` / A2UI 平铺 list)over **白名单 U-Chrom 组件集**:`Panel`、`Row/Column`、`Text`、`Button`、`Slider`、`Select`、`GoslingView`、`EmbeddingView`、`StructureView`、`Table`。agent 组合现有 widget 成新布局——真正"生成自己的 UI"——但每个叶子都解析到你 handler map 里审查过的 React 组件。bindings **仅限字面量或数据路径,无表达式**(A2UI 的刻意限制),所以没有逻辑可被利用。这给你 ~90% 的"generative UI"能力,零任意代码执行。
> 3. **采纳 JSON-Patch(RFC 6902)作为 patch 有线格式**。你已有 `gosling_patch`;把*所有*增量更新标准化到 RFC 6902 like AG-UI `StateDelta`,泛化到 component/data-model patch。让 Zustand 更新精准,给你 snapshot/delta 对账故事(不一致时请求 fresh snapshot)。
> 4. **预留 sandboxed-iframe 逃生舱做真正的 codegen——且仅在那**。罕见的 agent 必须产出 catalog 真表达不了的全新 UI/viz(e.g. `write_analysis_function` 产出自定义 plot)时,把它渲染在 **sandboxed `<iframe sandbox="allow-scripts">` on 独立 origin + 严格 CSP**,仅通过**窄 `postMessage` 桥**(`request_data`、`emit_ui_event` 白名单消息类型)与 parent 对话。这正是 MCP Apps / OpenAI Apps 模型。**绝不** `eval` agent 代码或 `dangerouslySetInnerHTML` agent markup 在主 React 树里——那会暴露你的 WebSocket session、tokens、整个 DOM。iframe 是灵活性的代价;只在声明层真不够用时才付。
> 5. **streaming:gate 首次绘制**。如果你流大 Gosling spec 或组件树,采纳 A2UI `beginRendering` 思路:缓冲 artifact 片段,根 + 引用子节点都到了再渲染,避免半画的面板。对当前离散 artifact 这不紧迫,但一旦加 `render_component` 树就重要了。

---

## 3. 目标架构:三层 A2UI 模型

```
┌───────────────────────────────────────────────────────────────┐
│  Tier 1: 领域声明式 spec(现有,继续深耕)                      │
│                                                               │
│  render_gosling / patch_gosling                               │
│  color_embedding / color_structure                            │
│  show_structure / export_view                                 │
│                                                               │
│  特征: agent 发 Gosling/embedding config JSON,前端            │
│        Gosling.js/Canvas 渲染器是权威;无代码执行             │
│  安全: 恶意 spec 最多画错图,不能 XSS                         │
│  优先: 主力;80% 用例在这层解决                               │
└───────────────────────────────────────────────────────────────┘
                              ↓ 不够用时才下探
┌───────────────────────────────────────────────────────────────┐
│  Tier 2: 可组合组件树(新增,实现"generative UI")              │
│                                                               │
│  render_component(spec: ComponentTreeSpec)                    │
│                                                               │
│  spec = 声明式节点树 over 白名单组件:                        │
│    Panel, Row, Column, Text, Button, Slider, Select,         │
│    GoslingView, EmbeddingView, StructureView, Table          │
│                                                               │
│  特征: agent 拼装新布局(两列对比、多面板、参数控制面板),     │
│        但每个叶子都解析到 ARTIFACT_HANDLERS 里受信的         │
│        React component;bindings = literal | dataPath,无表达式│
│  安全: 白名单是边界;未知组件名→reject + 报错给 agent        │
│  优先: 声明层表达不了的 layout 需求在这层满足               │
└───────────────────────────────────────────────────────────────┘
                              ↓ 极罕见
┌───────────────────────────────────────────────────────────────┐
│  Tier 3: sandboxed iframe 逃生舱(新增,审慎使用)              │
│                                                               │
│  render_custom_view(view_id, html_code, js_code)             │
│                                                               │
│  特征: agent 写任意 HTML/JS(e.g. 全新可视化算法、             │
│        三方库 demo);跑在 <iframe sandbox="allow-scripts">    │
│        独立 origin + 严格 CSP;仅通过 postMessage 桥通信      │
│  安全: 浏览器沙箱隔离;iframe 读不到 parent 的 WebSocket/    │
│        tokens/cookies;白名单 postMessage 类型               │
│  优先: 最后手段;catalog 真的表达不了时才用                  │
└───────────────────────────────────────────────────────────────┘
```

**层间规则**:
- **默认在 Tier 1 解决**。Gosling 声明式栈非常强,且对基因组学天然契合。
- **layout 组合→Tier 2**。agent 想"左边 embedding 右边 structure,下面参数滑块"→用 `render_component`。
- **全新算法/viz→Tier 3**。agent 要画个 catalog 没的(e.g. 力导向图、自定义 WebGL shader)→iframe 逃生舱。
- **绝不在主 realm eval agent 代码**。

---

## 4. 具体实施方案(三个阶段)

### 阶段 0:状态回环 MVP(最高优先级)

**目标**:让 agent 能"看到"用户在 UI 里做了什么,闭合"agent → UI → 用户 → agent"循环。

#### 4.0.1 后端持久化 view state

在 `ws_handler.py` 或新增 `view_manager.py`:

```python
@dataclass
class ViewSession:
    view_id: str
    view_type: str  # "gosling" | "embedding" | "structure" | "component" | "custom"
    state: dict     # 权威状态,JSON-serializable
    created_at: float
    last_updated: float

# 全局(或 per-WebSocket connection)
view_sessions: dict[str, ViewSession] = {}
```

修改现有 executors:
- `render_gosling`:创建 `ViewSession`,state 初始化为发出的 spec;返回 `view_id`。
- `patch_gosling`:deep-merge patch 到 `view_sessions[view_id].state`,更新 `last_updated`。
- 新增工具 `get_view_state(view_id) -> dict`:agent 能查当前状态(看用户改了什么)。

#### 4.0.2 前端报告状态变化

定义新的入站 WebSocket 消息类型 `ui_event`:

```typescript
// frontend → backend
{
  type: "ui_event",
  source_view_id: string,
  event_name: "brush_selection" | "region_click" | "cell_selection" | "parameter_change",
  payload: any  // 具体到 event_name:{chrom, start, end} | {cell_ids: [...]} | {param_name, value}
}
```

`ws_handler.handle_message` 加分支:

```python
elif msg_type == "ui_event":
    view_id = data["source_view_id"]
    if view_id in view_sessions:
        # 选项 A:直接覆写 view state 的某个 key
        view_sessions[view_id].state["last_interaction"] = {
            "event": data["event_name"],
            "payload": data["payload"],
            "timestamp": time.time()
        }
        # 选项 B:排队成"pending user action",下次 agent turn 时注入 system message
        # (取决于你想 agent 主动轮询还是被动接收)
```

前端:Gosling 的 `onBrushSelection`、embedding canvas 的 lasso、structure viewer 的 click 回调都发 `ui_event`。

#### 4.0.3 新增 agent 工具:`query_user_interaction`

```python
@register("query_user_interaction")
async def executor_query_interaction(websocket, tool_input):
    """Block and wait for the next user interaction on a view, or return the last one."""
    view_id = tool_input["view_id"]
    timeout = tool_input.get("timeout_seconds", 30)
    
    # 实现 A:返回 view_sessions[view_id].state["last_interaction"] 如果有
    # 实现 B(阻塞):创建 asyncio.Future,记到 pending_interactions[view_id] = future,
    #            等前端下次 ui_event 时 resolve;await asyncio.wait_for(future, timeout)
    ...
    return json.dumps({"event": ..., "payload": ...})
```

tool schema 暴露给 agent:

```python
{
  "name": "query_user_interaction",
  "description": "Get the last user interaction (brush, click, selection) on a view, or wait for the next one.",
  "input_schema": {
    "type": "object",
    "properties": {
      "view_id": {"type": "string"},
      "timeout_seconds": {"type": "number", "default": 30}
    },
    "required": ["view_id"]
  }
}
```

**验收**:agent 能执行流程:
1. `render_gosling(...)` → 拿到 view_id
2. 用户在前端刷选一块区域
3. agent 调 `query_user_interaction(view_id)` → tool_result 返回 `{chrom: "chr1", start: 1000000, end: 2000000}`
4. agent 据此 `run_analysis` 或 `patch_gosling` 聚焦该区域。**这就闭合了 agent↔用户的循环。**

> **设计选择**:阻塞式(`Future` + 超时,仿 pantheon `live_view_call`)适合"agent 主动问、等用户答";被动式(state 里记 `last_interaction`,agent 下轮读)适合"用户随便操作、agent 顺势而为"。建议**两者都提供**:`query_user_interaction(wait=true/false)`。

---

### 阶段 1:统一 patch 协议 + 后端 state 权威

**目标**:把零散的增量更新统一到 RFC 6902 JSON-Patch,所有 view 类型共用一套 state 同步机制。

#### 4.1.1 统一 patch 原语(三处一致)

仿 pantheon 的"deep-merge 三处字节级一致",我们用 RFC 6902:
- 后端:`jsonpatch` 库(Python)apply 到 `ViewSession.state`。
- 前端:`fast-json-patch`(TS)apply 到 Zustand store。
- 协议:`{type: "view.patch", view_id, patch: [{op, path, value}, ...]}`。

把现有 `patch_gosling` 重构成发 RFC 6902 patch,而非自定义 merge 格式。

#### 4.1.2 snapshot/delta 对账

- 每个 `view.patch` 带递增 `revision` 号。
- 前端检测到 revision 跳号(丢包/重连)→ 发 `{type: "view.request_snapshot", view_id}` → 后端回 `{type: "view.snapshot", view_id, state, revision}` 全量覆盖。
- 这给重连和并发更新一个对账故事(A2UI / AG-UI 都有)。

**验收**:刷新页面 / 断线重连后,前端能从后端 `ViewSession.state` 重建所有 view(不再丢状态)。

---

### 阶段 2:Tier 2 可组合组件树 + Tier 3 iframe 逃生舱

#### 4.2.1 Tier 2:`render_component` 工具

新增**一个**工具,取代"每个 UI 想法加一个 artifact 类型":

```python
COMPONENT_TREE_SCHEMA = {
  "name": "render_component",
  "description": "Compose a layout from whitelisted U-Chrom UI components. "
                 "Use when you need a custom arrangement (multi-panel, side-by-side "
                 "comparison, parameter controls) beyond a single chart.",
  "input_schema": {
    "type": "object",
    "properties": {
      "view_id": {"type": "string"},
      "tree": {"$ref": "#/$defs/node"}
    },
    "$defs": {
      "node": {
        "type": "object",
        "properties": {
          "component": {
            "type": "string",
            "enum": ["Panel", "Row", "Column", "Text", "Button", "Slider",
                     "Select", "GoslingView", "EmbeddingView", "StructureView", "Table"]
          },
          "props": {"type": "object"},   # 仅 literal | {"$dataPath": "..."},无表达式
          "children": {"type": "array", "items": {"$ref": "#/$defs/node"}}
        },
        "required": ["component"]
      }
    }
  }
}
```

前端 `artifactHandlers.ts` 加一个 `component_tree` handler + 一个**递归渲染器** `<ComponentRenderer node={tree} />`:
- 每个 `component` 名查 `COMPONENT_REGISTRY: Record<string, React.FC>`(白名单)。
- **未知组件名 → 不渲染,回报错给 agent**(assistant-ui 的安全边界)。
- `props` 里 `{"$dataPath": "spots.chr1.x"}` 解析到 store 数据;其余是字面量。**无表达式求值。**
- `GoslingView`/`EmbeddingView`/`StructureView` 复用 Tier 1 已有的渲染组件——组件树只是"编排"它们。

**关键安全属性**:agent 拼装的是受信 React 组件的*布局*,不是代码。最坏情况是布局难看,不能 XSS。

#### 4.2.2 Tier 3:`render_custom_view` sandboxed iframe

仅当 Tier 1/2 真表达不了(全新算法/可视化)时:

```python
{
  "name": "render_custom_view",
  "description": "LAST RESORT. Render agent-authored HTML/JS in a sandboxed iframe. "
                 "Use only when no declarative component can express the visualization.",
  "input_schema": {
    "type": "object",
    "properties": {
      "view_id": {"type": "string"},
      "html": {"type": "string"},
      "data_url": {"type": "string"}  # 复用 /api/custom/ endpoint 喂数据
    }
  }
}
```

前端:
```tsx
<iframe
  sandbox="allow-scripts"              // 注意:不加 allow-same-origin
  src={`${SANDBOX_ORIGIN}/custom-host.html`}  // 独立 origin!
  // 严格 CSP via 该 origin 的响应头
/>
```

桥接(窄 postMessage 白名单):
- iframe → parent:`{__uc: 1, t: "request_data"}`、`{__uc: 1, t: "ui_event", event, payload}`
- parent → iframe:`{__uc: 1, t: "data", payload}`、`{__uc: 1, t: "state", state}`
- **拒绝一切其他消息类型。**

> ⚠️ **安全红线**(两份调研一致强调):
> - **独立 origin**(不同端口/子域),否则 `allow-same-origin` + agent JS = 完全访问你的 cookies/localStorage/WebSocket。
> - **不给 `allow-same-origin`**(除非配独立 origin 且明白后果)。
> - **严格 CSP**:`default-src 'none'; script-src 'self' https://esm.sh; connect-src 'self'`。
> - **绝不** `eval` / `dangerouslySetInnerHTML` agent 代码到主 React 树。
> - pantheon 的 `sandbox="allow-scripts allow-same-origin"` + 加载 esm.sh/unpkg(`LiveViewFrame.vue:150`, `app-host.html:61-72`)**不要原样照抄**——它的 same-origin 姿态对我们是风险,因为我们要保护 WebSocket session 和数据。

#### 4.2.3 前端自检回灌(贯穿三层)

仿 pantheon 的 diagnostics + screenshot:
- React error boundary 包住每个 view,捕获渲染错误 → 发 `{type: "view.diagnostic", view_id, level: "error", message}` → 后端记到 `ViewSession`,下次 agent `get_view_state` 能看到。
- 新增工具 `capture_view_snapshot(view_id)`:前端把 Gosling canvas / 3D structure 的 `toDataURL()` 通过 `Future` 回传,inline 进 tool_result。**对 Opus 4.8(vision)**:agent 真的"看到"自己画的染色质结构,发现歪了能改。

---

## 5. 工具清单演进

| 工具 | 层 | 状态 | 说明 |
|------|----|----|------|
| render_gosling / patch_gosling | T1 | 已有 | patch 改用 RFC 6902(阶段1) |
| color_embedding / color_structure | T1 | 已有 | — |
| show_structure / export_view | T1 | 已有 | — |
| select_cells | T1 | 已有 | — |
| run_analysis | T1 | 已有 | 结构识别 registry 分发 |
| write_analysis_function | T1/T3 | 已有 | 现仅产后端 endpoint;可接 T3 出 iframe viz |
| add_notebook_cell | — | 已有 | — |
| **query_user_interaction** | 回环 | **新增(阶段0)** | 拿/等用户交互 → tool_result |
| **get_view_state** | 回环 | **新增(阶段0)** | agent 查 view 当前状态 |
| **render_component** | T2 | **新增(阶段2)** | 白名单组件树编排 |
| **render_custom_view** | T3 | **新增(阶段2,慎用)** | sandboxed iframe 逃生舱 |
| **capture_view_snapshot** | 自检 | **新增(阶段2)** | 截图回灌(vision 自检) |

---

## 6. 与现有重构的衔接

本方案完全建立在本轮已完成的重构 A+B 之上:
- **后端 `TOOL_EXECUTORS` 注册表**:新增 `query_user_interaction`/`get_view_state`/`render_component`/`render_custom_view`/`capture_view_snapshot` 只是 `@register(...)` 加几个 executor,`run_agent_loop` 一行不改。
- **前端 `ARTIFACT_HANDLERS` map**:新增 `component_tree`/`custom_view`/`view_patch`/`view_snapshot` handler 即可,ChatPanel 不改。
- **一致性测试** `test_tool_executors.py::test_every_tool_has_an_executor`:新工具漏注册会立刻红灯。

注册表重构(B)正是让本方案"加工具不改循环"的前提。

---

## 7. 风险与权衡

| 风险 | 缓解 |
|------|------|
| Tier 3 iframe 是真实攻击面 | 独立 origin + 严格 CSP + 窄 postMessage 白名单;默认不开,仅 catalog 不够时启用 |
| 后端 view state 内存增长 | per-connection 生命周期,断开清理;或 LRU + 落盘 |
| 阻塞式 `query_user_interaction` 占住 agent loop | 超时(仿 pantheon 30s)+ 默认被动式 |
| 组件树 props 注入 | 仅 literal | dataPath,无表达式求值;dataPath 白名单校验 |
| RFC 6902 迁移破坏现有 gosling_patch | 阶段1 单独做,有测试覆盖再切 |

---

## 8. 落地顺序建议

1. **阶段 0(状态回环)**——最高价值/最低风险,先做。让 agent 从"只写 UI"变成"看得见用户操作"。
2. **阶段 1(统一 patch + state 权威)**——打基础设施,重连不丢状态。
3. **阶段 2(T2 组件树 + T3 iframe + 自检)**——真正的"generative UI"能力,按需推进;T3 最后做且默认关。

每个阶段都应:真实数据端到端验证(遵循 CLAUDE.md 验证纪律),补 `test_tool_executors.py` 单测,前端 `tsc --noEmit` + `npm run build` 过关。

---

## 附:两份调研一句话结论

- **pantheon LiveView**:后端持权威 state,agent/UI 都是客户端;"不透明 state + 可加载模块"+ 统一 deep-merge patch + Future 式 action 回环 + diagnostics/截图自检。其 same-origin iframe 姿态**不可照抄**。
- **A2UI 业界**:收敛到"声明式白名单 catalog"与"sandboxed iframe"两极,回避主 realm eval;hybrid 两层(声明式 90% + iframe 逃生舱 10%)是 norm。我们的 `ARTIFACT_HANDLERS` + Gosling 已在正确的安全极上。

---

## 9. 实现进度(2026-06-11 已落地)

本节记录方案中**已实现并验证**的部分(分支 `feat/phase0-viewer-integration`)。

### P0 缺陷修复 ✅
- **notebook_cell 前端静默丢弃**:后端改走 `agent_artifact` 通道,前端 `ARTIFACT_HANDLERS` 加 `notebook_cell` handler(写入 `store.notebookCells` + 切到 Notebook tab)。
- **patch_gosling 先发后校验**:改为先校验 `target_id`/`patch.path`,非法直接返回 error,不再向前端发出无效 artifact。

### 阶段1:后端 view-state 权威 + 重连恢复 ✅
- `session.py` 新增 `ViewSession`(view_id/view_type/state/revision)+ `_deep_merge` + `Session.views` 注册表 + `get_or_create_view`。
- `render_gosling` 写入 ViewSession(`replace`),`patch_gosling` 通过 `_apply_json_patch_to_view` 同步后端权威 spec 并 bump revision。
- **重连恢复**:客户端自持 `session_id`(localStorage),总是带 `?session_id=` 连接;后端已知 id 则复用 session(恢复 history + chromdata + views),空 session 断开即清理、有状态 session 进入 30min grace window(惰性 sweep,无泄漏)。
- 协议:`view.request_snapshot` → `view.snapshot`(全量 view 重建);前端 `store.hydrateViews` 接住,重建 gosling artifacts + component tree。

### 阶段2-A:状态回环 ✅(设计文档列为最高优先级缺口)
- `ws_handler` 新增 `ui_event` 入站分支:把用户交互(brush/click/select)记到 `ViewSession.state.last_interaction`,并 resolve 阻塞中的 Future。
- 新增 `wait_for_interaction` + `_pending_interactions` futures map(仿 pantheon `live_view_call`)。
- 新增 agent 工具 **`get_view_state`**(读后端权威 view 状态)与 **`query_user_interaction`**(wait=false 读最近一次 / wait=true 阻塞等下一次,带超时)。
- 前端 `GoslingRenderer` 在用户手动 pan/zoom 时发 `ui_event{brush_selection}`。**agent 从"只写 UI"变成能看见用户操作。**

### 阶段2-B:Tier2 可组合组件树 ✅
- 新增 agent 工具 **`render_component`**:声明式节点树 over 白名单组件(Panel/Row/Column/Text/Table/Button/Slider/Select/GoslingView/EmbeddingView/StructureView)。
- 后端 `_validate_component_tree` 双重校验(未知组件名 reject + 节点数上限 200),前端 `ComponentRenderer.tsx` 递归渲染 + `COMPONENT_REGISTRY` 白名单,未知组件渲染可见错误而非任何代码;props 仅 literal | `{$dataPath}`,无表达式求值。
- TabContainer 在有组件树时显示 "Custom" tab。

### Tier3 sandboxed iframe ⏸️ 未实现
按方案定位为"最后手段",默认关闭。Tier1/2 已覆盖绝大多数需求,暂不引入 iframe 攻击面。待出现 catalog 真表达不了的需求时再按 §4.2.2 落地。

### 验证
- 后端:**282 passed**(新增 8 个 view-state/回环/组件树单测;`test_every_tool_has_an_executor` 锁定 13 工具一致)。
- 前端:`tsc --noEmit` 干净,`npm run build` 成功(消除了 dynamic/static import 警告)。
- 回归:WS 重连改动一度引入 17 个回归(协议首帧 + cleanup 不变量),已通过"客户端自持 session_id + 空 session 即清理"重新设计修正;测试中编码旧契约的断言(notebook_cell 旧的 `type:"artifact"`、2-arg `run_agent_loop` fake)已更新为新契约。

### 已知遗留(非本次范围)
- **~~流式~~**(§4 阶段债):~~loop 仍用阻塞 `messages.create`;模型硬编码 `claude-sonnet-4-6`(未抽 config)~~ **已修复**(2026-06-11):改用 `messages.stream` 实时流式 + `agent_message_delta`;模型抽取为 `DEFAULT_MODEL` 常量,可通过 `UCHROM_MODEL` 环境变量或 `model` 参数覆盖。
- **~~`agui_events.py`~~**:~~仍是未接线死代码(含第二份不一致 TOOLS),建议后续删除或明确标注为 AG-UI 迁移预留。~~ **已删除**(2026-06-11):连同 `test_agent_pipeline.py` 一起移除;`test_integration.py` 中的 AG-UI 协议测试类删除,`test_ws_backend.py` 中的 agui 单测移除。
- **前端自检回灌**(diagnostics + 截图):未实现,留待引入 vision 自检时。
