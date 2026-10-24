# 本地 Agent 接管 U-Chrom WebUI 设计规格

日期：2026-10-22
状态：按 2026-10-23 用户流程澄清和 UX 复审修订；local-first 为默认产品链路，Worker token relay 为可选增强
范围：Atlas、托管 WebUI、本地 WebUI、本地 companion、用户自己的 Claude Code / Codex

## 1. 设计结论

主流程采用“公网页面给出本地启动命令和 agent 指令，用户在自己的机器启动 WebUI，自己的 Claude/Codex 通过本地 MCP 操作页面”。启动本地 WebUI 不依赖 Wrangler、Cloudflare Worker 或公网 handoff API。

    Atlas / 托管 WebUI
            │ 用户点击“在本地继续”
            ▼
    页面本地生成：启动命令 + 问题 + 可选语义快照
            │ 用户复制并运行命令；把指令粘贴到本地 agent
            ▼
    本地 U-Chrom WebUI ←── 本地 companion / stdio MCP
            ▲
            │ live action + canonical state readback
            ▼
    用户自己的 Claude Code / Codex

网页只展示或复制用户本机要运行的命令和 prompt，不启动用户电脑上的进程，不向 U-Chrom 服务上传页面状态，也不要求一次性 token。用户运行命令启动本地页面后，agent 从本地 MCP 重新读取 canonical state；Hosted 页面快照只是迁移建议，必须和本地 state 比较后再提变更计划。

旧版设计中的 Worker + Durable Object one-time token 方案保留为可选 relay：只有当明确需要缩短大状态复制内容、统一跨站一次性领取等能力时才启用；它不是 Atlas → 本地 WebUI 主流程的前置服务。

Chrome DevTools MCP 不作为 MVP 的主链路。它可以作为后续增强，用于用户只想让 agent 直接调整当前浏览器标签页、且浏览器已启用 WebMCP 的场景；它不承担本地 Python 分析、数据下载、页面状态迁移或本地服务启动。

### 1.1 重新设计的产品目标

**目标：** 用户在 Atlas 或托管 WebUI 看到感兴趣的数据后，用自己的 Claude Code 或 Codex 在本机分析同一数据，并通过本地 MCP 让本地 WebUI 显示经过用户确认的结果；页面、agent 和分析使用的范围必须以 canonical readback 为准。

**默认链路的成功条件：**

- 公网页面只提供安装说明、本机启动命令和 MCP 指令；启动本地 WebUI 不依赖 Wrangler、Cloudflare Worker 或公网 handoff API。
- 首次用户能完成“安装 companion → 配置 MCP → 启动本地 WebUI → 粘贴指令 → 在页面 Apply”；每一步都有明确状态和失败提示。
- 默认 prompt 只携带 dataset reference、问题和状态摘要，不把完整 cell ID 列表直接送进模型上下文；用户明确选择后才能附加 canonical cell IDs，超过 1 MiB UTF-8 时拒绝生成且不截断。
- 本地 agent 必须先读取页面 canonical state，再提出带 `page_id` 和 `state_revision` 的计划；页面 mutation 只能由用户在 Agent 面板批准。
- `attach_handoff(token)` 只属于可选 relay/本地 JSON 导入能力，不能成为默认步骤。

**产品取舍：** local-first 优先保证隐私边界、私有数据和本地 Python 分析能力；可验证的安装/分发是面向普通 Atlas 用户的前置产品工作。Worker relay 只在减少大状态复制、跨站一次性领取或企业受控部署确有收益时启用。

## 2. 为什么采用本地 continuation

用户的目标不是单纯“让模型点击页面”，而是：

1. 在 Atlas 或托管 WebUI 发现一个感兴趣的数据集；
2. 让自己的 Claude/Codex 使用本地 Python、Notebook、文件和已有环境分析；
3. 让分析结论直接反映到 WebUI 的 selection、locus、Stats、view 和 rendering 配置；
4. 页面显示的状态、agent 看到的状态和分析使用的状态保持一致。

本地 continuation 避免以下问题：

- 托管页面不能静默启动用户电脑上的进程；
- 托管服务不应获得用户本地文件和 Python 环境权限；
- 浏览器级调试连接可能覆盖整个 Chrome profile，权限过宽；
- WebMCP 是页面内工具注册机制，不是 Claude/Codex 的跨机器 MCP transport；
- 截图或 DOM 操作只能看到视觉状态，不能保证后端去重、裁剪和 scope 规则已经被正确应用。

### 当前实现与新增设计的边界

| 能力 | 当前状态 | 本设计中的变化 |
| --- | --- | --- |
| Atlas 将公开 dataset URL 打开到托管 WebUI | 已实现 | Atlas 增加 `Continue locally` 本地命令与 prompt |
| 本地 WebUI 从 URL 或 `.cdz` 打开数据 | 已实现 | companion 自动启动并打开指定 dataset |
| Python `uchrom_browser.connect()` 实时控制本地页面 | 已实现 | MCP wrapper 复用同一 action/control 通道 |
| 页面注册实验性 WebMCP 工具 | 已实现，需运行环境支持 | 保留为可选入口；不是本地 agent 的传输层 |
| hosted WebUI 向本机提供规范化状态 | 本地 prompt/clipboard 方式已实现 | 状态在浏览器客户端序列化，用户复制给本地 agent；超限时不截断 |
| Worker + Durable Object token relay | 可选实现，非主链路 | 为有需要的托管部署提供一次性 relay，不要求 Atlas 使用 |
| Claude/Codex 的通用本地 MCP companion | 未实现 | 新增安装、client 配置、session/page pin |
| Agent 面板、计划确认、状态 revision、撤销 | 未实现 | 按本规格新增 |

当前 checkout 中 `uchrom-browser` README 标注“not on PyPI yet”。因此 Atlas 和 Hosted WebUI 只显示从源码安装前置条件与本机启动命令，不显示未经验证的 `uvx` 命令。

Atlas 静态站点和 hosted-browser 虽是不同 origin，但主链路不跨 origin 传输状态：Atlas 已有 catalog URL，hosted WebUI 可从当前页面构造 prompt，内容由用户复制到本地 agent。Worker relay 只在显式启用的可选模式中承担精确 origin 校验、目录校验和短时 token 领取。

当前代码定位：Atlas 的数据卡片和本地命令在 [app.js](../../../apps/atlas/site/app.js)；Hosted WebUI 的本地命令和语义 prompt 在 [HostedHandoff.tsx](../../../packages/uchrom-browser/uchrom_browser/frontend/src/components/HostedHandoff.tsx)；本地页面启动和 Python client 在 [browser package](../../../packages/uchrom-browser/uchrom_browser/__init__.py) 与 [client.py](../../../packages/uchrom-browser/uchrom_browser/client.py)；SSE 控制 broker 在 [control.py](../../../packages/uchrom-browser/uchrom_browser/control.py)；共享页面动作和 WebMCP 注册分别在 [actions.ts](../../../packages/uchrom-browser/uchrom_browser/frontend/src/actions.ts) 与 [webmcp.ts](../../../packages/uchrom-browser/uchrom_browser/frontend/src/webmcp.ts)。Worker relay 代码是可选部署能力。

## 3. 目标与非目标

### 3.1 目标

- 用户从 Atlas 一步进入“在本地继续分析”。
- 本地 agent 能检查依赖、启动本地 WebUI、打开同一数据集。
- 托管页的状态以语义快照交接到本地页，而不是交接点击序列。
- Claude Code 和 Codex 使用同一套本地 MCP 工具协议。
- agent 可以读取当前页面状态、运行分析、提出变更计划、应用变更并回读结果。
- selection、locus、Stats scope、视图范围和页面实际展示保持一致。
- 所有改变页面的操作都可审计、可拒绝、可撤销或通过重新加载快照恢复。
- 首次安装、浏览器启动、MCP 连接、页面 pin、待确认计划和已应用结果均有可见进度状态。
- 默认交接是摘要模式；完整选择列表通过用户明确勾选或 `uchrom_export_selection` 文件导出获得。

### 3.2 非目标

- MVP 不让托管网页直接执行本地 shell 命令。
- MVP 不把现有 /api/control/* 暴露到公网。
- MVP 不要求 U-Chrom 托管 Claude、Codex 或其他模型。
- MVP 不实现多用户共享的远程 relay。
- MVP 不承诺恢复任意浏览器 UI 像素、滚动位置或点击历史。
- MVP 不把用户的 prompt、原始 cell ID 或分析结果上传到产品遥测。

## 4. 术语与职责

| 名称 | 职责 |
| --- | --- |
| Atlas | 数据集发现、论文/数据元数据展示、发起本地 continuation |
| Hosted WebUI | 远程预览、确认当前数据和页面语义状态；不连接本地 control SSE |
| Local WebUI | 真正被 agent 实时控制的页面，负责渲染和状态 canonicalization |
| Local companion | 本机小型进程；启动 WebUI、验证 handoff、提供 stdio MCP、绑定 page |
| Claude Code / Codex | 用户自己的推理和工具调用主体；负责分析和提出/执行页面调整 |
| Python / U-Chrom | 读取 ChromData、运行统计和结构分析、生成结果与 provenance |
| action | 通过 actions.ts 执行的一次页面语义操作 |
| snapshot | 当前 dataset、selection、locus、Stats scope、views 和渲染配置的语义状态 |
| analysis scope | 单次分析记录中固定的细胞/范围；不作为全局页面状态，且可以与临时浏览高亮不同 |

## 5. 用户界面设计

### 5.1 Atlas：数据卡片入口

每个数据集卡片保留当前入口，并增加一个次级操作：

    [Open in browser]  [Continue locally]  [Download .cdz]

Continue locally 是带本地设备图标的文字按钮。按钮旁显示：

> 在你的电脑上打开 U-Chrom，让 Claude Code 或 Codex 分析并调整页面。

点击后打开轻量对话框，包含：

- 数据集名称、论文、版本/更新时间；
- Atlas 入口只展示 dataset metadata；Atlas 页面没有托管页面状态，不显示“从当前页面带入”；
- 问题输入框，placeholder 为“告诉 agent 你想比较、定位或查看什么”；
- 一个主动作：生成本地 continuation，并分别复制安装/启动命令和 MCP 指令。
- 首次使用的本地 companion 安装说明，以及“未安装 → 已启动 → MCP 已连接 → 等待确认 → 已应用”的步骤清单。

复制内容由两部分组成：本机安装/启动命令，以及交给 Claude Code/Codex 的本地 MCP 指令。命令示例：

    uv pip install -e packages/chromdata -e packages/uchrom-browser -e packages/uchrom-agent
    python -m uchrom_browser '<dataset-url>'

用户从 Atlas 直接进入时，页面只生成 dataset URL、版本说明和问题；不伪造 selection 或 locus，也不调用 handoff API。

### 5.2 托管 WebUI：页面内入口

托管 WebUI 顶部增加轻量 Continue locally action，位置在 dataset switcher 附近，不放入 3D 画布内部。

点击后显示三步面板。

第一步：确认交接内容

    将交给本地 agent

    Dataset       Stevens sim_cell1
    Selection     12 cells · canonical IDs
    Locus         chr15:28,400,000–31,200,000
    Stats         Rg · locus chromosome
    Views         3D · Genome · Stats

    [编辑问题……]
    [生成本地 handoff]

第二步：在本机启动

    首次使用先在 U-Chrom checkout 中运行：

    uv pip install -e packages/chromdata -e packages/uchrom-browser -e packages/uchrom-agent

    每次使用再运行：

    python -m uchrom_browser '<dataset-url>'

第三步：交给本地 agent

    把页面生成的 prompt 粘贴到已配置 U-Chrom MCP 的 Claude Code 或 Codex。默认 prompt 只包含状态摘要；只有明确勾选时才包含 canonical cell IDs。

    [复制安装命令] [复制启动命令] [复制 MCP 指令] [完成]

Atlas/托管页面不探测 localhost。agent 完成 attach 后会在对话中回报本地 URL，用户切换到本地 WebUI。

### 5.3 本地 WebUI：agent 控制面板

本地 WebUI 在右侧 inspector 增加 Agent section。它是状态面板，不是聊天机器人；模型对话仍在用户自己的 Claude/Codex 界面中。

面板包含：

    Agent
    Connected: Claude Code
    Page: p7f3a91c2  [pin]
    Dataset: Stevens sim_cell1

    Current page state
    Selection   12 cells
    Locus       chr15:28.4–31.2 Mb
    Stats       Rg · locus
    Views       3D · Genome · Stats

    Last request
    Set Stats to locus chromosome and open Genome view
    Status      Applied 10:42:18

    [View action history] [Undo last agent change]

面板必须显示状态来源：page canonical、handoff imported 或 analysis result。不能把“agent 想要的状态”显示成“页面已经生效的状态”。

### 5.4 变更计划预览

任何组合变更先形成计划，不直接静默修改页面。计划显示在本地 WebUI 的 Agent section，由用户在当前页面确认：

    Claude Code proposes

    1. Analyze the current 12-cell selection
    2. Compare Rg between saved groups A and B
    3. Set locus to chr15:28.4–31.2 Mb
    4. Open Stats (Rg, locus chromosome)
    5. Open Genome view with distance and contact rows

    Will change the page: selection, locus, views, Stats scope

    [Apply changes] [Reject]

只读 action（describe、get_selection、list_groups、capture）无需确认；页面 mutation 必须在本地 WebUI 中点击 Apply。MVP 不提供自动执行 mutation 的开关。涉及 shell、依赖安装、数据下载和文件写入的操作仍由 Claude/Codex 客户端的授权机制处理。

## 6. 完整用户交互流程

### 6.1 首次安装与每次 handoff

首次安装只做一次：

1. 用户从官方安装说明安装本地 companion。正式发布前，使用仓库开发环境，不显示未经验证的 `uvx` 安装命令。
2. 用户运行 setup，选择 Claude Code、Codex 或两者；setup 展示将新增的 MCP 配置，用户同意后才写入客户端配置。
3. 用户重启 Claude Code/Codex，让客户端启动 companion 的 stdio MCP server。
4. 用户调用 `uchrom_setup_status` 确认 MCP server ready。本地 WebUI 此时可以尚未启动。

每次从 Atlas 或托管 WebUI 继续：

1. 用户从 Atlas/Hosted 页面查看安装说明和状态摘要，决定是否附加 canonical cell IDs。
2. 用户首次在本机安装 `chromdata`、`uchrom-browser` 和 `uchrom-agent`，并显式配置 Claude Code/Codex 的 stdio MCP；后续复用已安装配置。
3. 用户运行本机启动命令，看到本地 WebUI 后把 MCP prompt 粘贴到 Claude Code/Codex。
4. agent 调用 `uchrom_setup_status`、`uchrom_workspace_snapshot` 和 `uchrom_get_selection`；没有本地 MCP 配置或页面连接时停止并给出下一步。
5. agent 将 hosted 摘要/快照视为迁移建议，与本地 canonical state 比较，不直接声称已导入；需要时提出 selection/locus/view 计划。
6. 页面 canonicalization 处理 unknown IDs、越界 locus 和 Stats scope；用户在本地 AgentPanel 点击 Apply。
7. agent 回读 snapshot 和 capture，向用户报告分析使用范围与页面最终实际状态。

默认 MCP prompt 固定按以下顺序执行：先 `uchrom_setup_status`，再读取 `uchrom_workspace_snapshot` 与 `uchrom_get_selection`，然后分析问题，调用 `uchrom_propose_ui_changes` 创建待确认计划，最后等待用户在本地 WebUI 点击 Apply。`uchrom_attach_handoff` 不在这条默认链路中。

MCP client 配置不能由网页或运行中的普通对话静默添加；首次配置和客户端重启是一次性前置步骤。handoff 中的 dataset reference、selection、locus、Stats scope 和问题会交给用户选择的 Claude/Codex 服务处理，生成面板必须明确提示。不得将本地文件路径、凭据或原始矩阵写入 handoff。

### 6.2 日常分析闭环

    用户提问
      ↓
    Claude/Codex 读取 workspace + 当前 page state
      ↓
    选择分析路径（Python/U-Chrom/只读页面 action）
      ↓
    运行分析并保存 provenance
      ↓
    生成 UI change plan
      ↓
    用户确认
      ↓
    调用 apply actions
      ↓
    每个 action 返回 canonical result
      ↓
    agent 回读 snapshot + capture
      ↓
    用户查看更新后的 WebUI 与结果文件

示例：用户说“看看 chr15 上 A/B 两组的 Rg 差异，并把最有代表性的范围展示出来”。

1. agent 调 describe_workspace 和 get_selection，得到真实 dataset、selection、当前 locus 和 view。
2. 页面 selection 是浏览状态，不自动等同于分析输入；agent 在对话中明确询问用户是否以当前 selection 作为分析输入。
3. Python 读取同一 ChromData，对确认的两组运行 Rg 分析，并在本地 run manifest 记录 dataset ID/version、实际 cell IDs 或解析后的 group、参数和软件版本。
4. agent 选择候选 locus，生成计划：设置 locus、打开 Stats、设置 chromScope=locus、打开 Genome view。
5. 用户确认后执行 action。
6. 页面返回实际的 canonical locus、Stats scope 和 pane id；如果页面裁剪了范围，agent 必须继续使用返回值。
7. agent 调 describe_workspace、get_selection、capture_view，向用户报告“分析使用范围”和“页面最终范围”。

### 6.3 结束与复现

用户可以从 Agent 面板导出轻量 result bundle：

- dataset URL/version/hash；
- canonical selection；
- actual locus；
- Stats scope；
- view configuration；
- analysis code/parameters/result references；
- action log（语义 action，不是 DOM 点击轨迹）；
- captures 和生成文件路径。

重新打开时，agent 通过 apply_snapshot 直接设置页面状态，不重放旧点击。分析输入范围保存在每次分析的 run manifest 中，不作为持久全局页面状态。

## 7. 本地架构

### 7.1 组件

    Claude Code / Codex
            │ stdio MCP
            ▼
    uchrom-agent companion
      ├─ handoff verifier
      ├─ local WebUI lifecycle
      ├─ page attach/pin
      ├─ pending plan + user approval
      └─ action history + state revision
            │ localhost HTTP
            ▼
    uchrom-browser FastAPI
      ├─ /api/control/*：现有 SSE action broker
      └─ /api/agent/*：受保护的 page pin、pending plan、approval、history
            │ SSE control channel
            ▼
    React WebUI actions.ts / Zustand store
            ▲
            └─ Agent section reads pending plans and posts Apply/Reject

### 7.2 companion 生命周期

- 默认监听 127.0.0.1，随机端口或可用端口；不监听 0.0.0.0。
- 启动后写入带随机 token 的本地状态文件，供 connect 和 MCP bridge 使用。
- 通过 python -m uchrom_browser <path-or-url> 启动已有 browser server，或调用内部 API 启动子进程。
- 等待 /api/health、页面 hello 和 dataset open 三个条件全部成立后才返回 attached。
- companion 通过本地 FastAPI 的 /api/agent/* 创建 session；页面与 session 显式绑定 page ID，不默认使用“最近 active page”作为 agent 目标。
- 本地 API 为 MCP 请求和页面 Apply/Reject 提供不同的 session 权限；只接受 loopback 来源、校验 Origin 和短时 session token。用户运行的本地 WebUI 生命周期由用户终端管理；companion 自己启动的子进程按 companion 生命周期策略关闭，不删除用户数据。
- 本地 FastAPI 持有 canonical page revision、pending plan、approval 和 UI action history；MCP stdio 进程只做 handoff、session 和 MCP 协议适配，不复制页面状态。

### 7.3 可选 hosted handoff relay

Worker relay 仅在显式部署和配置时启用；默认本地命令流程不调用它：

- POST /api/agent/handoffs：Atlas 或 hosted WebUI 提交 dataset ID、问题和可选 page snapshot；Worker 校验 dataset 位于发布 catalog。
- POST /api/agent/handoffs/redeem：本地 companion 在 JSON body 中提交 one-time token；响应只返回创建时保存的 payload。token 不放在 URL 路径、query、浏览器 history 或 Referer 中。
- token 是至少 256-bit 随机 bearer secret，有效期 10 分钟、成功领取一次后立即失效；clipboard 放置的是短指令和 token，而非可导航 URL。
- Worker 把 payload 放在专用 Durable Object 的短时存储中，兑换采用原子 consume；不依赖 hosted browser container 内存，也不记录 token 或 snapshot 到日志。
- Atlas origin 只可创建 dataset-only handoff；hosted WebUI origin 可创建带当前页面 snapshot 的 handoff。Atlas 仅允许精确配置的静态站点 origin；创建 API 校验 Origin、速率限制请求并验证 dataset ID 属于公开 catalog。
- 页面语义 snapshot 复制到本地 prompt 时最多 1 MiB UTF-8。超过上限时提示用户缩小 selection 后重试；不截断、不静默丢弃 ID。可选 Worker relay 使用同一限制。

兑换后的 payload 示例：

    {
      "version": 1,
      "issued_at": "2026-10-22T10:30:00Z",
      "expires_at": "2026-10-22T10:40:00Z",
      "dataset": {
        "id": "stevens_sim_cell1",
        "url": "https://.../sim_cell1.chromdata.zarr",
        "version": "catalog-version-or-etag"
      },
      "page_state": {
        "selection": {"cells": ["cell_1", "cell_2"], "source": "lasso"},
        "locus": {"chrom": "chr15", "start": 28400000, "end": 31200000},
        "views": [{"type": "stats", "stats_kind": "rg", "chrom_scope": "locus"}],
        "layout": "grid"
      },
      "question": "比较当前选择的两组细胞"
    }

page_state 是用户确认的迁移建议，不是本地事实；本地页面导入后必须返回 applied_state、dropped_cells、clamped_locus 和 warnings。Selection 使用 canonical cell IDs；用户的 analysis scope 不写入全局 snapshot，而是在每次分析的本地 run manifest 中单独固定并记录。

## 8. MCP 工具协议

MVP 提供页面控制、local continuation 状态和可选 relay 导入工具。分析继续使用用户自己的 Python/Skills；companion 不提供任意代码执行工具。

### 只读和会话工具

- `uchrom_setup_status()`：返回 companion 版本、MCP 状态和本地服务状态。
- `uchrom_attach_handoff(handoff_token_or_file)`：**可选能力**。兑换显式启用的 Worker token，或读取用户本机 handoff JSON 文件；它不是默认 local-first 流程。默认流程由用户运行启动命令后直接读取 canonical state。
- `uchrom_workspace_snapshot()`：返回页面 canonical state、dataset metadata、agent session 和 warnings。
- `uchrom_get_selection()`：返回 canonical cell IDs、source、group、数量；大 selection 默认返回摘要。
- `uchrom_export_selection()`：按用户请求把 canonical cell IDs 写入 companion 临时目录，返回文件句柄、数量和 digest，供本地 Python 直接读取，避免把大量 ID 放入模型上下文。
- `uchrom_list_groups()`：返回自动组和保存组。
- `uchrom_capture_view(pane, format)`：返回 capture 文件路径和实际 pane 信息。
- `uchrom_plan_status(plan_id)`：返回 pending / approved / rejected / stale / applied 状态和 canonical result。
- `uchrom_export_snapshot()`：导出页面状态；分析 provenance 由 run manifest 单独保存。

### 分析工具

MVP 不新增分析 MCP tools。Claude/Codex 使用本地终端、Python 和现有 U-Chrom analysis Skills 完成分析，并在本地保存 run manifest，至少记录 dataset/version、用户确认的 resolved cell IDs 或 group、参数、代码入口和软件版本。

### 页面变更工具

- `uchrom_propose_ui_changes(changes)`：校验 action、计算影响范围，创建绑定 page ID 和 state revision 的 pending plan。

底层 action 继续复用现有 `ui_tools.json`，包括 describe_workspace、get_selection、select_cells、set_locus、open_view、show_view、close_view、arrange、color_by、capture_view。用户在本地 WebUI 点击 Apply 后，本地 API 通过现有 broker 逐项执行 actions.ts action 并记录 canonical results；Undo 按钮恢复最近一次已批准计划执行前的页面 snapshot，不撤销分析计算或文件写入。MCP 工具只负责提出计划和读取状态，不提供绕过 WebUI 用户确认的 apply tool。

## 9. 状态一致性契约

### 9.1 单一事实来源

- 页面当前显示的 selection/locus/view/Stats 是页面 store 的 canonical state。
- action 输入只代表请求；action 返回值代表页面实际接受的状态。
- agent 不得用 handoff 原始值、旧的本地缓存或截图替代回读。
- selection 以服务端注册后的已知 cell IDs 为准；未知 ID 必须在结果中报告并从页面状态中剔除。
- locus 以页面实际裁剪后的范围为准；Stats 的 chromScope 必须显式返回 all 或 locus。
- analysis scope 与临时视觉 selection 分开记录。

### 9.2 变更响应格式

    {
      "ok": true,
      "requested": {"chrom": "chr15", "start": 0, "end": 999999999},
      "applied": {"chrom": "chr15", "start": 3000000, "end": 195000000},
      "warnings": ["range clamped to chromosome bounds"],
      "state_revision": "r_42"
    }

### 9.3 并发与冲突

- 用户手动操作后 state_revision 变化；agent 的旧计划提交时必须被拒绝或要求重新生成。
- 每个 mutation 携带 expected_revision，防止覆盖用户刚刚做的选择。
- 多标签页必须显式 page_id；没有 page pin 时只允许读取，不允许 mutation。
- agent 断线后，页面保持最后状态，不自动继续执行排队动作。

## 10. 安全、隐私和授权

- 默认本地 prompt 不经过 U-Chrom Worker；只包含公开 dataset URL、用户问题和用户确认的摘要/最小语义 snapshot。可选 Worker relay 才创建高熵一次性 token，并由 Durable Object 原子兑换。
- 默认不把完整 canonical cell ID 列表放进 prompt；用户勾选后页面必须显示“这些 ID 会进入所选模型服务上下文”的提示。大 selection 使用 `uchrom_export_selection` 写入本机临时文件，再由本地 Python 读取。
- 私有数据不通过公网 prompt 或 Worker relay 传输；用户在本地 WebUI/agent 中自行打开本地文件。
- 本地 companion 只接受 127.0.0.1 请求，校验 Origin、CSRF token 和 session bearer token。
- MCP tool 不执行任意 shell 或 Python。attach 只可启动 companion 自己管理的固定 U-Chrom browser 命令，并需遵从用户本地 agent 客户端的授权机制；安装依赖、下载数据或写入分析文件时，agent 必须说明本地命令和目标文件。
- 不默认上传 prompt、cell IDs、分析结果或 capture 到 U-Chrom telemetry。用户明确复制到 Claude/Codex 的本地 prompt 会进入其模型服务上下文，页面必须在复制前提示。
- `uchrom_propose_ui_changes` 创建绑定 `page_id` 和 `expected_revision` 的 pending plan；只有用户在该本地 WebUI 的 Agent section 点击 Apply 后，本地 FastAPI 才批准并执行计划。agent 通过 `uchrom_plan_status` 读取结果；不提供可绕过 WebUI 确认的 apply tool。
- 不把现有 hosted /api/control/* 公开到互联网。

## 11. 失败状态与用户反馈

| 状态 | 用户看到的反馈 | agent 行为 |
| --- | --- | --- |
| companion 未安装 | 显示一行安装命令和当前平台 | 停止，不假设安装成功 |
| MCP 未配置 | 显示 Claude Code/Codex 配置入口和重启提示 | 停止，不尝试静默写配置 |
| 本地服务启动失败 | 显示端口、依赖和日志入口 | 返回可诊断错误 |
| 本地启动命令失败 | 显示安装前置条件和 URL/依赖错误 | 不假设 WebUI 已启动 |
| 本地服务已启动但页面未连接 | 显示“打开本地 WebUI 后再继续” | 只读，不执行 mutation |
| MCP 已连接但页面未 pin | 显示 page 列表和 Pin 操作 | 只读，不执行 mutation |
| 页面已连接 | 显示 canonical state 和当前 revision | 可读取、分析和提出计划 |
| 计划待确认/已应用 | 显示 Apply/Reject、结果和 readback | 不绕过用户确认 |
| 可选 Worker handoff 过期/兑换失败 | 要求回 Atlas 重新生成 | 不加载任何数据 |
| dataset 不可访问 | 显示 URL/权限/网络问题 | 可询问用户改为下载 .cdz |
| 页面未 attach | 显示打开本地页面的提示 | mutation 不执行 |
| 状态导入有差异 | 展示 unknown cells、clamped locus 等 | 以 applied state 继续，要求确认 |
| 用户状态发生变化 | 显示“页面已被手动修改” | 重新 snapshot，废弃旧计划 |
| action 超时 | 显示具体 action 和 page ID | 不自动重试 mutation，允许用户重试 |

## 12. 分阶段交付

### Phase 0：本地闭环 spike

- 复用现有 `show-in-browser` Skill、Python client 和 control/SSE 链路，验证 Claude Code/Codex 本地分析后更新 WebUI 的可行性。
- 用真实 .cdz 数据跑通 page attach、canonical snapshot、locus/Stats/view mutation 和回读。
- 输出最小协议差距；此阶段不增加托管 handoff 或 production UI。

### Phase 1：完整本地 continuation MVP

- 新增 companion、stdio MCP、经用户确认的安装和 client 配置流程，并返回稳定的 setup/connection stage。
- Atlas 增加 Continue locally 入口，直接从 catalog 生成本机启动命令和 MCP 指令；不依赖 Worker API。
- Hosted WebUI 增加本机安装/启动命令、问题和摘要优先的 prompt；Worker token relay 作为可选增强。
- 本地 WebUI 增加 Agent section、page pin、pending plan 的 Apply/Reject、action history、undo。
- 支持 setup_status、workspace_snapshot、get_selection、export_selection、list_groups、capture_view、propose_ui_changes、plan_status、export_snapshot；`attach_handoff` 仅作为可选 relay/本地 JSON 导入；分析继续通过用户的本地 Python 与 Skills。

### Phase 2：结果 bundle 和分析 provenance

- 导出 result bundle、分析 run manifest 和结构化 provenance。
- 默认摘要和按需 selection 文件导出已经是 MVP 行为；后续再评估更大数据集的流式导出。

### Phase 3：可选浏览器直控

- 在支持 WebMCP 的环境中，允许 Chrome DevTools MCP 直接执行 uchrom_* 页面工具。
- 只提供明确的“直接控制当前标签页”入口，不把它和本地 continuation 混为一条链路。
- 做 profile 权限提示、页面绑定和实验功能检测。

## 13. 验收标准

### 用户体验

- 用户从 Atlas 点击 Continue locally 后能复制本机命令，运行后打开选定 dataset 的本地 WebUI；再把 MCP 指令粘贴到已配置的 Claude/Codex。
- 首次用户能看到安装、启动、连接、pin、Apply 的阶段状态；失败时知道下一步动作。
- Hosted WebUI 能在浏览器本地生成语义 snapshot prompt；用户明确复制给自己的模型服务。
- 默认 prompt 不包含完整 cell ID 列表；用户明确选择后才包含，且 UI 显示隐私提示。
- 用户能清楚区分“分析使用的 scope”和“页面临时高亮”。
- agent 的每次页面变更都有计划、确认、结果和实际状态回读。

### 技术行为

- 本地 WebUI 能从 Atlas dataset URL 或本地 .cdz 打开同一数据。
- unknown cell IDs、越界 locus 和无效 Stats scope 不会出现在最终页面状态中。
- 多标签页下 mutation 不会发到未绑定页面。
- 页面手动修改后，旧 agent 计划不能覆盖新状态。
- companion 退出后本地控制端口不可继续访问。

### 真实验证

- 使用 Stevens sim_cell1.cdz 和至少一个 Atlas 远程 store。
- 验证 selection、locus、Stats scope、view layout、capture 与页面 DOM/截图一致。
- 分别用 Claude Code、Codex 运行本地 prompt 流程，并保存命令、日志、结果 bundle 和截图；如果客户端未配置，验证 setup 指引而不是宣称连接成功。
- 记录未验证项：正式 PyPI/桌面安装器、不同操作系统、私有数据权限、远程网络中断、Worker relay 运行时 E2E。

## 14. 设计决策记录

- 选择本地 WebUI 而不是 Chrome DevTools MCP 作为主路线：本地链路权限窄、能运行 Python 分析、能复用现有 action/SSE、可以明确回读 canonical state。
- handoff 采用语义快照而不是操作 replay：跨页面迁移只需要数据和状态，不需要复现具体点击顺序。
- 模型由用户托管：U-Chrom 提供工具、数据和页面，不托管 Claude/Codex，也不保存用户对话。
- WebMCP 保留为增强入口：它适合浏览器内 agent 的 live page tool discovery，但不替代本地 companion。
- 先本地、后 hosted relay：只有在真实使用数据表明用户强烈需要远程页面直控时，才增加公网 relay、租户隔离和审计系统。

## 15. 2026-10-24 验证边界

已用真实 `packages/uchrom-browser/tests/fixtures/sim_cell1/sim_cell1.cdz` 独立跑通本地 agent loop：SSE page attach、canonical selection readback、locus canonicalization、Stats/Genome 计划审批与应用、revision readback 和 capture。浏览器 agent API、control/SSE、companion、frontend Vitest/build、Atlas local continuation/build，以及 Worker tests/typecheck 的实际命令和结果记录在 `.superpowers/sdd/2026-10-22-local-agent-webui-mvp-plan/task-4-report.md`。

这组证据不等于完整浏览器产品 E2E：真实测试通过 HTTP 审批调用模拟 AgentPanel 操作，未验证渲染 DOM 中点击 AgentPanel Apply；Worker 只做回归测试，未验证完整 create→redeem→attach runtime 链路。PyPI、桌面安装器、Claude/Codex 自动配置、私有数据权限、网络中断和跨平台安装也保持未验证。
