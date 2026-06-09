# U-Chrom WebApp

染色质 3D 结构交互式分析工具 — 为单细胞 Hi-C / DNA FISH / seqFISH+ 等多模态数据提供统一的可视化和分析平台。

## 项目简介

U-Chrom WebApp 是一个 Web 端交互式分析工具，旨在解决染色质 3D 结构数据分析中的核心痛点：

- **多视图联动**：3D 结构、接触矩阵、基因组轨道、细胞嵌入在同一界面中实时同步
- **单细胞群体分析**：点击 UMAP cluster 即可查看该群体的代表性结构
- **多模态整合**：统一处理测序数据（Hi-C、Dip-C）和成像数据（DNA FISH、chromatin tracing）
- **发表级出图**：所见即所得的 Figure Composer，导出符合 Nature/Science 规范的 SVG
- **AI Agent 辅助**：自然语言驱动的探索性分析，自动生成 figure legends

### 核心功能

1. **3D 结构可视化** — 基于 Three.js 的 WebGL 渲染器，支持多细胞叠加、染色体选择、bin 高亮
2. **Contact Map** — 集成 HiGlass，提供多分辨率平滑缩放的接触矩阵热图
3. **基因组浏览器** — 集成 IGV.js，支持加载 bigWig/WIG 轨道、注释层
4. **细胞嵌入** — UMAP/t-SNE 投影，按细胞类型/染色体着色，支持框选与 3D 结构联动
5. **Figure Composer** — 拖拽式布局编辑器，预设 Nature/Science 尺寸模板，导出 SVG/PDF
6. **AI Agent** — 基于 AG-UI 协议的自然语言接口，支持工具调用与声明式 panel 生成

## 技术栈

### 后端
- **FastAPI** — 异步 Web 框架，WebSocket 实时通信
- **Uvicorn** — ASGI 服务器
- **HiGlass tileset API** — 动态生成多分辨率接触矩阵 tiles
- **ProcessPoolExecutor** — 后台异步计算（距离矩阵、embedding）
- **uchrom** — 核心数据结构（`ChromData`）与分析算法

### 前端
- **React 18** + **TypeScript** — UI 框架
- **Vite** — 构建工具，HMR 开发体验
- **Zustand** — 轻量级状态管理（全局 viewport、cell selection）
- **Three.js** — 3D 结构 WebGL 渲染
- **HiGlass** — 接触矩阵多分辨率浏览
- **IGV.js** — 基因组轨道浏览器
- **deck.gl** — 可选的 GPU 加速可视化层
- **Vega-Lite** — 统计图表声明式渲染
- **react-resizable-panels** — 面板拖拽调整

## 快速开始

### 环境要求
- Python ≥ 3.9
- Node.js ≥ 18
- 已安装 `uchrom` 包（`pip install -e .` 从项目根目录）

### 后端启动

```bash
# 从项目根目录执行
cd webapp/backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

后端服务将在 `http://localhost:8000` 启动，提供以下端点：
- `/ws/main` — WebSocket 连接（会话管理、Agent 消息）
- `/api/data/*` — 数据查询接口（细胞、bins、计算接口）
- `/api/tileset_info` + `/api/tiles` — HiGlass 兼容的 tileset 端点
- `/api/track_wig/{name}` — IGV.js WIG 格式轨道
- `/api/export` — 图表导出（SVG/PDF）

### 前端启动

```bash
cd webapp/frontend
npm install    # 首次运行需安装依赖
npm run dev    # 启动开发服务器
```

前端将在 `http://localhost:5173` 启动（Vite 默认端口），自动连接到 `ws://localhost:8000/ws/main`。

### 生产构建

```bash
cd webapp/frontend
npm run build  # 构建产物输出到 dist/
```

可使用 FastAPI 静态文件服务或 nginx 提供构建后的前端文件。

## 示例数据

### 加载 H1Esc-HFF 示例数据

项目根目录下的 `example-data/H1Esc-HFF.R1.tar.gz` 包含单细胞 DNA FISH 数据（来自 Tan et al. Science 2018）：

```bash
# 解压数据
cd example-data
tar -xzf H1Esc-HFF.R1.tar.gz

# 在 Python 中加载
from uchrom.core.cdata import ChromData
cd = ChromData.read('example-data/H1Esc-HFF.R1/cell_001.h5cd')
```

#### 通过 WebApp 加载

1. 启动后端和前端
2. 点击左上角 **File → Upload Data**
3. 选择 `.h5cd` 文件或拖拽到上传区域
4. 数据解析完成后，左侧数据树将显示细胞、染色体、轨道信息
5. 点击主画布 **Add Panel** 添加可视化面板

### 数据格式

WebApp 支持以下数据格式：
- **`.h5cd`** — U-Chrom 原生 HDF5 格式（推荐，支持完整元数据）
- **`.csv`** — 平面结构表（需包含 `chrom, start, end, x, y, z` 列）
- **FOF-CT core table** — 4DN FISH Omics Format（`.csv` 文件，带 `##` 开头的元数据行）

## 主要功能

### 3D 结构可视化

- **染色体选择**：底部导航栏切换 chr1-chrX
- **多细胞叠加**：在 UMAP 面板框选多个细胞 → 3D 面板自动叠加显示（半透明）
- **Bin 高亮**：在 Contact Map / IGV 面板拖选基因组区间 → 3D 结构高亮对应 bins
- **视图控制**：鼠标拖拽旋转，滚轮缩放，右键平移

### Contact Map（HiGlass 集成）

- **多分辨率缩放**：滚轮平滑缩放，自动加载不同分辨率的 tiles
- **双向联动**：拖拽改变视图 → 更新全局 `GenomicViewport` → 其他面板同步
- **细胞群体平均**：选择细胞子集 → 重算该群体的平均距离矩阵
- **Colormap 配置**：右侧样式面板调整色阶（RdBu / YlOrRd / Viridis）

### 基因组浏览器（IGV.js 集成）

- **轨道加载**：
  - 内置轨道：`cd.tracks` 中的 epigenomic signals（ATAC-seq、ChIP-seq 等）
  - 外部轨道：上传 bigWig / WIG / BED 文件
- **区间选择**：拖选区间 → 更新全局 viewport → Contact Map 和 3D 结构同步跳转
- **多轨道叠加**：H3K27me3、H3K4me3、nuclear speckle 等信号并排显示

### AI Agent

Agent 面板位于右侧，支持自然语言驱动的分析流程：

**示例对话：**

```
User: 显示 Purkinje 细胞的 chr15 结构
Agent: 已筛选 312 个 Purkinje 细胞，正在渲染 chr15...
      [主画布自动创建 3D Structure Viewer panel，加载对应细胞]
```

```
User: 比较 Purkinje 和 MLI1 在 chr15:40-60Mb 的接触矩阵
Agent: 工具调用：
       - query_chromdata(cell_type="Purkinje") → 312 cells
       - query_chromdata(cell_type="MLI1") → 198 cells
       - set_viewport(chrom="chr15", start=40000000, end=60000000)
      [主画布自动创建两个 HiGlass panel，左右并排]
```

**Agent 功能：**
- 数据查询（按细胞类型、染色体、基因组区间筛选）
- 分析调用（TAD detection、compartment calling、loop identification）
- 面板生成（声明式输出 panel spec，前端渲染）
- Figure legend 生成（基于当前面板状态输出可投稿的图注文字）

### Figure Composer

点击工具栏 **Figure** 按钮进入出图模式：

1. **布局编辑**：
   - 从主画布拖入已有面板，或新建面板
   - 拖拽调整位置与大小
   - 添加 label（A/B/C...），设置字体大小
2. **尺寸预设**：
   - Nature single column (89mm)
   - Nature double column (183mm)
   - Science double column (120mm)
3. **样式统一**：
   - 全局字体大小（7pt / 8pt / 9pt）
   - Colormap 方案
   - Colorbar 位置与范围
4. **导出**：
   - SVG（矢量，可在 Illustrator 继续编辑）
   - PDF（用于投稿）
   - PNG（用于预览）
   - Figure State JSON（可复现的配置文件）

## 架构说明

### 1D-3D Event Bus

前端通过 Zustand 维护两个全局状态，实现多面板联动：

```typescript
// store.ts
interface AppState {
  viewport: { chrom: string; start: number; end: number };
  cellSelection: { ids: string[]; label: string };
  setViewport: (v: Viewport) => void;
  setCellSelection: (s: CellSelection) => void;
}
```

**各面板响应行为：**

| 面板类型 | viewport 变化 | cellSelection 变化 |
|---------|-------------|-------------------|
| HiGlass Contact Map | 缩放到对应区间 | 重算选中细胞群平均矩阵 |
| IGV Browser | 跳转到对应区间 | — |
| 3D Structure Viewer | 高亮对应 bins | 切换显示细胞 |
| Cell Embedding | — | 高亮选中点 |

### AG-UI 协议

Agent 与 UI 通过 WebSocket 传递 JSON 消息，遵循 AG-UI（Agent-UI Interface）协议：

**Agent → UI（声明式 spec）：**
```json
{
  "type": "create_panel",
  "panel_type": "higlass_contact",
  "config": {
    "cell_ids": ["c1", "c2", "c3"],
    "viewport": {"chrom": "chr15", "start": 0, "end": 100000000},
    "colormap": "RdBu"
  }
}
```

**UI → Agent（用户操作反馈）：**
```json
{
  "type": "viewport_changed",
  "viewport": {"chrom": "chr15", "start": 20000000, "end": 45000000}
}
```

前端负责渲染，Agent 负责决策。这种分离使得：
- Agent 可在不重新计算的情况下输出多种可视化方案
- 用户可在前端调整样式（colormap、字体）无需调用 Agent
- Figure State 本身即 Agent 输出的 spec，可保存、分享、版本化

### Phase 0-4 改造成果

**Phase 0（已完成）**：Viewer 集成
- 将自研的 Contact Map / Track Plot 替换为 HiGlass / IGV.js
- 实现 1D-3D event bus，建立基因组坐标联动机制
- 后端新增 `/api/tileset_info`、`/api/tiles`、`/api/track_wig` 端点

**Phase 1（规划中）**：AG-UI 协议完整实现
- Agent 输出声明式 panel spec（JSON）
- 前端解析 spec 渲染面板（HiGlass / IGV / Vega-Lite）
- 支持流式数据填充（骨架先行，数据异步加载）

**Phase 2（规划中）**：Figure Composer 深度整合
- Figure State JSON 与 panel spec 统一
- 导出时包含数据引用（tileset URL、track 文件路径）
- 支持离线渲染（后端 headless Chromium）

**Phase 3（规划中）**：插件系统
- 用户自定义分析模块（Python + WebAssembly）
- 插件输出标准 panel spec，自动注册到 UI

**Phase 4（规划中）**：多用户协作
- 实时同步编辑（类似 Google Docs）
- 会话分享链接（只读 / 可编辑权限）
- 注释与讨论线程

### 会话状态编码与分享

Phase 0 实现了 **viewer state 编码到 URL hash** 的机制，用户可通过复制 URL 分享当前视图状态：

**分享方式：**
1. 点击顶栏 "Share" 按钮，链接自动复制到剪贴板（按钮显示 "Copied!" 2 秒）
2. 将链接发送给协作者，他们打开后会看到相同的视图状态

**编码内容：**
- `viewport`: 基因组区间（chrom, start, end）
- `cellSelection`: 选中的细胞列表和筛选模式
- `panels`: 面板布局（类型、ID、标签）

**示例 URL：**
```
https://localhost:5173/#%7B%22viewport%22%3A%7B%22chrom%22%3A%22chr21%22%2C%22start%22%3A18000000%2C%22end%22%3A20000000%7D%2C%22cellSelection%22%3A%7B%22mode%22%3A%22cell_type%22%2C%22ids%22%3A%5B%22c1%22%2C%22c2%22%5D%2C%22label%22%3A%22Purkinje%22%7D%2C%22panels%22%3A%5B%7B%22id%22%3A%22p1%22%2C%22type%22%3A%22umap%22%2C%22label%22%3A%22Cell%20Embedding%22%7D%5D%7D
```

URL hash 在页面加载时自动解析，恢复 viewport、cell selection 和 panels 状态。无效的 hash 会触发 console warning 并使用默认状态。

## 开发指南

### 项目结构

```
webapp/
├── backend/
│   ├── main.py              # FastAPI 应用入口，路由注册
│   ├── session.py           # Session 类（管理 ChromData、分析结果）
│   ├── ws_handler.py        # WebSocket 消息处理（Agent 协议）
│   ├── data_api.py          # 数据查询 REST API
│   ├── tileset_api.py       # HiGlass tileset 端点
│   ├── track_wig.py         # IGV.js WIG 格式轨道
│   ├── agui_events.py       # AG-UI 事件定义
│   └── templates/           # HTML 模板（standalone export）
├── frontend/
│   ├── src/
│   │   ├── App.tsx          # 根组件
│   │   ├── store.ts         # Zustand 状态管理
│   │   ├── components/
│   │   │   ├── MainCanvas.tsx       # 主画布容器
│   │   │   ├── HiGlassPanel.tsx     # HiGlass 面板
│   │   │   ├── IGVPanel.tsx         # IGV.js 面板
│   │   │   ├── StructureViewer.tsx  # 3D 结构 Three.js 渲染
│   │   │   ├── CellEmbedding.tsx    # UMAP/t-SNE 投影
│   │   │   └── AgentPanel.tsx       # Agent 对话界面
│   │   └── utils/
│   │       └── ws.ts        # WebSocket 客户端
│   ├── package.json
│   └── vite.config.ts
└── README.md               # 本文件
```

### 添加新面板类型

1. **定义面板类型**（`frontend/src/store.ts`）：
   ```typescript
   type PanelType = 'higlass_contact' | 'igv_browser' | 'structure_3d' | 'your_new_panel';
   ```

2. **创建 React 组件**（`frontend/src/components/YourNewPanel.tsx`）：
   ```typescript
   export function YourNewPanel({ config }: { config: YourPanelConfig }) {
     const { viewport, setViewport } = useStore();
     // 订阅 viewport，渲染逻辑...
   }
   ```

3. **注册到 MainCanvas**（`frontend/src/components/MainCanvas.tsx`）：
   ```typescript
   case 'your_new_panel':
     return <YourNewPanel config={panel.config} />;
   ```

4. **（可选）添加后端 API**：如需后端计算，在 `backend/data_api.py` 添加端点。

### 测试

后端测试使用 `pytest`：
```bash
pytest tests/test_tileset_api.py -v    # HiGlass tileset 端点
pytest tests/test_track_wig.py -v      # IGV.js WIG 端点
pytest tests/test_bins_api.py -v       # bins 元数据端点
```

前端测试（规划中）：
```bash
cd webapp/frontend
npm run test  # Vitest + React Testing Library
```

## 常见问题

**Q: 前端连接 WebSocket 失败？**  
A: 检查后端是否启动，确认端口为 8000。浏览器控制台应显示 `WebSocket connection to 'ws://localhost:8000/ws/main' failed`，若看到此消息说明前端配置正确但后端未响应。

**Q: HiGlass 面板显示空白？**  
A: 检查后端 `/api/tileset_info?d=contact-chr1` 是否返回正确的 JSON。HiGlass 要求 `datatype: "matrix"`，`bins_per_dimension: 256`，缺少字段会导致渲染失败。

**Q: 如何加载自己的数据？**  
A: 将数据转换为 `.h5cd` 格式：
```python
from uchrom.core.cdata import ChromData
cd = ChromData.from_dataframe(your_df)  # df 需包含 chrom, start, end, x, y, z
cd.write('your_data.h5cd')
```
然后在 WebApp 中通过 File → Upload 上传。

**Q: 导出的 SVG 文件在 Illustrator 中打不开？**  
A: 检查 SVG 是否包含非 ASCII 字符（如中文 label）。当前导出器使用 UTF-8 编码，部分旧版 Illustrator 可能不兼容。建议升级到 Illustrator 2020 或更高版本。

**Q: 如何贡献代码？**  
A: 欢迎提交 Pull Request！请遵循以下流程：
1. Fork 本仓库
2. 创建 feature 分支（`git checkout -b feat/your-feature`）
3. 提交修改并编写测试
4. 推送到 GitHub 并创建 PR

## 路线图

- [x] Phase 0: HiGlass + IGV.js 集成，1D-3D 联动
- [ ] Phase 1: AG-UI 协议完整实现
- [ ] Phase 2: Figure Composer 深度整合
- [ ] Phase 3: 插件系统
- [ ] Phase 4: 多用户协作

## 许可证

本项目遵循与 U-Chrom 主仓库相同的许可证（待补充）。

## 致谢

- HiGlass 团队（Harvard Medical School）
- IGV.js 团队（Broad Institute）
- Three.js 社区
- Vite 和 React 生态
