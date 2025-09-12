import numpy as np
from PyQt5.QtWidgets import QWidget
from vispy import scene
from matplotlib import cm
from matplotlib import colors as mpl_colors
from vispy.color import Color


class Layer(object):
    LABEL = "Layer"

    def __init__(self, canvas):
        self.name = None
        self.vis_objs = []
        self.canvas = canvas
        self.control_panel = self.init_props_panel()
        self.locked = False
        self.is_visible = True

    def remove(self):
        for o in self.vis_objs:
            o.parent = None
        self.vis_objs.clear()

    def set_props(self, key, val):
        for o in self.vis_objs:
            setattr(o, key, val)

    def set_visible(self, visible: bool):
        self.is_visible = visible
        if visible:
            # Re-draw the layer when making it visible
            self.draw()
        else:
            # Remove all visual objects when hiding
            self.remove()

    def set_locked(self, locked: bool):
        self.locked = locked

    def __str__(self):
        if self.name is None:
            return f"{self.LABEL} <{id(self)}>"
        else:
            return self.name

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

    def draw(self, df, shift_factor=0.05, color="#ff0000", font_size=400, bold=True):
        labels = self.vis_objs
        for chrom in df['chrom'].unique():
            sdf = df[df['chrom'] == chrom]
            pos = sdf[['x', 'y', 'z']].values
            center = pos.mean(axis=0)
            norm = np.sqrt(sum([(pos[:, i]-center[i])**2 for i in range(3)]))
            max_norm_ix = np.argmax(norm)
            max_norm_pos = pos[max_norm_ix]
            self.label_ori_pos.append(max_norm_pos)
            label_pos = max_norm_pos * (1 + shift_factor)
            # when color is dict or a colormap, use its color for label
            if isinstance(color, dict):
                c = color.get(chrom, color.get(str(chrom).lower().replace('chr',''), "#FFFFFF"))
            else:
                c = color
            # Show numeric part only (e.g., chr1 -> 1)
            chrom_text = str(chrom).lower().replace('chr', '')
            label = scene.visuals.Text(chrom_text, color=c, parent=self.canvas.view.scene, bold=bold)
            label.pos = tuple(label_pos)
            label.font_size = font_size
            label.set_gl_state(depth_test=True)
            labels.append(label)

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
        # Initialize cache_props BEFORE control panel connects in super().__init__
        self.cache_props = {
            'color_mode': 'rainbow',      # 'rainbow' or 'single'
            'single_color': '#FFFFFF',    # used when color_mode == 'single'
            'df': df,                     # Store the actual dataframe to use for drawing
            'chr_colormap': chr_colormap, # Store the colormap
            'width': width,               # Store width
            'style': style,               # Store style
        }
        super().__init__(canvas)
        self.draw(df=df, chr_colormap=chr_colormap, width=width, style=style)

    def draw(self, **props):
        if len(props) != 0:
            self.cache_props.update(props)
        props = self.cache_props
        try:
            df, chr_colormap, width, style = props['df'], props['chr_colormap'], props['width'], props['style']
        except Exception as e:
            print(repr(e))
            return
        
        # If layer is not visible, don't draw anything
        if not self.is_visible:
            return
        color_mode = props.get('color_mode', 'rainbow')
        single_color = props.get('single_color', '#FFFFFF')
        num_chrom = int(df['chrom'].nunique())
        for chrom in chr_colormap.keys():
            sdf = df[df['chrom'] == chrom]
            if sdf.shape[0] <= 1:
                continue
            pos = sdf[['x', 'y', 'z']].values
            if color_mode == 'single':
                color = single_color
                color_rgba = mpl_colors.to_rgba(color)
                colors_rgba = np.tile(color_rgba, (pos.shape[0], 1))
                per_vertex = True
            else:
                if num_chrom > 1:
                    # multiple chromosomes -> keep original: one color per chromosome
                    color = chr_colormap.get(chrom, "#888888")
                    colors_rgba = mpl_colors.to_rgba(color)
                    per_vertex = False
                else:
                    # single chromosome -> rainbow gradient along polymer
                    t = np.linspace(0.0, 1.0, pos.shape[0])
                    cmap = cm.get_cmap('rainbow')
                    colors_rgba = cmap(t)
                    per_vertex = True
            def draw_line(p):
                if style == 'points':
                    line = scene.visuals.Markers(
                        pos=p, parent=self.canvas.view.scene, size=width,
                        face_color=colors_rgba if per_vertex else Color(colors_rgba), edge_width=0, spherical=True, scaling=True)
                elif style == 'tube':
                    radius = width / 2
                    if per_vertex:
                        # Highly optimized gradient approximation for performance
                        max_segments = int(props.get('tube_gradient_segments', 50))  # Reduced from 300
                        total_points = p.shape[0]
                        
                        if total_points <= max_segments * 2:
                            # For small datasets, use fewer segments but longer tubes
                            step = max(2, total_points // max_segments)
                            for i in range(0, total_points - step, step):
                                j = min(total_points - 1, i + step * 2)  # Longer segments
                                seg = p[i:j+1]
                                c = tuple(colors_rgba[i])
                                tube = scene.visuals.Tube(points=seg, parent=self.canvas.view.scene, 
                                                        color=c, radius=radius, tube_points=8)  # Reduce geometry complexity
                                self.vis_objs.append(tube)
                        else:
                            # For large datasets, use adaptive decimation
                            indices = np.linspace(0, total_points-1, max_segments, dtype=int)
                            for i in range(len(indices)-1):
                                start_idx = indices[i]
                                end_idx = indices[i+1]
                                seg = p[start_idx:end_idx+1]
                                if seg.shape[0] < 2:
                                    continue
                                c = tuple(colors_rgba[start_idx])
                                tube = scene.visuals.Tube(points=seg, parent=self.canvas.view.scene, 
                                                        color=c, radius=radius, tube_points=6)  # Even simpler geometry
                                self.vis_objs.append(tube)
                        return
                    else:
                        # Non-gradient tube - single object, much faster
                        line = scene.visuals.Tube(points=p, parent=self.canvas.view.scene, 
                                                color=Color(colors_rgba), radius=radius, tube_points=8)
                else:
                    line = scene.visuals.Line(pos=p, parent=self.canvas.view.scene, color=colors_rgba if per_vertex else Color(colors_rgba), width=width)
                self.vis_objs.append(line)
            if props.get('breaks', False):
                # calculate breaks
                first_row = sdf.iloc[0, :]
                starts = sdf['start'].values
                diff = starts[1:] - starts[:-1]
                bin_size = first_row['end'] - first_row['start']
                breaks = np.where(diff > (bin_size+10))[0] + 1
                if breaks.shape[0] <= 0:
                    draw_line(pos)
                else:
                    ob = 0
                    for b in list(breaks) + [pos.shape[0]]:
                        s_pos = pos[ob:b]
                        draw_line(s_pos)
                        ob = b
            else:
                draw_line(pos)

    def init_props_panel(self) -> QWidget:
        from .obj_panel import ChromatinProps
        w = ChromatinProps()
        w.connect_with(self)
        return w

    def re_render(self, parent=False):
        self.remove()
        self.draw()
        self.control_panel.update_params()
        if parent:
            if self.parent is None:
                return
            self.parent.re_render(parent=True)

