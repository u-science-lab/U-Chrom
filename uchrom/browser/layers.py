"""
Layer implementations built directly on the PyVista backend.
This file provides the concrete (non-abstract) layers used by the UI.
"""

import numpy as np
from PyQt5.QtWidgets import QWidget
from matplotlib import cm
from matplotlib import colors as mpl_colors


class Layer(object):
    """Base layer class for PyVista-backed rendering."""
    LABEL = "Layer"

    def __init__(self, canvas):
        self.name = None
        self.vis_handles = []  # Backend handles for created objects
        self.vis_objs = []  # Compatibility wrappers (minimal API)
        self.canvas = canvas
        self.control_panel = self.init_props_panel()
        self.locked = False
        self.is_visible = True
    
    def _create_vis_obj_wrapper(self, handle):
        """Create a wrapper for compatibility with legacy vis_objs usage."""
        class VisObjWrapper:
            def __init__(self, handle, layer):
                self.handle = handle
                self.layer = layer
            def set_data(self, **kwargs):
                pass
            @property
            def opacity(self):
                return 1.0
            @opacity.setter
            def opacity(self, value):
                # Prefer backend-side opacity updates via set_props('opacity', ...)
                pass
        return VisObjWrapper(handle, self)

    def remove(self):
        """Remove all visuals for this layer from the scene."""
        for handle in list(self.vis_handles):
            try:
                self.canvas.backend.remove_object(handle)
            except Exception:
                pass
        self.vis_handles.clear()
        self.vis_objs.clear()
        if hasattr(self.canvas.backend, 'render'):
            self.canvas.backend.render()

    def set_props(self, key, val):
        """Set properties on visuals; uses backend ops when available."""
        if key == 'opacity' and hasattr(self.canvas.backend, 'set_object_opacity'):
            for handle in self.vis_handles:
                try:
                    self.canvas.backend.set_object_opacity(handle, float(val))
                except Exception:
                    continue
            return
        try:
            self.draw()
        except Exception:
            pass

    def set_visible(self, visible: bool):
        self.is_visible = visible
        if visible:
            self.draw()
        else:
            self.remove()
        if hasattr(self.canvas.backend, 'render'):
            self.canvas.backend.render()

    def set_locked(self, locked: bool):
        self.locked = locked

    def __str__(self):
        return self.name if self.name is not None else f"{self.LABEL} <{id(self)}>"

    def __repr__(self):
        return str(self)

    def init_props_panel(self) -> QWidget:
        from .obj_panel import LayerPropsPanel
        w = LayerPropsPanel()
        w.connect_with(self)
        return w


class ChrLabelLayer(Layer):
    LABEL = "ChrLabel"

    def __init__(self, canvas):
        super().__init__(canvas)
        self.labels = []
        self.label_ori_pos = []

    def draw(self, df, shift_factor=0.05, color="#CD18FC", font_size=150, bold=True):
        # Clear any existing labels
        self.remove()
        for chrom in df['chrom'].unique():
            sdf = df[df['chrom'] == chrom]
            pos = sdf[['x', 'y', 'z']].values
            center = pos.mean(axis=0)
            norm = np.sqrt(sum([(pos[:, i]-center[i])**2 for i in range(3)]))
            max_norm_ix = np.argmax(norm)
            max_norm_pos = pos[max_norm_ix]
            self.label_ori_pos.append(max_norm_pos)
            label_pos = max_norm_pos * (1 + shift_factor)
            # Determine label color
            if isinstance(color, dict):
                c = color.get(chrom, color.get(str(chrom).lower().replace('chr',''), "#FFFFFF"))
            else:
                c = color
            chrom_text = str(chrom).lower().replace('chr', '')
            handle = self.canvas.backend.add_text(
                chrom_text,
                tuple(label_pos),
                color=c,
                font_size=font_size,
                bold=bold
            )
            self.vis_handles.append(handle)

    def init_props_panel(self) -> QWidget:
        from .obj_panel import ChrLabelProps
        w = ChrLabelProps()
        w.connect_with(self)
        return w


class ChromatinLayer(Layer):
    LABEL = "Chromatin"

    def __init__(self, canvas, df, chr_colormap, width=1.0, style='line'):
        self.parent = None
        self.df = df
        self.cache_props = {
            'color_mode': 'rainbow',
            'single_color': '#FFFFFF',
            'df': df,
            'chr_colormap': chr_colormap,
            'width': width,
            'style': style,
        }
        super().__init__(canvas)
        self.draw(df=df, chr_colormap=chr_colormap, width=width, style=style)

    def draw(self, **props):
        if len(props) != 0:
            self.cache_props.update(props)
        props = self.cache_props
        try:
            df = props['df']
            chr_colormap = props['chr_colormap']
            width = props['width']
            style = props['style']
        except Exception:
            return
        # Clear existing visuals
        self.remove()
        if not self.is_visible:
            return
        color_mode = props.get('color_mode', 'rainbow')
        single_color = props.get('single_color', '#FFFFFF')
        opacity = float(props.get('opacity', 1.0))
        num_chrom = int(df['chrom'].nunique())
        for chrom in df['chrom'].unique():
            sdf = df[df['chrom'] == chrom]
            if sdf.shape[0] <= 1:
                continue
            pos = sdf[['x', 'y', 'z']].values
            if color_mode == 'single':
                color = single_color
                colors_rgba = mpl_colors.to_rgba(color)
            else:
                if num_chrom > 1:
                    color = chr_colormap.get(chrom, "#888888")
                    colors_rgba = mpl_colors.to_rgba(color)
                else:
                    t = np.linspace(0.0, 1.0, pos.shape[0])
                    cmap = cm.get_cmap('rainbow')
                    colors_rgba = cmap(t)
            if style == 'points':
                handle = self.canvas.backend.add_points(
                    pos,
                    color=colors_rgba,
                    size=width,
                    opacity=opacity
                )
                if handle is not None:
                    self.vis_handles.append(handle)
                    self.vis_objs.append(self._create_vis_obj_wrapper(handle))
            elif style == 'tube':
                high_quality = props.get('high_quality', False)
                if isinstance(colors_rgba, np.ndarray) and colors_rgba.ndim == 2:
                    self._draw_gradient_tube(pos, colors_rgba, width/2, props)
                else:
                    handle = self.canvas.backend.add_tube(
                        pos,
                        color=colors_rgba,
                        radius=width/2,
                        opacity=opacity,
                        high_quality=high_quality
                    )
                    if handle is not None:
                        self.vis_handles.append(handle)
                        self.vis_objs.append(self._create_vis_obj_wrapper(handle))
            else:  # line
                handle = self.canvas.backend.add_line(
                    pos,
                    color=colors_rgba,
                    width=width,
                    opacity=opacity
                )
                if handle is not None:
                    self.vis_handles.append(handle)
                    self.vis_objs.append(self._create_vis_obj_wrapper(handle))
            if props.get('breaks', False):
                self._handle_breaks(sdf, pos, colors_rgba, width, style)

    def _draw_gradient_tube(self, pos, colors_rgba, radius, props):
        max_segments = int(props.get('tube_gradient_segments', 50))
        high_quality = props.get('high_quality', False)
        total_points = pos.shape[0]
        if total_points <= max_segments * 2:
            step = max(2, total_points // max_segments)
            for i in range(0, total_points - step, step):
                j = min(total_points - 1, i + step * 2)
                seg = pos[i:j+1]
                if seg.shape[0] >= 2:
                    c = tuple(colors_rgba[i])
                    handle = self.canvas.backend.add_tube(
                        seg,
                        color=c,
                        radius=radius,
                        opacity=float(props.get('opacity', 1.0)),
                        high_quality=high_quality
                    )
                    if handle is not None:
                        self.vis_handles.append(handle)
                        self.vis_objs.append(self._create_vis_obj_wrapper(handle))
        else:
            indices = np.linspace(0, total_points-1, max_segments, dtype=int)
            for i in range(len(indices)-1):
                start_idx = indices[i]
                end_idx = indices[i+1]
                seg = pos[start_idx:end_idx+1]
                if seg.shape[0] >= 2:
                    c = tuple(colors_rgba[start_idx])
                    handle = self.canvas.backend.add_tube(
                        seg,
                        color=c,
                        radius=radius,
                        opacity=float(props.get('opacity', 1.0)),
                        high_quality=high_quality
                    )
                    if handle is not None:
                        self.vis_handles.append(handle)
                        self.vis_objs.append(self._create_vis_obj_wrapper(handle))

    def _handle_breaks(self, sdf, pos, colors_rgba, width, style):
        first_row = sdf.iloc[0, :]
        starts = sdf['start'].values
        diff = starts[1:] - starts[:-1]
        bin_size = first_row['end'] - first_row['start']
        median_gap = np.median(diff)
        gap_thresh = median_gap * 2
        breaks_ix = np.where(diff > gap_thresh)[0]
        if len(breaks_ix) > 0:
            for handle in self.vis_handles:
                self.canvas.backend.remove_object(handle)
            self.vis_handles.clear()
            breaks_ix = np.concatenate([[0], breaks_ix + 1, [len(pos)]])
            for i in range(len(breaks_ix) - 1):
                start = breaks_ix[i]
                end = breaks_ix[i + 1]
                seg_pos = pos[start:end]
                if seg_pos.shape[0] < 2:
                    continue
                if isinstance(colors_rgba, np.ndarray) and colors_rgba.ndim == 2:
                    seg_color = colors_rgba[start:end]
                else:
                    seg_color = colors_rgba
                if style == 'points':
                    handle = self.canvas.backend.add_points(seg_pos, color=seg_color, size=width)
                elif style == 'tube':
                    if isinstance(seg_color, np.ndarray) and seg_color.ndim == 2:
                        for j in range(seg_pos.shape[0] - 1):
                            sub_seg = seg_pos[j:j+2]
                            c = tuple(seg_color[j])
                            handle = self.canvas.backend.add_tube(sub_seg, color=c, radius=width/2)
                            if handle is not None:
                                self.vis_handles.append(handle)
                        continue
                    else:
                        handle = self.canvas.backend.add_tube(seg_pos, color=seg_color, radius=width/2)
                else:
                    handle = self.canvas.backend.add_line(seg_pos, color=seg_color, width=width)
                if handle is not None:
                    self.vis_handles.append(handle)

    def init_props_panel(self) -> QWidget:
        from .obj_panel import ChromatinProps
        w = ChromatinProps()
        w.connect_with(self)
        return w
    
    def re_render(self, parent=False):
        self.remove()
        self.draw()
        if hasattr(self.control_panel, 'update_params'):
            self.control_panel.update_params()
        if parent and self.parent is not None and hasattr(self.parent, 're_render'):
            self.parent.re_render(parent=True)


__all__ = [
    'Layer',
    'ChrLabelLayer',
    'ChromatinLayer',
]