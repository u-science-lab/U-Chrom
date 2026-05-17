# uchrom.pl 智能出图模块设计

**日期**: 2026-05-18  
**目标**: 设计 publication-ready 图表生成系统

---

## 一、核心 API 设计

### 1.1 主函数签名

```python
def create_figure(
    chromdata: ChromData,
    layout: str | dict,
    panels: list[PanelSpec],
    style: str = "default",
    dpi: int = 300,
    figsize: tuple[float, float] | None = None,
    title: str | None = None,
    **kwargs
) -> Figure:
    """
    创建多面板科学图表。
    
    Parameters
    ----------
    chromdata : ChromData
        数据源
    layout : str | dict
        布局方式：
        - "1x1", "2x1", "1x2", "2x2", "3x1" 等字符串
        - 或自定义 GridSpec 配置字典
    panels : list[PanelSpec]
        面板配置列表，每个元素指定一个子图
    style : str
        预设样式：'default', 'nature', 'cell', 'science', 'pnas'
    dpi : int
        分辨率（默认 300 适合印刷）
    figsize : tuple[float, float] | None
        图片尺寸（英寸），None 则根据布局自动计算
    title : str | None
        整体标题
    **kwargs
        额外参数传递给样式系统
        
    Returns
    -------
    Figure
        matplotlib Figure 对象，可调用 .save() 导出
    """
```

### 1.2 PanelSpec 数据结构

```python
@dataclass
class PanelSpec:
    """单个面板配置"""
    type: str  # 'structure_3d', 'contact_map', 'track', 'compartment', 'tad'
    data: dict  # 面板特定数据
    label: str | None = None  # 面板标签 (A, B, C...)
    title: str | None = None  # 子图标题
    colormap: str | None = None  # 颜色映射
    show_scale: bool = True  # 是否显示 scale bar
    annotations: list[Annotation] | None = None  # 额外注释
    
@dataclass
class Annotation:
    """注释配置"""
    type: str  # 'arrow', 'box', 'text', 'line'
    position: tuple  # 位置坐标
    text: str | None = None
    style: dict | None = None  # 样式参数
```

---

## 二、预设样式系统

### 2.1 样式配置结构

```python
@dataclass
class JournalStyle:
    """期刊样式配置"""
    name: str
    
    # 字体设置
    font_family: str = "Arial"
    font_size_title: int = 12
    font_size_label: int = 10
    font_size_tick: int = 8
    font_size_legend: int = 8
    
    # 图片尺寸
    single_column_width: float = 3.5  # 英寸
    double_column_width: float = 7.0
    max_height: float = 9.0
    
    # 颜色方案
    colormap_sequential: str = "viridis"
    colormap_diverging: str = "RdBu_r"
    colormap_qualitative: list[str] = field(default_factory=lambda: ["#1f77b4", "#ff7f0e", "#2ca02c"])
    
    # 线条和标记
    line_width: float = 1.0
    marker_size: float = 4.0
    
    # 间距
    panel_spacing: float = 0.3  # 面板间距（英寸）
    margin_left: float = 0.5
    margin_right: float = 0.2
    margin_top: float = 0.3
    margin_bottom: float = 0.5
    
    # DPI
    dpi: int = 300
    
    # 其他
    show_grid: bool = False
    spine_width: float = 0.5
```

### 2.2 预设样式库

```python
JOURNAL_STYLES = {
    "nature": JournalStyle(
        name="Nature",
        font_family="Helvetica",
        font_size_title=8,
        font_size_label=7,
        font_size_tick=6,
        single_column_width=89/25.4,  # 89mm → 英寸
        double_column_width=183/25.4,  # 183mm
        colormap_sequential="viridis",
        dpi=300,
    ),
    
    "cell": JournalStyle(
        name="Cell",
        font_family="Arial",
        font_size_title=9,
        font_size_label=8,
        font_size_tick=7,
        single_column_width=3.35,
        double_column_width=6.85,
        colormap_sequential="plasma",
        dpi=300,
    ),
    
    "science": JournalStyle(
        name="Science",
        font_family="Arial",
        font_size_title=8,
        font_size_label=7,
        font_size_tick=6,
        single_column_width=3.35,
        double_column_width=7.0,
        colormap_sequential="cividis",
        dpi=300,
    ),
    
    "pnas": JournalStyle(
        name="PNAS",
        font_family="Arial",
        font_size_title=9,
        font_size_label=8,
        font_size_tick=7,
        single_column_width=3.42,
        double_column_width=7.0,
        colormap_sequential="viridis",
        dpi=300,
    ),
    
    "default": JournalStyle(
        name="Default",
        font_family="Arial",
        font_size_title=12,
        font_size_label=10,
        font_size_tick=8,
        single_column_width=4.0,
        double_column_width=8.0,
        dpi=150,  # 屏幕预览用低 DPI
    ),
}
```

---

## 三、布局引擎

### 3.1 GridSpec 布局

```python
def _create_layout(layout: str | dict, style: JournalStyle) -> GridSpec:
    """
    创建 matplotlib GridSpec 布局。
    
    Parameters
    ----------
    layout : str | dict
        - 字符串: "2x1" → 2 行 1 列
        - 字典: {"nrows": 2, "ncols": 2, "width_ratios": [1, 2], ...}
    style : JournalStyle
        样式配置，用于计算间距
        
    Returns
    -------
    GridSpec
        matplotlib GridSpec 对象
    """
    if isinstance(layout, str):
        # 解析 "2x1" 格式
        nrows, ncols = map(int, layout.split('x'))
        gs = GridSpec(
            nrows, ncols,
            hspace=style.panel_spacing / style.max_height,
            wspace=style.panel_spacing / style.double_column_width,
        )
    else:
        # 自定义配置
        gs = GridSpec(**layout)
    
    return gs
```

### 3.2 自动尺寸计算

```python
def _calculate_figsize(
    layout: str | dict,
    style: JournalStyle,
    column_mode: str = "single"
) -> tuple[float, float]:
    """
    根据布局和样式自动计算图片尺寸。
    
    Parameters
    ----------
    layout : str | dict
        布局配置
    style : JournalStyle
        样式配置
    column_mode : str
        'single' 或 'double'
        
    Returns
    -------
    tuple[float, float]
        (width, height) 英寸
    """
    if isinstance(layout, str):
        nrows, ncols = map(int, layout.split('x'))
    else:
        nrows = layout.get("nrows", 1)
        ncols = layout.get("ncols", 1)
    
    # 宽度
    if column_mode == "single":
        width = style.single_column_width
    else:
        width = style.double_column_width
    
    # 高度：根据行数和面板间距
    panel_height = width / ncols  # 假设正方形面板
    height = nrows * panel_height + (nrows - 1) * style.panel_spacing
    height = min(height, style.max_height)  # 限制最大高度
    
    return (width, height)
```

---

## 四、自动注释系统

### 4.1 Panel Labels (A, B, C...)

```python
def _add_panel_labels(
    fig: Figure,
    axes: list[Axes],
    style: JournalStyle,
    labels: list[str] | None = None
):
    """
    在每个子图左上角添加面板标签。
    
    Parameters
    ----------
    fig : Figure
        matplotlib Figure
    axes : list[Axes]
        子图列表
    style : JournalStyle
        样式配置
    labels : list[str] | None
        自定义标签，None 则自动生成 A, B, C...
    """
    if labels is None:
        labels = [chr(65 + i) for i in range(len(axes))]  # A, B, C...
    
    for ax, label in zip(axes, labels):
        ax.text(
            -0.1, 1.05,  # 相对坐标
            label,
            transform=ax.transAxes,
            fontsize=style.font_size_label + 2,
            fontweight='bold',
            va='bottom',
            ha='right'
        )
```

### 4.2 Scale Bar

```python
def _add_scale_bar(
    ax: Axes,
    length_bp: int,
    style: JournalStyle,
    position: str = "bottom_right"
):
    """
    添加基因组坐标 scale bar。
    
    Parameters
    ----------
    ax : Axes
        目标子图
    length_bp : int
        scale bar 长度（碱基对）
    style : JournalStyle
        样式配置
    position : str
        位置：'bottom_right', 'bottom_left', 'top_right', 'top_left'
    """
    # 计算位置
    if position == "bottom_right":
        x, y = 0.85, 0.05
    elif position == "bottom_left":
        x, y = 0.15, 0.05
    # ... 其他位置
    
    # 格式化长度
    if length_bp >= 1_000_000:
        label = f"{length_bp / 1_000_000:.1f} Mb"
    elif length_bp >= 1_000:
        label = f"{length_bp / 1_000:.0f} kb"
    else:
        label = f"{length_bp} bp"
    
    # 绘制
    ax.plot(
        [x, x + 0.1], [y, y],
        transform=ax.transAxes,
        color='black',
        linewidth=style.line_width * 2,
        solid_capstyle='butt'
    )
    ax.text(
        x + 0.05, y + 0.02,
        label,
        transform=ax.transAxes,
        fontsize=style.font_size_tick,
        ha='center',
        va='bottom'
    )
```

### 4.3 Statistical Annotations

```python
def _add_statistical_annotation(
    ax: Axes,
    x1: float, x2: float, y: float,
    pvalue: float,
    style: JournalStyle
):
    """
    添加统计显著性标注（*, **, ***, ns）。
    
    Parameters
    ----------
    ax : Axes
        目标子图
    x1, x2 : float
        比较的两个 x 坐标
    y : float
        标注的 y 坐标
    pvalue : float
        p 值
    style : JournalStyle
        样式配置
    """
    # 确定显著性符号
    if pvalue < 0.001:
        symbol = "***"
    elif pvalue < 0.01:
        symbol = "**"
    elif pvalue < 0.05:
        symbol = "*"
    else:
        symbol = "ns"
    
    # 绘制横线
    ax.plot([x1, x2], [y, y], color='black', linewidth=style.line_width)
    
    # 添加文本
    ax.text(
        (x1 + x2) / 2, y,
        symbol,
        fontsize=style.font_size_label,
        ha='center',
        va='bottom'
    )
```

---

## 五、面板类型实现

### 5.1 Structure 3D Panel

```python
def _render_structure_3d_panel(
    ax: Axes,
    chromdata: ChromData,
    panel_spec: PanelSpec,
    style: JournalStyle
):
    """
    渲染 3D 结构面板（投影到 2D）。
    
    Parameters
    ----------
    ax : Axes
        目标子图
    chromdata : ChromData
        数据源
    panel_spec : PanelSpec
        面板配置
    style : JournalStyle
        样式配置
    """
    # 提取坐标
    coords = chromdata.coords
    
    # 投影到 2D（默认 XY 平面）
    projection = panel_spec.data.get("projection", "xy")
    if projection == "xy":
        x, y = coords[:, 0], coords[:, 1]
    elif projection == "xz":
        x, y = coords[:, 0], coords[:, 2]
    elif projection == "yz":
        x, y = coords[:, 1], coords[:, 2]
    
    # 着色方案
    colormap = panel_spec.colormap or style.colormap_sequential
    colors = panel_spec.data.get("colors", None)
    
    # 绘制
    if colors is not None:
        ax.scatter(x, y, c=colors, cmap=colormap, s=style.marker_size, alpha=0.8)
    else:
        ax.plot(x, y, linewidth=style.line_width, color='black')
    
    # 样式
    ax.set_aspect('equal')
    ax.axis('off')  # 3D 结构通常不显示坐标轴
```

### 5.2 Contact Map Panel

```python
def _render_contact_map_panel(
    ax: Axes,
    chromdata: ChromData,
    panel_spec: PanelSpec,
    style: JournalStyle
):
    """
    渲染接触图面板。
    
    Parameters
    ----------
    ax : Axes
        目标子图
    chromdata : ChromData
        数据源
    panel_spec : PanelSpec
        面板配置
    style : JournalStyle
        样式配置
    """
    # 计算接触矩阵
    matrix = panel_spec.data.get("matrix")
    if matrix is None:
        # 从 chromdata 计算
        from uchrom.op import compute_contact_matrix
        matrix = compute_contact_matrix(chromdata)
    
    # 绘制热图
    colormap = panel_spec.colormap or style.colormap_sequential
    im = ax.imshow(
        matrix,
        cmap=colormap,
        aspect='equal',
        origin='lower',
        interpolation='nearest'
    )
    
    # 添加 colorbar
    cbar = ax.figure.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.ax.tick_params(labelsize=style.font_size_tick)
    
    # 坐标轴
    ax.set_xlabel("Genomic position", fontsize=style.font_size_label)
    ax.set_ylabel("Genomic position", fontsize=style.font_size_label)
    ax.tick_params(labelsize=style.font_size_tick)
```

### 5.3 Track Panel

```python
def _render_track_panel(
    ax: Axes,
    chromdata: ChromData,
    panel_spec: PanelSpec,
    style: JournalStyle
):
    """
    渲染基因组 track 面板（TAD, compartment, etc.）。
    
    Parameters
    ----------
    ax : Axes
        目标子图
    chromdata : ChromData
        数据源
    panel_spec : PanelSpec
        面板配置
    style : JournalStyle
        样式配置
    """
    track_type = panel_spec.data.get("track_type", "signal")
    
    if track_type == "signal":
        # 信号轨道（连续值）
        positions = panel_spec.data["positions"]
        values = panel_spec.data["values"]
        ax.fill_between(positions, values, alpha=0.5, color=style.colormap_qualitative[0])
        ax.plot(positions, values, linewidth=style.line_width, color=style.colormap_qualitative[0])
        
    elif track_type == "regions":
        # 区域轨道（TAD, compartment）
        regions = panel_spec.data["regions"]
        for i, (start, end, label) in enumerate(regions):
            color = style.colormap_qualitative[i % len(style.colormap_qualitative)]
            ax.axvspan(start, end, alpha=0.3, color=color, label=label)
    
    # 坐标轴
    ax.set_xlabel("Genomic position (bp)", fontsize=style.font_size_label)
    ax.set_ylabel(panel_spec.data.get("ylabel", "Signal"), fontsize=style.font_size_label)
    ax.tick_params(labelsize=style.font_size_tick)
    
    # Scale bar
    if panel_spec.show_scale:
        chrom_length = panel_spec.data.get("chrom_length", 1_000_000)
        _add_scale_bar(ax, chrom_length // 10, style)
```

---

## 六、导出系统

### 6.1 Figure 类扩展

```python
class Figure:
    """扩展 matplotlib Figure，添加导出方法"""
    
    def __init__(self, fig: plt.Figure, metadata: dict):
        self.fig = fig
        self.metadata = metadata  # 保存生成参数
    
    def save(
        self,
        path: str,
        format: str | None = None,
        dpi: int | None = None,
        **kwargs
    ):
        """
        保存图片。
        
        Parameters
        ----------
        path : str
            输出路径
        format : str | None
            格式：'pdf', 'png', 'svg'，None 则从路径推断
        dpi : int | None
            分辨率，None 则使用样式默认值
        **kwargs
            传递给 fig.savefig()
        """
        if format is None:
            format = path.split('.')[-1]
        
        if dpi is None:
            dpi = self.metadata.get("dpi", 300)
        
        self.fig.savefig(
            path,
            format=format,
            dpi=dpi,
            bbox_inches='tight',
            **kwargs
        )
    
    def to_base64(self, format: str = "png", dpi: int = 150) -> str:
        """
        转换为 base64 字符串（用于 WebSocket 传输）。
        
        Parameters
        ----------
        format : str
            图片格式
        dpi : int
            分辨率（预览用低 DPI）
            
        Returns
        -------
        str
            base64 编码的图片数据
        """
        import io
        import base64
        
        buf = io.BytesIO()
        self.fig.savefig(buf, format=format, dpi=dpi, bbox_inches='tight')
        buf.seek(0)
        return base64.b64encode(buf.read()).decode('utf-8')
    
    def save_params(self, path: str):
        """
        保存生成参数为 JSON（用于重现）。
        
        Parameters
        ----------
        path : str
            输出路径（.json）
        """
        import json
        with open(path, 'w') as f:
            json.dump(self.metadata, f, indent=2)
```

---

## 七、使用示例

### 7.1 基础用法

```python
import uchrom
from uchrom.pl import create_figure, PanelSpec

# 加载数据
cd = uchrom.ChromData.read("data.h5cd")

# 定义面板
panels = [
    PanelSpec(
        type="structure_3d",
        data={"projection": "xy", "colors": cd.cellm["compartment"]},
        label="A",
        title="3D Structure (XY projection)",
        colormap="RdBu_r",
    ),
    PanelSpec(
        type="contact_map",
        data={"matrix": None},  # 自动计算
        label="B",
        title="Contact Map",
    ),
]

# 生成图表
fig = create_figure(
    chromdata=cd,
    layout="1x2",
    panels=panels,
    style="nature",
    dpi=300,
)

# 保存
fig.save("figure1.pdf")
fig.save("figure1.png", dpi=150)  # 低分辨率预览
fig.save_params("figure1_params.json")  # 保存参数
```

### 7.2 Agent 调用示例

```python
# Agent 生成的代码
cd = chromdata  # 已加载

# 用户: "生成 Figure 2: 三个细胞的 A/B compartment 对比，适合 Nature 投稿"
cells = ["cell_001", "cell_002", "cell_003"]
panels = []

for i, cell_id in enumerate(cells):
    cd_cell = cd.get_cell(cell_id)
    comp = uchrom.strc.comp.detect_compartments(cd_cell)
    
    panels.append(PanelSpec(
        type="track",
        data={
            "track_type": "regions",
            "regions": [(r.start, r.end, r.type) for _, r in comp.iterrows()],
            "ylabel": "Compartment",
        },
        label=chr(65 + i),  # A, B, C
        title=f"Cell {cell_id}",
    ))

fig = uchrom.pl.create_figure(
    chromdata=cd,
    layout="3x1",
    panels=panels,
    style="nature",
    dpi=300,
)

# 导出并发送给前端
fig.save("/tmp/figure2.pdf")
preview_base64 = fig.to_base64(dpi=150)
emit_artifact("figure", {
    "path": "/tmp/figure2.pdf",
    "preview": preview_base64,
    "format": "pdf",
    "params": fig.metadata
})
```

---

## 八、实现优先级

### Phase 2.1 (本周)
1. ✅ 实现 `create_figure()` 核心函数
2. ✅ 实现预设样式系统 (Nature, Cell, Science)
3. ✅ 实现布局引擎 (GridSpec)
4. ✅ 实现自动注释 (panel labels, scale bar)

### Phase 2.2 (下周)
5. ✅ 实现 3 种面板类型 (structure_3d, contact_map, track)
6. ✅ 实现 Figure 类和导出系统
7. ✅ Agent 集成和 prompt 模板

### Phase 2.3 (测试)
8. ✅ 单元测试
9. ✅ E2E 测试
10. ✅ 文档和示例

---

## 九、技术决策

### 9.1 为什么使用 matplotlib 而非 plotly？

**原因**:
- matplotlib 是科学出版的事实标准
- 支持矢量格式 (PDF, SVG)
- 样式控制更精细（字体、线宽、间距）
- plotly 更适合交互式可视化，不适合静态出版图

### 9.2 为什么不直接生成 SVG？

**原因**:
- PDF 是期刊投稿的标准格式
- matplotlib 的 PDF 后端质量更高
- SVG 作为可选格式提供（用户可编辑）

### 9.3 为什么需要 Figure 类包装？

**原因**:
- 保存生成参数（metadata），支持重现
- 提供 `to_base64()` 方法，方便 WebSocket 传输
- 统一导出接口，简化 Agent 调用

---

**设计完成！准备实现。**
