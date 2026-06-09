# U-Chrom Web Portal v0 — 设计规格

> 状态：设计已确认，待实现
> 日期：2026-06-10
> 分支/worktree：`worktree-web-portal`

## 一、定位与目标

U-Chrom Web Portal 是一个**染色质 3D 结构"分析就绪"数据集门户**，分发统一的
ChromData (`.h5cd`) 格式数据集。

- **短期目标**：配合论文发表，提供一个能展示 Takei 2025 等数据集、可被
  reviewer 和读者在线访问的门户，增强公信力。
- **长期目标**：演进为染色质 3D 领域的数据仓库（社区生态），支持外部数据集
  提交、检索、用户系统。

v0 是"纵切片 + 可扩展地基"：先把单数据集端到端跑通（配合发表），架构上为生态
功能预留扩展位，不做成一次性死胡同。

## 二、与 webapp 的关系（平行双产品）

`webapp`（`feat/phase0-viewer-integration` / `feat/agent-integration` 分支）是
**交互式分析工具**（IGV/HiGlass 风格的 explorer）；本 portal 是**数据目录/仓库**
（4DN portal 风格的 catalog）。二者是平行的两类产品，**不合并代码**。

三条对接接缝：
1. **数据格式**：portal 分发 `.h5cd`，webapp 消费 `.h5cd`。`ChromData` +
   `load_dataset()` 是唯一硬契约。
2. **入口跳转**：portal 详情页的"在 Analyzer 中打开"按钮跳转到 webapp，把重型
   交互（3D、HiGlass、Figure Composer）转交给 webapp。
3. **共享底层**：二者都依赖 `uchrom` 包，但 portal 的预览图**独立生成**，不抽取
   webapp 的可视化代码。

portal **不重做** webapp 已有的能力（交互 3D、接触矩阵、Agent）。复杂交互一律
"跳转到 webapp"。

## 三、关键决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 核心目标 | 短期配合发表 + 长期生态（同一条路两段） | v0 做纵切片，地基按生态打 |
| 数据托管 | 外部托管（Zenodo 等），portal 只存元数据 + 预览 | 后端最轻、零流量成本 |
| 技术形态 | 动态后端从头上：FastAPI + SQLite + Next.js SSR | 为提交/搜索/用户预留 |
| 预览图生成 | 独立基于 uchrom 离线生成，与 webapp 解耦 | 路径清晰、依赖少 |
| v0 可视化 | 仅 notebook HTML 嵌入（最小 v0），交互图留 v1 | 最快跑通 |
| 代码组织 | 方案 A：Monorepo 三件套（backend/pipeline/frontend） | 离线重计算与在线服务分离 |

## 四、代码组织（方案 A：Monorepo 三件套）

```
data-portal/
├── backend/          FastAPI + SQLite，只读 REST API（无状态、轻量）
│   ├── models.py     SQLAlchemy: Dataset 表
│   ├── schemas.py    Pydantic: DatasetSummary / DatasetDetail
│   ├── api/          /api/datasets, /api/facets, /api/health
│   ├── db.py         SQLite 连接
│   └── main.py       FastAPI app + CORS + StaticFiles
├── pipeline/         离线预生成 CLI（不在请求路径上）
│   ├── catalog/      *.yaml 数据集声明文件（进 git）
│   ├── ingest.py     .h5cd → 提取统计 → 写 SQLite + 静态产物
│   └── render_nb.py  nbconvert notebook → HTML + 缩略图
├── frontend/         Next.js SSR：列表页 + 详情页
│   └── src/app/
└── data/             生成物（gitignore）
    ├── portal.db
    ├── notebooks/{id}.html
    └── thumbnails/{id}.png
```

职责单一：pipeline（重、慢、离线）和 API（轻、快、在线）彻底分开。
后端运行时**完全不碰 .h5cd 大文件**（它们在 Zenodo），这是后端能极轻的根本原因。

## 五、数据模型（SQLite + SQLAlchemy）

v0 仅一张 `datasets` 表，字段分三类：

```python
class Dataset:
    # ── 身份与检索 ──
    id: str              # slug, 主键, 如 "takei2025_cerebellum"
    title: str
    description: str
    organism: str        # "Mus musculus"
    assembly: str        # "mm10"
    technology: str      # "DNA seqFISH+"
    doi: str
    citation: str
    created_at, updated_at: datetime

    # ── 统计摘要（pipeline 从 .h5cd 提取）──
    n_cells: int
    n_traces: int
    n_spots: int
    n_markers: int
    cell_types: JSON     # {"Granule": 1109, "Bergmann": 192, ...}
    genome_coverage: str # "genome-wide" 或 "chr1-chrX"
    xyz_unit: str        # "μm"
    resolution: JSON     # {"voxel_xy_nm": 103, "voxel_z_nm": 250}

    # ── 外部托管 + 产物指针 ──
    files: JSON          # [{"label","url","size_mb","format"}, ...]
    notebook_html_path: str   # 可空（nbconvert 失败时）
    thumbnail_path: str
    analyzer_url: str         # 可空（webapp 未就绪时前端隐藏按钮）
    status: str               # "published" | "draft"（为审核流预留）
```

设计决策：
1. **JSON 列而非额外建表**：`cell_types`/`files`/`resolution` 是随数据集走的小
   结构，v0 不需 join，SQLite JSON 列足够。未来按 cell_type facet 检索再 normalize。
2. **`id` 用 slug 做主键**：URL 友好、与 example-data 命名一致、人类可读。
3. **`files` 是数组**：一个数据集常有多 repID / 多格式，各指向外部 URL。
4. **`status` 现在就加**：v0 全为 "published"，留列给未来审核队列，零迁移。
5. **`analyzer_url` 可空**：webapp 未部署时为空，前端不显示跳转按钮——平行解耦，
   portal 不被 webapp 进度阻塞。

**不做（YAGNI）**：用户表、提交记录表、tags 多对多、版本历史。

## 六、Pipeline 摄取流程（离线 CLI）

Pipeline 是独立 CLI，**不在请求路径上**，是 portal 内容的唯一来源。

### 输入：每个数据集一个 YAML 声明文件

```yaml
# pipeline/catalog/takei2025_cerebellum.yaml
id: takei2025_cerebellum
title: "Mouse Cerebellum DNA seqFISH+ (Takei 2025)"
description: "..."
organism: "Mus musculus"
assembly: "mm10"
technology: "DNA seqFISH+"
doi: "10.1038/s41586-025-08838-x"
citation: "Takei et al., Nature 2025"
source_h5cd: "~/data/takei2025/rep1.h5cd"   # 本地路径，供提取统计
notebook: "tutorials/takei2025_walkthrough.ipynb"
files:                                        # 人工填，指向 Zenodo
  - label: "Replicate 1 (.h5cd)"
    url: "https://zenodo.org/records/XXXXX/files/rep1.h5cd"
    size_mb: 312
    format: h5cd
analyzer_url: null
```

YAML 把"人写的元数据"和"机器提取的统计"分开：YAML 进 git 做审计（契合
example-data catalog 纪律），统计由机器算不会手抄错。未来提交流程中，此 YAML 即
上传表单的后端表示。

### 处理步骤（`pipeline/ingest.py <catalog.yaml>`）

```
1. 读 YAML → 人工元数据 + source_h5cd 路径
2. ChromData.read(source_h5cd) → 提取 n_cells/n_traces/n_spots/n_markers、
   cell_types（spots 按 cell_type 分组计数）、genome_coverage/xyz_unit/resolution
3. QC 校验（轻量）→ 不通过则中止，不写库
4. render_nb.py: nbconvert notebook → data/notebooks/{id}.html；
   截代表图 → data/thumbnails/{id}.png
5. UPSERT 一行进 SQLite（幂等，可重复跑）
6. 打印摘要
```

关键设计：
- **幂等 UPSERT**：改了 YAML 重跑即可，不产生重复行。
- **QC 复用 ChromData 校验**：`ChromData.read()` 构造时已做 coords/必需列/tracks
  校验；pipeline 加门户级检查（notebook 能否 nbconvert、URL 格式、统计非空）。
  不通过中止、不写库——保证库里全是好数据。
- **`source_h5cd` 只在 ingest 时读一次**，portal 运行时不碰 .h5cd。
- **nbconvert 失败兜底**：记 warning，`notebook_html_path` 留空，元数据/下载照常
  入库——单个产物失败不拖垮整条记录。

### 输出

`data/portal.db` + `data/notebooks/{id}.html` + `data/thumbnails/{id}.png` 均为
生成物（gitignore）；唯一进 git 的是 `pipeline/catalog/*.yaml`。

## 七、后端 REST API（FastAPI）

后端只读 `portal.db` 和静态产物，无状态、无重计算。

```
GET  /api/datasets?organism=&technology=&q=
     → 列表（轻字段：id/title/organism/technology/n_cells/n_markers/thumbnail_url）
GET  /api/datasets/{id}              → 完整元数据；404 若不存在
GET  /api/datasets/{id}/notebook     → FileResponse HTML；404/占位 若不可用
GET  /api/datasets/{id}/thumbnail    → PNG（或 StaticFiles mount）
GET  /api/facets                     → {organism:[...], technology:[...]}
GET  /api/health                     → {status, n_datasets}
```

设计决策：
1. **列表/详情字段分离**：列表只返回卡片轻字段，详情返回全量。减少传输、可缓存。
2. **下载不经后端**：`files` URL 是 Zenodo 外链，前端 `<a href>` 直连——后端不做
   下载代理，零流量成本。代价：无法统计下载量（未来要统计可加 redirect 端点）。
3. **notebook 用 `FileResponse` 直出**，前端 iframe 隔离其 CSS/JS。
4. **Pydantic 双层 schema**：`DatasetSummary`/`DatasetDetail` 既是文档也是契约，
   未来 Python SDK 直接照此反序列化。
5. **CORS**：允许前端 origin（开发期跨端口）。
6. **为生态预留但不实现**：POST 提交、全文搜索、认证——v0 不建路由，注释标注扩展点。

安全：
- v0 全部只读公开端点，无写操作、无用户数据，无认证是合理的。
- `{id}` 用 slug 白名单正则 `[a-z0-9_]` 校验，notebook 端点路径用 `pathlib` 解析后
  校验落在 `data/notebooks/` 内，防 `../` 路径穿越（唯一注入点）。

## 八、前端页面（Next.js SSR）

SSR 渲染（SEO 友好、分享链接有预览）。两页面 + 全局壳。

```
frontend/src/app/
├── layout.tsx              顶栏（logo + 导航）
├── page.tsx                列表页
└── datasets/[id]/page.tsx  详情页
```

### 列表页 `/`
- SSR fetch `/api/datasets` → 卡片网格（缩略图 + 标题 + organism/technology +
  n_cells/n_markers）
- 筛选下拉来自 `/api/facets`；搜索框走 `?q=` 简单 LIKE
- v0 可能只有 1 个数据集，列表页照做——加第二个零改动

### 详情页 `/datasets/[id]`
三 tab：
- **Overview**：统计卡片、描述、cell_types 分布、元数据表、`load_dataset()` 代码
  片段（带复制按钮，标注 "SDK coming soon"）
- **Notebook**：`<iframe>` 懒加载（切到该 tab 才加载），固定高度 + 内部滚动
- **Download**：遍历 `files` 渲染 Zenodo 外链按钮（标注大小/格式）；`analyzer_url`
  非空时显示"在 Analyzer 中打开"按钮

设计决策：
1. **SSR 而非 SSG**：随数据库实时更新，加新数据集刷新即见；为未来动态功能铺路。
2. **tab 而非长滚动**：notebook HTML 重，独立 tab 懒加载，首屏只渲染轻量 Overview。
3. **iframe 隔离 notebook**：防 nbconvert 自带样式污染 portal。v0 固定高度。
4. **代码示例用 `load_dataset()`**：即使 SDK 未实现，先展示目标 API 形态，倒逼契约。
5. **shadcn/ui + Tailwind**：用现成组件。

## 九、错误处理与边界总览

| 失败点 | 处理 | 影响面 |
|--------|------|--------|
| Pipeline: .h5cd 读取失败 | 中止 ingest，非零退出，不写库 | 该数据集不入库 |
| Pipeline: nbconvert 失败 | warning，notebook 路径留空，其余入库 | Notebook tab 占位 |
| Pipeline: 重复 ingest | UPSERT 幂等 | 无 |
| API: `{id}` 不存在 | 404 + JSON detail | 前端 notFound |
| API: 路径穿越 | slug 白名单 + 路径落点校验 | 安全防线 |
| API: DB 文件缺失 | 启动检查，/health unhealthy | 可探活 |
| Frontend: 后端不可达 | friendly error，不白屏 | 降级提示 |
| Frontend: notebook 不可用 | Notebook tab 占位文案 | 局部降级 |
| Frontend: analyzer_url 空 | 按钮不渲染 | 无 |

原则：单个产物失败只降级局部；数据完整性失败则拒绝入库。

## 十、测试策略

```
tests/
├── pipeline/
│   ├── test_ingest.py            用 example-data 小 .h5cd fixture 验证提取正确
│   ├── test_ingest_idempotent.py 重复 ingest 不产生重复行
│   └── test_qc.py                坏 .h5cd/缺列 → 正确中止
├── backend/
│   ├── test_api_datasets.py      TestClient: 列表/详情/404
│   ├── test_facets.py
│   └── test_security.py          路径穿越被拒
└── frontend/                     v0 关键路径手测，Playwright 留 v1
```

关键决策：
- **Pipeline 测试用真实小 .h5cd**：`example-data/` 已有 Takei 小 fixture（~750KB）
  和 mESC FISH 测试数据，符合项目"真实数据验证"纪律，不用合成数据糊弄。
- **后端用 FastAPI `TestClient`** + 临时 SQLite + seed 数据。
- **前端 v0 不上自动化**：页面少逻辑薄，关键路径手测；E2E 留 v1。
- **验证纪律**：实现完成后真跑一遍 ingest 把 Takei fixture 导入、起前后端、确认
  端到端跑通，而非"测试通过就算完"。

## 十一、完整链路

```
catalog/*.yaml + .h5cd
   → pipeline ingest（提取统计 + nbconvert）
   → portal.db + notebooks/*.html
   → FastAPI 读库提供 REST
   → Next.js SSR 渲染列表页 + 详情页（Overview/Notebook/Download）
   → 下载指向 Zenodo 外链；"在 Analyzer 打开"指向 webapp
```

## 十二、不做的（v0 范围外）

- 交互式 Plotly 图（UMAP/热图/距离矩阵）→ v1
- 轻量 3D 浏览器 → v2（复杂 3D 转交 webapp）
- 用户系统、数据集提交、QC 审核队列 → 生态阶段
- Python SDK 实现 → v1（v0 仅在 UI 展示目标 API 形态）
- 下载量统计、全文搜索 → 按需

## 十三、v0 已实现状态 + v1 跟进项

**v0 已完成（2026-06-10）**：12 任务 TDD 实现，26 测试通过，已在真实 .h5cd
（mesc_sox2_test）端到端验证（ingest → REST → SSR）。提交范围
`bc35948..HEAD`。

**v1 跟进项**（最终代码评审记录，按优先级）：

1. **（已在 v0 修复）NaN cell_type 归入 "unassigned" 桶** —— 原 `value_counts()`
   丢弃 NaN，导致真实 Takei 数据细胞类型分布不等于 n_cells。已用
   `dropna=False` + 显式 unassigned 桶修复。
2. **缩略图**：`thumbnail_url` 当前指向尚不存在的 `/thumbnail` 端点（因
   `thumbnail_path` 从不写入而处于惰性状态）。v1 实现该端点 + notebook 代表图
   提取，或在此前移除 `thumbnail_url`/`thumbnail_path`/`resolution` 三个未用字段。
3. **筛选/搜索 UI**：后端 `/api/datasets?organism=&technology=&q=` 与
   `/api/facets` 已完整支持，但前端列表页尚无筛选控件（`getFacets` 已导出未用）。
   v1 接上 UI 即可，无需后端改动。
4. **data_root 单一来源**：ingest 的 `--data-dir` 与 API 读路径需保持一致；
   生产默认值一致，但应统一来源或在文档中固化约束。
5. **notebook iframe `sandbox` 属性** + `<html lang>` 与中文 UI 对齐（防御纵深 +
   i18n 一致性）。
6. **`/api/health` 计数**：当前计入 draft，与其他端点的 published 过滤不一致
   （仅探活用途，影响轻微）。
7. **真实 Takei 数据集上线**：当 full .h5cd 托管到 Zenodo 后，新增其 catalog
   YAML 并 ingest，按项目纪律在 PR 报告真实数据指标（细胞数/marker 数/分布）。
   这是 portal 配合论文发表的关键一步。
