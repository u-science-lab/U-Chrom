# `uchrom.im` 模块说明

`uchrom.im` 是 U-Chrom 中面向成像数据处理的工作流模块，用来把多轮 3D 显微图像逐步转换为可用于 trace 和矩阵分析的结构化结果。

它覆盖的主要阶段包括：

1. 原始 3D 图像读取与轮次组织
2. 2D 投影与全局配准
3. 3D 局部配准
4. 细胞分割
5. 3D spot localization
6. localization 过滤与局部坐标校正
7. trace 构建与距离矩阵生成

当前这套实现同时支持：

- U-Chrom 自己的轻量级处理方法
- 与 pyHiM 对齐的 2D/3D 后端，尤其是 `mask_3d`、`localize_3d`、`filter_localizations`、`register_localizations` 这一条链路


## 1. 模块结构

`uchrom/im` 目录下的主要组成如下：

- `io.py`
  负责图像读取、manifest 解析，以及基础保存接口。
- `prep/`
  负责 z projection 和投影结果保存。
- `reg/`
  负责 2D global registration 与 3D local registration。
- `seg/`
  负责 2D/3D segmentation，包括 pyHiM 风格的 mask 后端。
- `loc/`
  负责 2D/3D localization，当前重点是 `method="pyhim_3d"`。
- `trace/`
  负责 localization 过滤、局部校正、trace 构建与矩阵生成。
- `compare.py`
  提供 notebook 验证和 pyHiM 对比所需的读取、统计与可视化工具。
- `workspace.py`
  提供 `ImWorkspace`，用于把整条工作流串起来。
- `_base.py`
  定义 `Image2D`、`Image3D`、`MaskResult`、`LocalizationResult`、`TraceResult`、`MatrixResult` 等基础数据结构。
- `_pyhim.py`
  放置 pyHiM 对齐相关的内部实现，包括 3D mask、3D localization、spot property 计算等。


## 2. 对外接口

`uchrom.im.__init__` 暴露的核心接口可以分成三类。

数据对象：

- `Image2D`
- `Image3D`
- `MaskResult`
- `LocalizationResult`
- `TraceResult`
- `MatrixResult`
- `ImWorkspace`

处理函数：

- `project`
- `project_rounds`
- `register_global`
- `register_local`
- `segment`
- `localize`
- `filter_localizations`
- `register_localizations`
- `build_traces`
- `build_matrix`

I/O 与保存函数：

- `load_image`
- `load_rounds`
- `save_project`
- `save_registration`
- `save_localizations`
- `save_traces`
- `save_matrix`


## 3. 数据组织约定

`load_rounds()` 和 `ImWorkspace.from_manifest()` 都依赖同一种 manifest 结构。每个 round 需要包含一个 `fiducial`，并可选包含若干 `images` 通道。

最小示例：

```python
from pathlib import Path

manifest = {
    "RT26": {
        "fiducial": {"path": Path("scan_001_RT26_005_ROI_converted_decon_ch00.tif")},
        "images": {
            "barcode": {"path": Path("scan_001_RT26_005_ROI_converted_decon_ch01.tif")},
        },
        "meta": {"sample_id": "scan_001", "roi": "005"},
    },
    "DAPI": {
        "fiducial": {"path": Path("scan_001_DAPI_005_ROI_converted_decon_ch01.tif")},
        "images": {
            "dapi": {"path": Path("scan_001_DAPI_005_ROI_converted_decon_ch00.tif")},
        },
        "meta": {"sample_id": "scan_001", "roi": "005"},
    },
}
```

载入后每个 round 会被组织成：

- `fiducial`: `Image3D`
- `images`: `{role: Image3D}`
- `meta`: round 级元数据

常用的 metadata 字段包括：

- `round`
- `role`
- `roi`
- `sample_id`
- `coordinate_frame`


## 4. 推荐工作流

推荐按照下面的顺序使用本模块：

```text
raw_rounds
  -> project
  -> register_global
  -> register_local
  -> segment(mask_3d)
  -> localize(localize_3d)
  -> filter_localizations
  -> register_localizations
  -> build_traces
  -> build_matrix
```

对应的最小流程示例如下：

```python
from uchrom.im import (
    ImWorkspace,
    segment,
    localize,
    filter_localizations,
    register_localizations,
    build_traces,
    build_matrix,
)

workspace = ImWorkspace.from_manifest(manifest, meta={"sample_id": "scan_001", "roi": "005"})

workspace.project()
workspace.register_global(reference="RT26")
workspace.register_local(reference="RT26")

workspace.masks["mask_3d"] = segment(
    workspace.raw_rounds["DAPI"]["images"]["dapi"],
    method="pyhim_mask_3d",
    global_registration=workspace.global_registration,
    z_binning=2,
)

barcode_stacks = {
    round_name: round_spec["images"]["barcode"]
    for round_name, round_spec in workspace.raw_rounds.items()
    if "barcode" in round_spec["images"]
}

workspace.localizations = localize(
    barcode_stacks,
    method="pyhim_3d",
    global_registration=workspace.global_registration,
    roi="005",
    backend="stardist",
    z_binning=2,
)

filtered = filter_localizations(workspace.localizations, flux_min_3D=10.0)

registered_locs = register_localizations(
    filtered,
    global_registration=workspace.global_registration,
    local_registration=workspace.local_registration,
    tolerance_drift=(3, 1, 1),
    remove_uncorrected_localizations=True,
)

workspace.traces = build_traces(
    registered_locs,
    masks=workspace.masks["mask_3d"],
    method="KDtree",
    distance_threshold_um=1.0,
    pixel_size_xy=0.1,
    pixel_size_z=0.25,
)

workspace.matrices = build_matrix(workspace.traces)
```


## 5. `ImWorkspace` 的角色

`ImWorkspace` 是这套模块最推荐的入口，它维护了整条流程中的关键状态：

- `raw_rounds`
- `projections`
- `global_registration`
- `local_registration`
- `masks`
- `localizations`
- `traces`
- `matrices`

它适合 notebook 和交互式分析，因为每一步结果都可以保留在内存里，便于后续比对、QC 和重复运行。

`workspace.save(step, out_dir, mode=...)` 则提供了统一的结果导出入口。常见的 `step` 包括：

- `project`
- `register_global`
- `register_local`
- `mask_2d`
- `mask_3d`
- `localize_3d`
- `tracing`
- `matrix`


## 6. 3D 对齐相关语义

这一部分是当前最重要的使用约定。

### 6.1 `segment(..., method="pyhim_mask_3d")`

这个后端用于生成 3D 细胞 mask。

关键语义：

- 输入应为 raw DAPI 3D stack
- 可通过 `global_registration` 自动读取该 round 的 pyHiM-style XY shift
- 可通过 `z_binning` 在分割前做 z 重采样
- 输出 mask 的 `meta["coordinate_frame"]` 会标明结果是否位于 `global_registered`

### 6.2 `localize(..., method="pyhim_3d")`

这个后端用于生成 3D barcode localization table。

关键语义：

- 输入推荐直接给 raw barcode 3D stack
- `z_binning` 会在检测前生效
- `global_registration` 会在内部应用 global XY shift
- 如果输入本身已经处于全局配准坐标系，应传 `coordinate_frame="global_registered"`，避免重复平移
- `localize_3d` 阶段默认不做 mask assignment，所以 `CellID #` 保持 pyHiM localize 阶段的语义，通常为 `0`

### 6.3 `filter_localizations(...)`

这一步用于过滤低质量 3D 点。

当前与 pyHiM 对齐的常见用法是：

```python
filtered = filter_localizations(localizations, flux_min_3D=10.0)
```

语义上它只根据 `flux` 列筛选，不做空间配准，也不做 mask 归属。

### 6.4 `register_localizations(...)`

这一步会把 `localize_3d` 的点应用到 local block correction 上。

关键语义：

- 这里假设 global registration 已在 `localize(..., method="pyhim_3d")` 阶段完成
- 它主要应用的是 local 3D drift correction
- 如果某个点没有可用的局部配准结果，并且 `remove_uncorrected_localizations=True`，则该点会被移除

因此：

- `localize_3d` 输出是“call 点”
- `register_localizations` 输出是“经过局部校正、可进入 trace 的点”


## 7. 各阶段输入输出

### 7.1 Projection

- 输入：`Image3D` 或 3D `ndarray`
- 输出：2D 投影数组，或 `project_rounds()` 返回的 round 字典

### 7.2 Segmentation

- 输入：2D 图像或 3D stack
- 输出：`MaskResult`

`MaskResult` 主要包含：

- `labels`
- `properties`
- `method`
- `meta`
- `raw_labels`

### 7.3 Localization

- 输入：单个 stack 或 `{round_name: stack}` 字典
- 输出：`LocalizationResult`

`LocalizationResult.table` 是一个 pandas DataFrame。对 `pyhim_3d` 而言，常见列包括：

- `Buid`
- `ROI #`
- `CellID #`
- `Barcode #`
- `id`
- `zcentroid`
- `xcentroid`
- `ycentroid`
- `npix`
- `peak`
- `flux`
- `round`
- `label`

### 7.4 Traces

- 输入：经过过滤和局部校正后的 localization table
- 输出：`TraceResult`

### 7.5 Matrix

- 输入：trace table
- 输出：`MatrixResult`

矩阵结果默认包含：

- `PWDscMatrix`
- `PWDmedianMatrix`
- `Nmatrix`
- `uniqueBarcodes`


## 8. 可选方法与适用场景

### 8.1 `segment()`

支持的方法：

- `threshold`
- `stardist`
- `pyhim`
- `pyhim_mask`
- `pyhim_mask_2d`
- `pyhim_mask_3d`

建议：

- 快速调试可以用 `threshold`
- 与 pyHiM 对齐时优先用 `pyhim_mask_3d`

### 8.2 `localize()`

支持的方法：

- `pyhim_3d`
- `threshold`
- `dog`

建议：

- 需要和 pyHiM localize_3d 对齐时使用 `pyhim_3d`
- `threshold` / `dog` 更适合轻量实验和排查

### 8.3 `build_traces()`

支持的方法：

- `KDtree`
- `masking`

建议：

- 与 pyHiM trace 行为更接近的是 `KDtree`
- 基于细胞分割直接归组时可以考虑 `masking`


## 9. 与 pyHiM 对比时的推荐检查点

如果你的目标是做 U-Chrom 和 pyHiM 的阶段对齐，建议按下面几个检查点分别验证：

1. `mask_3d`
   比较 mask shape、前景重叠、label IoU、max projection overlay
2. `localize_3d`
   比较总点数、每个 barcode 点数、3D nearest-neighbor residual
3. `filter_localizations`
   比较过滤前后点数、每个 barcode 删除数、过滤后最小 `flux`
4. `register_localizations`
   比较 remove 掉的点数和校正后 residual
5. `traces` 与 `matrix`
   比较 trace rows、barcode 覆盖、PWD / Nmatrix

当前 `notebooks/im_pipeline.ipynb` 已经是这套流程的主要验收 notebook，推荐优先参考它。


## 10. 常见注意事项

### 10.1 坐标系不要混用

最常见的问题不是算法本身，而是把 raw 坐标和 global-registered 坐标混在一起。

建议：

- raw 输入交给 `global_registration` 去自动处理
- 已经平移过的输入要显式标记 `coordinate_frame="global_registered"`

### 10.2 `CellID #` 的阶段语义不同

不要把 `localize_3d` 阶段的 `CellID #` 和 trace 阶段的 `Mask_id` 混为一谈。

当前推荐理解是：

- `localize_3d`：spot detection 结果，默认不做细胞归属
- `build_traces`：根据 KDTree 或 mask 归组后，才真正进入 trace 语义

### 10.3 notebook 中的结果可能只在内存里

如果没有调用 `workspace.save(...)`，某些最新结果只存在 notebook 内存，不一定已经落盘。


## 11. 相关文件

- 模块入口：[__init__.py](/F:/project/Caolab/U-C-p/UC/U-Chrom/uchrom/im/__init__.py)
- 工作流封装：[workspace.py](/F:/project/Caolab/U-C-p/UC/U-Chrom/uchrom/im/workspace.py)
- 3D 对齐实现：[_pyhim.py](/F:/project/Caolab/U-C-p/UC/U-Chrom/uchrom/im/_pyhim.py)
- Notebook 验收流程：[im_pipeline.ipynb](/F:/project/Caolab/U-C-p/UC/U-Chrom/notebooks/im_pipeline.ipynb)

