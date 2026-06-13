# Gosling.js Spec 参考文档

> 面向本项目（**gosling.js@1.0.7** + React 18 + HiGlass + PixiJS）的可视化 spec 规范参考。
> 说明用中文，代码示例用英文。所有结论均来自 Gosling 官方文档（见文末参考来源）。

> **本项目实测结论（2026-06-12 验证）**：从 gosling 2.0.0-alpha.10 降级到 **1.0.7** 后，
> 配合下列修复，Gosling contact map 已能用 WebGL 正常渲染。**数据加载后**控制台仅剩 4 条
> React 弃用警告（`findDOMNode` / `legacy childContextTypes` / `legacy contextTypes` /
> `componentWillReceiveProps`），全部来自 `node_modules/gosling.js` 内部的 HiGlass 老依赖
> （`react-grid-layout` / `react-sortable-hoc`），**与本项目源码及 spec 无关，无法在不 fork
> gosling.js 的前提下消除**（React 用 `console.error` 打印 lifecycle 弃用警告，所以它们显示为红色
> ERROR，但本质是 warning）。
>
> **重要教训**：早先误把「页面一打开就一连串 404 报错」也归进「无害警告」——这是错的。
> 那批 404（`tileset_info` / `tads` → `Error retrieving tilesetInfo` / `[Gosling Data Fetcher]
> Error` / `Cannot read properties of undefined (reading 'filter')`）是**真 bug**：前端在后端
> session 还没加载数据时就无条件挂载了 local contact map spec，Gosling 去拉空 session 的端点
> 全部 404，CSV fetcher 拿到 undefined 再 `.filter()` 直接崩。修复见下方第 6 条与排错表。
>
> 完成的关键修复：
> 1. **降级到 gosling.js@1.0.7**（`--save-exact`），对齐 package.json / lock / node_modules，
>    用回 React 18 + forwardRef → 消除 ref 警告。
> 2. **移除 `<StrictMode>`**（main.tsx）→ 消除 HiGlass/PixiJS 双重挂载崩溃
>    （`checkMaxIfStatementsInShader` 收到 0 / `Cannot read 'destroy' of null`）。
> 3. **重写 `localContactMapSpec.ts` 的 overlay 结构**：heatmap + TAD 边界用一个
>    `alignment:'overlay'` 父容器 + 嵌套 `tracks:[...]` → 消除 `track.tracks is not iterable`。
> 4. **TAD 边界 track 从 `type:'json'` 改为 `type:'csv'`** + 后端 `/api/tads` 等新增
>    `format=csv` 输出（空数据也返回表头）→ 消除 `Please provide values of the JSON data`。
> 5. （后端连带修复）`call_tads_by_pval(cd, chrom, params)` 等三处漏传 `chrom` 参数；
>    `statsmodels` 加入 `pyproject.toml` / `requirements.txt`（TAD/compartment caller 运行期依赖）。
> 6. **数据未加载时不挂载 local contact map spec**（`GenomicPanel.tsx`）：用 store 的
>    `dataVersion > 0` 门控，`specToRender = activeSpec ?? (hasData ? LOCAL_CONTACT_MAP_SPEC : null)`，
>    `null` 时渲染「No data loaded」空状态 → 彻底消除空 session 的 404 风暴和 CSV fetcher 的
>    `.filter()` 崩溃。验证：加载 `test_20cells_chr21.h5cd` 后 `tileset_info` / `tads?format=csv`
>    / `tiles`（批量 9 瓦片）全部 200，heatmap + TAD track 正常渲染。

---

## 0. 快速排错（先看这里）

| 报错 / 现象 | 根因 | 修复 |
|---|---|---|
| `track.tracks is not iterable` | 在 leaf track 上写了 `alignment: 'overlay'`，但**没有提供嵌套的 `tracks: [...]` 数组**。编译器看到 `alignment: 'overlay'` 后会去遍历 `track.tracks`，发现它是 `undefined` 于是崩溃。 | overlay 必须是「父 track 容器」结构：`{ alignment: 'overlay', tracks: [ {mark:...}, {mark:...} ] }`。叠加 = 多个子 track 共享坐标域。详见 [§4.2](#42-overlaid-tracks叠加)。 |
| `Please provide values of the JSON data` | `data.type: 'json'` **只支持内联 `values` 数组，不支持远程 `url`**。你给了 `{type:'json', url:'...'}`，缺少 `values`。 | 要么把数据内联成 `values: [...]`（官方建议 ~100 行以内）；要么数据放远程时改用 `type: 'csv'`（支持 `url`）。详见 [§5.1](#51-json内联) 与 [§5.2](#52-csv远程-url)。 |
| `ref` 相关警告 / `gosRef.current` 为 `null` / `Cannot read 'api' of null` | React 版本与 gosling 版本的 ref 机制不匹配。**1.x 用 `forwardRef`**（标准 `useRef` + `ref={gosRef}`，通过 `gosRef.current.api.xxx()` 访问）；**2.0 改成 ref-as-prop 并移除了 React/HiGlass 依赖**。在 1.0.7 上请用 1.x 的写法，且 React 必须是 16/17/18。 | 1.0.7 → `const gosRef = useRef(null); <GoslingComponent ref={gosRef} spec={...}/>`，调用前判空 `if (gosRef.current) {...}`。详见 [§8](#8-react-goslingcomponent-用法)。 |
| 渲染空白 / HiGlass 样式错乱 | 缺少 HiGlass 的 CSS。 | 在 HTML `<head>` 引入 `https://esm.sh/higlass@1.13/dist/hglib.css`。详见 [§8.1](#81-安装与依赖)。 |
| circular layout 下 track 不显示 / 高度异常 | 当 `alignment: 'overlay'` 时 `width`/`height` 是**必填**的；circular 下 `height` 控制环厚度比例。 | overlay 容器显式写 `width` 和 `height`。 |
| `byte length of Float32Array should be a multiple of 4`（at `tileResponseToData`） | matrix 瓦片的 `dense` 字段被后端 **gzip 压缩**后再 base64。但 Gosling 1.0.7 的瓦片解码是 `new Float32Array(base64ToArrayBuffer(dense))`，**不解压**，gzip 字节数非 4 的倍数即崩。 | 后端 `dense` 直接 base64 编码裸 little-endian float32（**不要 gzip**）。256×256×4=262144 字节。 |
| matrix schema 校验失败 / `No dataConfig children, server or tilesetUid: {server:}` | 1.0.7 `MatrixData` schema **只接受 `url`**（无 `server`/`tilesetUid`），且 url 必须含字面量 `tileset_info/?d=`（**带尾斜杠**）——编译器靠 split 这个子串推导 server+tilesetUid。 | matrix data 只写 `{type:'matrix', url:'.../tileset_info/?d=<uid>'}`。 |
| matrix 热图渲染空白 / 只有坐标轴 | matrix 是 **2D track**，`IsHiGlassMatrix` 要求同时有 `x/xe` **和 `y/ye`**，字段名为 `xs/xe/ys/ye`，`mark:'bar'`。少了 y 通道则不渲染热图。 | 四个位置通道齐全：`x:{field:'xs'} xe:{field:'xe'} y:{field:'ys'} ye:{field:'ye'}`，`mark:'bar'`。 |
| matrix 数据正确但画布空白 | viewport 落在 contact 数据所在染色体**之外**（如默认 chr1 而数据是 chr21）。 | 把 viewport `xDomain` 设到数据染色体；或 UI 切换到对应染色体。 |
| `CsvData` schema 拒绝 `quantitativeFields` | 1.0.7 `CsvData` **没有 `quantitativeFields`**（那是 JSON data 字段）。csv loader 自动推断类型。 | 从 csv data 里删掉 `quantitativeFields`。 |
| 页面一打开就一连串 `404` + `Error retrieving tilesetInfo` + `[Gosling Data Fetcher] Error` + `Cannot read properties of undefined (reading 'filter')` | 前端在后端 session **还没加载数据**时就无条件挂载了 local contact map spec。Gosling 去拉空 session 的 `tileset_info` / `tads` 端点（设计上无数据返回 404），CSV fetcher 拿到 undefined 响应后执行 `.filter()` 崩溃。`--reload` 重启后 session 清空会复现。 | 用「数据是否已加载」状态门控 spec 挂载。本项目用 store 的 `dataVersion > 0`：`specToRender = activeSpec ?? (hasData ? LOCAL_CONTACT_MAP_SPEC : null)`，`null` 时渲染空状态而非 `<GoslingComponent>`。详见 `GenomicPanel.tsx`。 |
| `findDOMNode is deprecated` / `legacy childContextTypes` / `legacy contextTypes` / `componentWillReceiveProps renamed` | HiGlass 内部用老式 class 组件 API（`react-grid-layout` / `react-sortable-hoc`），在 `node_modules/gosling.js` 里。React 用 `console.error` 打印这些 lifecycle 弃用警告，所以**显示为红色 ERROR，但本质是 warning**。共 4 条，**无害、无法也无需修改**（除非 fork gosling.js）。 | 忽略；或后续升级 Gosling 2.0（移除 HiGlass）后自然消失。若一定要让控制台干净，可在自己代码里精准过滤这几条已知字符串（吞 `console.error` 有掩盖未来真 error 的风险，慎用）。 |

---

## 1. Gosling 是什么

Gosling.js 是一套**声明式的交互式 (epi)genomics 可视化语法**（declarative grammar）。一个可视化由一份 **Gosling specification（spec）**定义 —— 本质是一个 JSON 对象，其结构与取值受 Gosling grammar 约束（类比 Grammar of Graphics 之于通用图表）。库接收 spec 作为输入，渲染出对应可视化，并通过 JavaScript API（如 zoomTo、subscribe）支持程序化交互。

核心层级关系：

```
GoslingSpec (root)
└── views[]            (多视图，受 arrangement 控制排布)
    └── tracks[]       (一个 view 内的多个 track，受 alignment 控制叠加/堆叠)
        └── (overlay 时) tracks[]   (嵌套子 track)
```

三个核心组合属性（贯穿全文）：

- **`layout`** —— 渲染坐标系：`linear`（笛卡尔）或 `circular`（极坐标）。
- **`alignment`** —— 一个 view 内多个 track 的对齐方式：`overlay`（叠加）或 `stack`（堆叠，默认）。
- **`arrangement`** —— 多个 view 之间的排布：`parallel` / `serial` / `vertical` / `horizontal`。

---

## 2. 顶层 GoslingSpec 结构

顶层 spec 既可以是「单 view 简写」（直接写 `tracks`），也可以是「多 view」（写 `views`）。常见顶层字段：

| 字段 | 类型 | 含义 / 取值 |
|---|---|---|
| `title` | string | 标题 |
| `subtitle` | string | 副标题 |
| `assembly` | string \| array | 基因组版本：`"hg38"`(默认) / `"hg19"` / `"hg18"` / `"hg17"` / `"hg16"` / `"mm10"` / `"mm9"` / `"unknown"`。设为 `"unknown"` 时坐标轴不显示 `chrN:` 标签。也可传 `[[chrName, size], ...]` 自定义。 |
| `layout` | string | `"linear"` / `"circular"`，作用于所有 view（可被单个 view 覆盖）。 |
| `arrangement` | string | 多 view 排布：`"parallel"` / `"serial"` / `"horizontal"` / `"vertical"`。 |
| `views` | array | 视图数组（多视图模式）。可层级嵌套。 |
| `tracks` | array | 轨道数组（单视图简写模式，直接挂在根上）。 |
| `spacing` | number | 间距：linear 为像素，circular 为相对比例。 |
| `style` | Style | 全局样式，可被子级覆盖。 |
| `static` | boolean | 禁用缩放/平移，默认 `false`。 |
| `centerRadius` | number | circular 中心留白半径占比，0–1，默认 `0.3`。 |
| `xDomain` / `yDomain` | Domain | 初始可见基因组区间。 |
| `xOffset` / `yOffset` | number | 视图像素偏移。 |
| `linkingId` | string | 跨 view 联动 ID。 |
| `zoomLimits` | array | 缩放范围限制。 |
| `id` | string | view/track 的 ID，供 JS API（如 `zoomTo`）定位。 |

> 注：`width` / `height` 写在 track 级别（linear 直接是像素；circular 下 `height` 表示环厚度比例）。当 `alignment: 'overlay'` 时 `width`/`height` 为**必填**。

最小可运行 spec（单视图简写）：

```json
{
  "title": "Minimal Example",
  "assembly": "hg38",
  "layout": "linear",
  "tracks": [
    {
      "data": {
        "url": "https://server.gosling-lang.org/api/v1/tileset_info/?d=cistrome-multivec",
        "type": "multivec",
        "row": "sample",
        "column": "position",
        "value": "peak",
        "categories": ["sample 1"]
      },
      "mark": "rect",
      "x": { "field": "position", "type": "genomic" },
      "color": { "field": "peak", "type": "quantitative", "legend": true },
      "width": 600,
      "height": 130
    }
  ]
}
```

---

## 3. Layout：linear vs circular

在根上统一设置：

```json
{ "layout": "linear", "views": [ /* ... */ ] }
```

或在单个 view 内覆盖：

```json
{ "layout": "circular", "tracks": [ /* ... */ ] }
```

- **linear**：`width`（像素）、`height`（像素）。
- **circular**：`width`（像素）、`height`（每个 track 自己设，控制环的厚度比例）、`centerRadius`（中心留白半径 / 整体半径，默认 `0.3`）。

两种 layout 都靠 `width`/`height` 切换，但 `height` 在两者含义不同（circular 下是环厚度）。

---

## 4. Track 的三种组合模式（最关键部分）

一个 **track** 是基本构建块（柱状图、折线、ideogram 等）；多个 track 组成一个 **view**。view 决定基因组位置，track 定义数据编码。

### 4.1 Single track（单轨）

最简单：`tracks` 数组里只有一个 track 对象。

```json
{
  "title": "Single Track - Bar Chart",
  "assembly": "hg38",
  "layout": "linear",
  "tracks": [
    {
      "data": {
        "url": "https://server.gosling-lang.org/api/v1/tileset_info/?d=cistrome-multivec",
        "type": "multivec",
        "row": "sample",
        "column": "position",
        "value": "peak",
        "categories": ["sample 1"]
      },
      "mark": "bar",
      "x": { "field": "position", "type": "genomic", "axis": "bottom" },
      "y": { "field": "peak", "type": "quantitative" },
      "width": 600,
      "height": 130
    }
  ]
}
```

### 4.2 Overlaid tracks（叠加）

**这是踩坑重灾区。** 叠加 = 多个子 track 画在**同一块画布、共享坐标系**上（例如 line + point 叠加，或 ideogram 的 rect + text + triangle 叠加）。

规则（务必牢记）：

1. 必须用「**父 track 容器**」结构：父 track 上写 `"alignment": "overlay"`，并提供嵌套的 **`"tracks": [ ... ]`** 子数组。
2. 父 track 上写的 `data` / `x` / `y` / `color` 等会被子 track **继承**；子 track 只需写各自不同的部分（如不同的 `mark`）。
3. **绝对不要**在一个叶子 track 上单独写 `"alignment": "overlay"` 而不带嵌套 `tracks` 数组 —— 这会触发 `track.tracks is not iterable` 崩溃。
4. overlay 容器需显式提供 `width` / `height`。

正确写法（line + point 叠加，二者共享 data/x/y）：

```json
{
  "title": "Overlaid Track - line + point",
  "assembly": "hg38",
  "layout": "linear",
  "tracks": [
    {
      "alignment": "overlay",
      "data": {
        "url": "https://server.gosling-lang.org/api/v1/tileset_info/?d=cistrome-multivec",
        "type": "multivec",
        "row": "sample",
        "column": "position",
        "value": "peak",
        "categories": ["sample 1"]
      },
      "x": { "field": "position", "type": "genomic", "axis": "bottom" },
      "y": { "field": "peak", "type": "quantitative" },
      "color": { "field": "sample", "type": "nominal" },
      "width": 600,
      "height": 130,
      "tracks": [
        { "mark": "line" },
        {
          "mark": "point",
          "size": { "field": "peak", "type": "quantitative", "range": [0, 6] }
        }
      ]
    }
  ]
}
```

ideogram 风格（rect + text + triangle 叠加，每个子 track 可有自己的 mark / 编码）的结构同理：父容器 `alignment: 'overlay'` + 共享 `data`，`tracks` 里放多个不同 `mark` 的子 track。

> 在「stacked 里嵌 overlaid」的复杂场景，官方明确建议：**用嵌套结构**——外层 view 用 `alignment: 'stack'`（或默认），其中某个 track 自身是一个 `alignment: 'overlay'` + `tracks: [...]` 的容器。

错误写法（会崩，反面教材）：

```json
// ❌ WRONG — leaf track 上写了 alignment:'overlay' 却没有嵌套 tracks 数组
// → 抛出 "track.tracks is not iterable"
{
  "tracks": [
    {
      "alignment": "overlay",
      "data": { /* ... */ },
      "mark": "line",
      "x": { "field": "position", "type": "genomic" },
      "y": { "field": "peak", "type": "quantitative" }
    }
  ]
}
```

### 4.3 Stacked tracks（堆叠）

堆叠 = 多个 track 在垂直方向平铺，每个占一块区域。`alignment: 'stack'` 是**默认值**，所以通常只要把多个 track 平铺进 `tracks` 数组即可。

```json
{
  "title": "Stacked Tracks",
  "assembly": "hg38",
  "layout": "linear",
  "alignment": "stack",
  "spacing": 10,
  "tracks": [
    {
      "data": { "url": "https://server.gosling-lang.org/api/v1/tileset_info/?d=cistrome-multivec",
                "type": "multivec", "row": "sample", "column": "position",
                "value": "peak", "categories": ["sample 1"] },
      "mark": "bar",
      "x": { "field": "position", "type": "genomic" },
      "y": { "field": "peak", "type": "quantitative" },
      "width": 600, "height": 100
    },
    {
      "data": { "url": "https://server.gosling-lang.org/api/v1/tileset_info/?d=cistrome-multivec",
                "type": "multivec", "row": "sample", "column": "position",
                "value": "peak", "categories": ["sample 2"] },
      "mark": "line",
      "x": { "field": "position", "type": "genomic" },
      "y": { "field": "peak", "type": "quantitative" },
      "width": 600, "height": 100
    }
  ]
}
```

### 4.4 View-level 组合（多视图、circular vs linear）

多个 view 之间用 `arrangement` 控制排布，view 可层级嵌套（一个 view 内部又可以包含 `views`）。

```json
{
  "title": "Multiple Views",
  "arrangement": "parallel",
  "views": [
    {
      "layout": "linear",
      "tracks": [ /* ... */ ]
    },
    {
      "arrangement": "serial",
      "views": [
        { "layout": "circular", "tracks": [ /* ... */ ] },
        { "layout": "circular", "tracks": [ /* ... */ ] }
      ]
    }
  ]
}
```

View 级关键属性：

| 属性 | 类型 | 说明 |
|---|---|---|
| `layout` | string | `"linear"` / `"circular"` |
| `alignment` | string | `"stack"`(默认) / `"overlay"` |
| `arrangement` | string | `"parallel"` / `"serial"` / `"horizontal"` / `"vertical"` |
| `spacing` | number | track/view 间距（linear 像素，circular 相对值） |
| `static` | boolean | 禁用缩放/平移，默认 `false` |
| `assembly` | string | 基因组版本（见 §2） |
| `linkingId` | string | 跨 view 联动 |
| `centerRadius` | number | circular 中心留白比例，默认 `0.3` |
| `xDomain` / `yDomain` | Domain | 可见基因组区间 |
| `orientation` | string | `"horizontal"` / `"vertical"` |
| `id` | string | 供 JS API 定位的 view ID |

---

## 5. Data Source 类型

数据分两大类：**Plain（无需 HiGlass server，直接读文件）** 和 **Pre-aggregated（需要 HiGlass tileset server）**。

### 5.1 JSON（内联）

- **必填**：`type: "json"`、`values`（JSON 数组形式的内联数据）。
- **不支持 `url`**（这是 `Please provide values of the JSON data` 报错的根因）。
- 可选：`chromosomeField`、`genomicFields`、`sampleLength`、`genomicFieldsToConvert`(experimental)。
- 官方建议：仅用于**小数据（~100 行以内）**，更大数据改用 `csv`。

```json
{
  "data": {
    "type": "json",
    "chromosomeField": "Chromosome",
    "genomicFields": ["chromStart", "chromEnd"],
    "values": [
      { "Chromosome": "chr1", "chromStart": 0,       "chromEnd": 2300000, "Name": "p36.33", "Stain": "gneg"   },
      { "Chromosome": "chr1", "chromStart": 2300000, "chromEnd": 5300000, "Name": "p36.32", "Stain": "gpos25" }
    ]
  }
}
```

### 5.2 CSV（远程 url）

- **必填**：`type: "csv"`、`url`。
- 可选：`separator`(默认 `,`)、`sampleLength`、`headerNames`、`genomicFields`、`chromosomeField`、`chromosomePrefix`，以及实验性 `longToWideId`、`genomicFieldsToConvert`。
- 适用于任何足够小的表格文件（tsv/csv/BED/BEDPE/GFF）。**需要远程 URL 时用它，而不是 json。**

```json
{
  "data": {
    "url": "https://raw.githubusercontent.com/sehilyi/gemini-datasets/master/data/UCSC.HG38.Human.CytoBandIdeogram.csv",
    "type": "csv",
    "chromosomeField": "Chromosome",
    "genomicFields": ["chromStart", "chromEnd"]
  }
}
```

### 5.3 BigWig

- **必填**：`type: "bigwig"`、`url`。
- 可选：`value`(默认 `"value"`)、`start`、`end`、`column`(默认 `"position"`)、`binSize`、`aggregation`(`"mean"`/`"sum"`，默认 `"mean"`)。

```json
{
  "data": {
    "url": "https://s3.amazonaws.com/gosling-lang.org/data/4DNFIMPI5A9N.bw",
    "type": "bigwig",
    "column": "position",
    "value": "peak"
  }
}
```

### 5.4 Multivec（需 HiGlass server）

多样本/分类的预聚合数据（ChIP-seq、DNase-seq、序列等）。

- **必填**：`type: "multivec"`、`url`。
- 可选：`value`(默认 `"value"`)、`row`(默认 `"category"`)、`column`、`start`、`end`、`categories`、`binSize`、`aggregation`。

```json
{
  "data": {
    "url": "https://resgen.io/api/v1/tileset_info/?d=UvVPeLHuRDiYA3qwFlm7xQ",
    "type": "multivec",
    "row": "sample",
    "column": "position",
    "value": "peak",
    "categories": ["sample 1", "sample 2", "sample 3", "sample 4"]
  }
}
```

### 5.5 Vector（需 HiGlass server）

单值的预聚合一维数据。

- **必填**：`type: "vector"`、`url`。
- 可选：同 BigWig（`value`/`start`/`end`/`column`/`binSize`/`aggregation`）。

```json
{
  "data": {
    "url": "https://resgen.io/api/v1/tileset_info/?d=VLFaiSVjTjW6mkbjRjWREA",
    "type": "vector",
    "column": "position",
    "value": "peak"
  }
}
```

### 5.6 BEDDB（需 HiGlass server）

预处理的 BED 数据库（基因注释、ClinVar 等）。

- **必填**：`type: "beddb"`、`url`、`genomicFields`（`{index, name}` 对象数组）。
- 可选：`valueFields`（`{index, name, type}`）、`exonIntervalFields`(experimental)。

```json
{
  "data": {
    "url": "https://higlass.io/api/v1/tileset_info/?d=OHJakQICQD6gTD7skx4EWA",
    "type": "beddb",
    "genomicFields": [
      { "index": 1, "name": "start" },
      { "index": 2, "name": "end" }
    ],
    "valueFields": [
      { "index": 5, "name": "strand", "type": "nominal" },
      { "index": 3, "name": "name",   "type": "nominal" }
    ]
  }
}
```

### 5.7 索引型大文件：BAM / BED / GFF3 / VCF

这几类都需要配套的索引文件 `indexUrl`（`.tbi` / `.bai`）。

| 类型 | 必填 | 常用可选 |
|---|---|---|
| `bam` | `type`、`url`、`indexUrl` | `maxInsertSize`(5000)、`loadMates`(false)、`extractJunction`(false)、`junctionMinCoverage`(1) |
| `bed` | `type`、`url`、`indexUrl` | `sampleLength`(1000)、`customFields`（文件内 chrom/chromStart/chromEnd 必须存在） |
| `gff` | `type`、`url`、`indexUrl` | `sampleLength`(1000)、`attributesToFields` |
| `vcf` | `type`、`url`、`indexUrl` | `sampleLength`(1000)，仅支持已索引的 VCF |

```json
{
  "data": {
    "url": "https://s3.amazonaws.com/gosling-lang.org/data/bed/chr1_CDS_BED12.bed.gz",
    "indexUrl": "https://s3.amazonaws.com/gosling-lang.org/data/bed/chr1_CDS_BED12.bed.gz.tbi",
    "type": "bed"
  }
}
```

### 5.8 关于 matrix / Hi-C（重要说明）

> **在 Gosling 官方文档的 Data、Public Datasets、Usage 页面中，均未出现独立的 `type: "matrix"` 数据类型，也没有列出 Hi-C contact matrix 的官方示例。** 当前文档化的预聚合类型只有 `vector` / `multivec` / `beddb`（以及 plain 类的 csv/json/bigwig/bam/bed/gff/vcf）。
>
> 因此，如果本项目需要渲染 Hi-C 交互矩阵热图：
> - 不要假定 `{ type: 'matrix', url, server, tilesetUid }` 一定可用 —— 该字段在 1.0.7 的公开文档里**未被记载**，需要以实际 TypeScript 类型定义 / examples 为准再确认。
> - 矩阵热图在 Gosling 里通常是用 **`mark: "rect"`** + 行列双 genomic 编码来表达；具体 data 类型请核对 `gosling.js` 的 schema/类型定义（`node_modules/gosling.js` 里的 d.ts）后再用。
> - 若确实有 HiGlass cooler/matrix tileset，更稳妥的路线是直接确认安装包内的类型声明，而非照搬未文档化字段。

---

## 6. Visual Channels（视觉通道）

每个通道可以**绑定数据字段**，也可以**赋常量值**。绑定字段时 Gosling 把数据值（domain）映射到视觉值（range）。

通道定义的通用属性：

- `field` —— 数据字段名
- `type` —— 数据类型：`"genomic"` / `"quantitative"` / `"nominal"`
- `domain` —— 输入数据值范围
- `range` —— 输出视觉值范围
- `legend` —— 是否显示图例，默认 `false`
- `axis` —— 轴位置：`"none"` / `"top"` / `"bottom"` / `"left"` / `"right"`

常量赋值：`"color": { "value": "steelblue" }`。

| 通道 | 用途 | 支持的 `type` |
|---|---|---|
| `x` / `xe` | 水平位置，`xe` 为终点（基因组区间）；含 `linkingId`、`grid` | `genomic` |
| `y` / `ye` | 垂直位置，`ye` 为终点；含 `zeroBaseline`(默认 true)、`flip`、`baseline`(默认 0) | `quantitative` / `nominal` / `genomic` |
| `x1 x1e y1 y1e` | 仅用于 link mark，连接一对基因组区间 | `genomic` |
| `row` | 配合 `y` 按分类把视图分层（仅 nominal）；`range` 默认 `[0, height]` | `nominal` |
| `size` | 圆半径 / 三角或 rect 边长 / 线宽 | `quantitative` / `nominal` |
| `text` | text mark 显示的文字内容 | `quantitative` / `nominal` |
| `color` | 前景填充色；含 `title`、`scale`(`linear`/`log`)、`scaleOffset` | `quantitative` / `nominal` |
| `stroke` | 描边色（rect/area/point/bar/link） | `quantitative` / `nominal` |
| `strokeWidth` | 描边粗细（同上 mark） | `quantitative` / `nominal` |
| `opacity` | 透明度（同时影响 color 和 stroke） | `quantitative` / `nominal` |

> 注意：**每种 mark 只支持通道的一个子集**（如 `point` 支持 `size`，而 `line` 不支持）。

nominal → 颜色映射示例：

```json
{
  "mark": "rect",
  "color": {
    "field": "Stain",
    "type": "nominal",
    "domain": ["gneg", "gpos25", "gpos50", "gpos75", "gpos100", "gvar"],
    "range": ["white", "#D9D9D9", "#979797", "#636363", "black", "#A0A0F2"]
  }
}
```

`row` 分层示例：

```json
{
  "mark": "line",
  "x": { "field": "position", "type": "genomic", "domain": {"chromosome": "1", "interval": [1, 3000500]}, "axis": "top" },
  "y": { "field": "peak", "type": "quantitative" },
  "color": { "field": "sample", "type": "nominal", "legend": true },
  "row": { "field": "sample", "type": "nominal" }
}
```

---

## 7. Mark 类型

Gosling 的基本 mark 类型：**point, line, area, bar, rect, text, link（含 withinLink / betweenLink）, triangle（triangleLeft/Right/Bottom）**。

| mark | 画什么 | 常用通道 |
|---|---|---|
| `point` | 圆点（散点 / bubble） | `x`(genomic), `y`(quantitative), `size`, `color` |
| `line` | 折线连接数据点 | `x`(genomic), `y`(quantitative) |
| `area` | 面积图（上沿折线，下沿 x 轴） | `x`, `y`, `color` |
| `bar` | 柱状图（高度编码值） | `x`(genomic), `y`(quantitative) |
| `rect` | 矩形（基因组区间 / 矩阵） | `x`/`xe`(区间边界), `color`, `size`(高度) |
| `text` | 文本标签（基因名 / 碱基） | `x`/`xe`, `y`, `color`, `text` |
| `link` (`withinLink`/`betweenLink`) | 弧形连接 | `x`/`xe`(弧起点), `x1`/`x1e`(弧终点), `stroke` |
| `triangle*` | 三角（Left/Right/Bottom） | `x`(genomic), `size` |

point：

```json
{
  "mark": "point",
  "x": { "field": "position", "type": "genomic", "axis": "top" },
  "y": { "field": "peak", "type": "quantitative" }
}
```

rect（区间 + nominal 颜色 + 常量高度）：

```json
{
  "mark": "rect",
  "color": { "field": "Stain", "type": "nominal",
             "domain": ["gneg", "gpos25", "gpos50", "gpos75", "gpos100", "gvar"],
             "range": ["white", "#D9D9D9", "#979797", "#636363", "black", "#A0A0F2"] },
  "x":  { "field": "chromStart", "type": "genomic", "axis": "top" },
  "xe": { "field": "chromEnd",   "type": "genomic" },
  "size": { "value": 30 }
}
```

text（碱基标注）：

```json
{
  "mark": "text",
  "style": { "textStrokeWidth": 0 },
  "x":  { "field": "start", "type": "genomic", "axis": "top" },
  "xe": { "field": "end",   "type": "genomic" },
  "y":  { "field": "count", "type": "quantitative" },
  "color": { "field": "base", "type": "nominal", "domain": ["A", "T", "G", "C"] },
  "text":  { "field": "base", "type": "nominal" }
}
```

withinLink（弧形，circular）：

```json
{
  "mark": "withinLink",
  "x":   { "field": "s1", "type": "genomic", "domain": {"chromosome": "1"}, "axis": "top" },
  "xe":  { "field": "e1", "type": "genomic" },
  "x1":  { "field": "s2", "type": "genomic", "domain": {"chromosome": "1"}, "axis": "top" },
  "x1e": { "field": "e2", "type": "genomic" },
  "stroke": { "value": "steelblue" },
  "style": { "circularLink": true }
}
```

triangleRight：

```json
{
  "mark": "triangleRight",
  "x": { "field": "end", "type": "genomic", "axis": "top" },
  "size": { "value": 15 }
}
```

> 跨染色体连接：加载数据时用 `genomicFieldsToConvert`（experimental，仅 csv/json）把染色体字段转成 genomic 字段。

---

## 8. React GoslingComponent 用法

### 8.1 安装与依赖

```bash
# 官方给的是 yarn 形式
yarn add gosling.js higlass pixi.js react@18 react-dom@18
```

并在 HTML `<head>` 引入 HiGlass 样式（**漏了会渲染异常/空白**）：

```html
<head>
  <link rel="stylesheet" href="https://esm.sh/higlass@1.13/dist/hglib.css" />
</head>
```

> Gosling 1.x 支持 React **16 / 17 / 18**。本项目用 React 18 + gosling 1.0.7 是匹配的。

### 8.2 基本渲染

```jsx
import { GoslingComponent } from "gosling.js";

function App() {
  return <GoslingComponent spec={yourSpec} />;
}
```

### 8.3 GoslingComponent Props（1.x）

| Prop | 类型 | 说明 |
|---|---|---|
| `spec` | object | Gosling 规范 |
| `padding` | number | 组件内边距 |
| `margin` | number | 组件外边距 |
| `border` | string | 边框样式 |
| `id` | string | 组件 ID |
| `className` | string | CSS 类名 |
| `theme` | object | 主题配置 |
| `reactive` | boolean | 默认 `true`；spec 更新时已有 track 保持缩放位置 |
| `urlToFetchOptions` | object | URL → `RequestInit` 映射，给匹配数据源加请求选项 |

> 注：1.0.x 文档未列出 `compiled` / `experimental` props。

### 8.4 通过 ref 拿 API（1.x = forwardRef 写法）

```jsx
import React, { useRef, useEffect } from "react";
import { GoslingComponent } from "gosling.js";

function App() {
  const gosRef = useRef(null);

  useEffect(() => {
    if (gosRef.current) {
      // 1.x：通过 .api 命名空间访问
      gosRef.current.api.exportPdf();
    }
  }, []);

  return <GoslingComponent ref={gosRef} spec={yourSpec} />;
}
```

### 8.5 API 方法

导航：

```js
gosRef.current.zoomTo(viewId, position, padding?, duration?);
// position: "chr1" 或 "chr1:1-10000"；padding 单位 bp(默认0)；duration 毫秒(默认1000)
gosRef.current.api.zoomToExtend(viewId, duration?);   // 缩放到整个基因组
gosRef.current.zoomToGene(viewId, gene, padding?, duration?);  // 按基因名导航，如 "MYC"
gosRef.current.getViewIds();   // 返回 view id 列表（viewId 对应 spec 里的 track.id）
```

导出：

```js
gosRef.current.exportPng(transparentBackground?);  // 默认 false
gosRef.current.exportPdf(transparentBackground?);
gosRef.current.getCanvas({ resolution = 4, transparentBackground = false });
// 返回 { canvas, canvasWidth, canvasHeight, resolution }
```

事件订阅：

```js
gosRef.current.subscribe(eventName, (msg, eventData) => { /* ... */ });
// eventName: "mouseOver" | "rangeSelect" | "click" | "rawData" | "onNewTrack" | "onNewView" | "location"
gosRef.current.unsubscribe(eventName);
// unsubscribe 支持: "mouseOver" | "rangeSelect" | "click" | "rawData" | "location"
```

`eventData` 形状随事件不同（节选）：

```js
// click / mouseOver
{ id, data: [{...}], genomicPosition: { chromosome, position } }
// rangeSelect
{ id, data: [{...}], genomicRange: [ {chromosome, position}, {chromosome, position} ] }
// location（每次轴范围变化，如缩放时触发）
{ id, genomicRange: [ {chromosome, position}, {chromosome, position} ] }
```

### 8.6 1.x vs 2.0 差异（关键）

| 维度 | **1.x（本项目 1.0.7）** | 2.0 |
|---|---|---|
| 依赖 | 依赖 **React + HiGlass + PixiJS** | **移除了 React 和 HiGlass 依赖** |
| ref 机制 | `forwardRef`：`useRef` + `ref={gosRef}`，通过 `gosRef.current.api.xxx()` 访问 | **ref-as-prop**（React 19 风格，ref 作为普通 prop 传入） |
| React 版本 | 支持 16 / 17 / 18 | 不再绑定特定 React |
| 影响 | 沿用本文 §8.4 写法即可 | 照搬 2.0 的 ref-as-prop 写法到 1.0.7 会出现 ref 警告 / `gosRef.current` 为 null |

> 本项目固定在 **1.0.7**，请严格使用 1.x 的 `forwardRef` + `useRef` + `.api` 写法，不要混用 2.0 的 ref-as-prop。

---

## 9. 参考来源 URL

- Gosling Docs 概览：https://gosling-lang.org/docs/
- Data（数据源类型）：https://gosling-lang.org/docs/data
- Composition（track/view 组合）：https://gosling-lang.org/docs/composition
- Mark（标记类型）：https://gosling-lang.org/docs/mark
- Visual Channel（视觉通道）：https://gosling-lang.org/docs/visual-channel
- Usage（安装与使用）：https://gosling-lang.org/docs/usage
- JavaScript API：https://gosling-lang.org/docs/js-api
- Public Datasets：https://gosling-lang.org/docs/public-datasets
- GitHub 仓库：https://github.com/gosling-lang/gosling.js
- React 模板/示例：https://github.com/WeihangZJP/gosling-react

> 抓取时间：2026-06。`track` 与 `getting-started` 的直链返回 404，相关内容已从 `composition` / `usage` / `js-api` 页面补全。`matrix` 数据类型在上述官方页面均未文档化（见 §5.8）。
