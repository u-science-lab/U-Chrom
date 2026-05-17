"""Publication-ready figure generation system."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import numpy as np


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

    # 图片尺寸（英寸）
    single_column_width: float = 3.5
    double_column_width: float = 7.0
    max_height: float = 9.0

    # 颜色方案
    colormap_sequential: str = "viridis"
    colormap_diverging: str = "RdBu_r"
    colormap_qualitative: list = field(default_factory=lambda: ["#1f77b4", "#ff7f0e", "#2ca02c"])

    # 线条和标记
    line_width: float = 1.0
    marker_size: float = 4.0

    # 间距（英寸）
    panel_spacing: float = 0.3
    margin_left: float = 0.5
    margin_right: float = 0.2
    margin_top: float = 0.3
    margin_bottom: float = 0.5

    # DPI
    dpi: int = 300

    # 其他
    show_grid: bool = False
    spine_width: float = 0.5


# 预设样式库
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


@dataclass
class Annotation:
    """注释配置"""
    type: str  # 'arrow', 'box', 'text', 'line'
    position: tuple  # 位置坐标
    text: Optional[str] = None
    style: Optional[dict] = None


@dataclass
class PanelSpec:
    """单个面板配置"""
    type: str  # 'structure_3d', 'contact_map', 'track', 'compartment', 'tad'
    data: dict  # 面板特定数据
    label: Optional[str] = None  # 面板标签 (A, B, C...)
    title: Optional[str] = None  # 子图标题
    colormap: Optional[str] = None  # 颜色映射
    show_scale: bool = True  # 是否显示 scale bar
    annotations: Optional[list[Annotation]] = None  # 额外注释


class Figure:
    """扩展 matplotlib Figure，添加导出方法"""

    def __init__(self, fig: plt.Figure, metadata: dict):
        self.fig = fig
        self.metadata = metadata

    def save(
        self,
        path: str,
        format: Optional[str] = None,
        dpi: Optional[int] = None,
        **kwargs
    ):
        """保存图片"""
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
        """转换为 base64 字符串（用于 WebSocket 传输）"""
        import io
        import base64

        buf = io.BytesIO()
        self.fig.savefig(buf, format=format, dpi=dpi, bbox_inches='tight')
        buf.seek(0)
        return base64.b64encode(buf.read()).decode('utf-8')

    def save_params(self, path: str):
        """保存生成参数为 JSON"""
        import json
        with open(path, 'w') as f:
            json.dump(self.metadata, f, indent=2)


def _create_layout(layout: str | dict, style: JournalStyle) -> GridSpec:
    """创建 matplotlib GridSpec 布局"""
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


def _calculate_figsize(
    layout: str | dict,
    style: JournalStyle,
    column_mode: str = "single"
) -> tuple[float, float]:
    """根据布局和样式自动计算图片尺寸"""
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


def _add_panel_labels(
    fig: plt.Figure,
    axes: list,
    style: JournalStyle,
    labels: Optional[list[str]] = None
):
    """在每个子图左上角添加面板标签"""
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


def _add_scale_bar(
    ax,
    length_bp: int,
    style: JournalStyle,
    position: str = "bottom_right"
):
    """添加基因组坐标 scale bar"""
    # 计算位置
    if position == "bottom_right":
        x, y = 0.85, 0.05
    elif position == "bottom_left":
        x, y = 0.15, 0.05
    elif position == "top_right":
        x, y = 0.85, 0.95
    elif position == "top_left":
        x, y = 0.15, 0.95
    else:
        x, y = 0.85, 0.05

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


def create_figure(
    chromdata,
    layout: str | dict,
    panels: list[PanelSpec],
    style: str = "default",
    dpi: Optional[int] = None,
    figsize: Optional[tuple[float, float]] = None,
    title: Optional[str] = None,
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
        面板配置列表
    style : str
        预设样式：'default', 'nature', 'cell', 'science', 'pnas'
    dpi : int | None
        分辨率（默认使用样式配置）
    figsize : tuple[float, float] | None
        图片尺寸（英寸），None 则自动计算
    title : str | None
        整体标题
    **kwargs
        额外参数

    Returns
    -------
    Figure
        包装的 matplotlib Figure 对象
    """
    # 获取样式
    style_obj = JOURNAL_STYLES.get(style, JOURNAL_STYLES["default"])
    if dpi is not None:
        style_obj.dpi = dpi

    # 应用样式到 matplotlib
    plt.rcParams['font.family'] = style_obj.font_family
    plt.rcParams['font.size'] = style_obj.font_size_label
    plt.rcParams['axes.linewidth'] = style_obj.spine_width

    # 计算尺寸
    if figsize is None:
        column_mode = kwargs.get("column_mode", "single")
        figsize = _calculate_figsize(layout, style_obj, column_mode)

    # 创建布局
    gs = _create_layout(layout, style_obj)
    fig = plt.figure(figsize=figsize, dpi=style_obj.dpi)

    # 创建子图
    axes = []
    for i, panel_spec in enumerate(panels):
        ax = fig.add_subplot(gs[i])
        axes.append(ax)

        # 渲染面板
        if panel_spec.title:
            ax.set_title(panel_spec.title, fontsize=style_obj.font_size_title)

        # 根据面板类型渲染
        if panel_spec.type == "structure_3d":
            _render_structure_3d_panel(ax, chromdata, panel_spec, style_obj)
        elif panel_spec.type == "contact_map":
            _render_contact_map_panel(ax, chromdata, panel_spec, style_obj)
        elif panel_spec.type == "track":
            _render_track_panel(ax, chromdata, panel_spec, style_obj)
        else:
            # 未实现的类型：显示占位符
            ax.text(0.5, 0.5, f"Panel {i+1}\nType: {panel_spec.type}",
                    ha='center', va='center', transform=ax.transAxes,
                    fontsize=style_obj.font_size_label)
            ax.set_xticks([])
            ax.set_yticks([])

    # 添加面板标签
    panel_labels = [p.label for p in panels if p.label]
    if panel_labels:
        _add_panel_labels(fig, axes, style_obj, panel_labels)

    # 添加整体标题
    if title:
        fig.suptitle(title, fontsize=style_obj.font_size_title + 2, fontweight='bold')

    # 保存元数据
    metadata = {
        "layout": layout,
        "style": style,
        "dpi": style_obj.dpi,
        "figsize": figsize,
        "panels": [{"type": p.type, "label": p.label, "title": p.title} for p in panels],
    }

    return Figure(fig, metadata)


def _render_structure_3d_panel(ax, chromdata, panel_spec: PanelSpec, style: JournalStyle):
    """渲染 3D 结构面板（投影到 2D）"""
    coords = chromdata.coords

    # 投影到 2D
    projection = panel_spec.data.get("projection", "xy")
    if projection == "xy":
        x, y = coords[:, 0], coords[:, 1]
    elif projection == "xz":
        x, y = coords[:, 0], coords[:, 2]
    elif projection == "yz":
        x, y = coords[:, 1], coords[:, 2]
    else:
        x, y = coords[:, 0], coords[:, 1]

    # 着色方案
    colormap = panel_spec.colormap or style.colormap_sequential
    colors = panel_spec.data.get("colors", None)

    # 绘制
    if colors is not None:
        scatter = ax.scatter(x, y, c=colors, cmap=colormap, s=style.marker_size, alpha=0.8)
        cbar = ax.figure.colorbar(scatter, ax=ax, fraction=0.046, pad=0.04)
        cbar.ax.tick_params(labelsize=style.font_size_tick)
    else:
        ax.plot(x, y, linewidth=style.line_width, color='black', alpha=0.7)
        ax.scatter(x, y, s=style.marker_size, color='black', alpha=0.5)

    # 样式
    ax.set_aspect('equal')
    ax.set_xlabel(f"{projection[0].upper()} (nm)", fontsize=style.font_size_label)
    ax.set_ylabel(f"{projection[1].upper()} (nm)", fontsize=style.font_size_label)
    ax.tick_params(labelsize=style.font_size_tick)

    if not style.show_grid:
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)


def _render_contact_map_panel(ax, chromdata, panel_spec: PanelSpec, style: JournalStyle):
    """渲染接触图面板"""
    matrix = panel_spec.data.get("matrix")
    if matrix is None:
        # 从 chromdata 计算距离矩阵（简化版）
        coords = chromdata.coords
        from scipy.spatial.distance import pdist, squareform
        distances = squareform(pdist(coords))
        # 转换为接触频率（距离越近，接触频率越高）
        matrix = 1.0 / (1.0 + distances)

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
    cbar.set_label("Contact frequency", fontsize=style.font_size_label)

    # 坐标轴
    ax.set_xlabel("Genomic position", fontsize=style.font_size_label)
    ax.set_ylabel("Genomic position", fontsize=style.font_size_label)
    ax.tick_params(labelsize=style.font_size_tick)


def _render_track_panel(ax, chromdata, panel_spec: PanelSpec, style: JournalStyle):
    """渲染基因组 track 面板"""
    track_type = panel_spec.data.get("track_type", "signal")

    if track_type == "signal":
        # 信号轨道（连续值）
        positions = panel_spec.data.get("positions", [])
        values = panel_spec.data.get("values", [])
        if len(positions) > 0 and len(values) > 0:
            ax.fill_between(positions, values, alpha=0.5, color=style.colormap_qualitative[0])
            ax.plot(positions, values, linewidth=style.line_width, color=style.colormap_qualitative[0])

    elif track_type == "regions":
        # 区域轨道（TAD, compartment）
        regions = panel_spec.data.get("regions", [])
        for i, region in enumerate(regions):
            if len(region) >= 2:
                start, end = region[0], region[1]
                label = region[2] if len(region) > 2 else f"Region {i+1}"
                color = style.colormap_qualitative[i % len(style.colormap_qualitative)]
                ax.axvspan(start, end, alpha=0.3, color=color, label=label)

        if len(regions) > 0:
            ax.legend(fontsize=style.font_size_legend, loc='upper right')

    # 坐标轴
    ax.set_xlabel("Genomic position (bp)", fontsize=style.font_size_label)
    ylabel = panel_spec.data.get("ylabel", "Signal")
    ax.set_ylabel(ylabel, fontsize=style.font_size_label)
    ax.tick_params(labelsize=style.font_size_tick)

    # Scale bar
    if panel_spec.show_scale:
        chrom_length = panel_spec.data.get("chrom_length", 1_000_000)
        _add_scale_bar(ax, chrom_length // 10, style)

