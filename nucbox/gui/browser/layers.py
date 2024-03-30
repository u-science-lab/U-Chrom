import numpy as np
from PyQt5.QtWidgets import QWidget
from vispy import scene
from vispy.color import Color


class Layer(object):
    LABEL = "Layer"

    def __init__(self, canvas):
        self.name = None
        self.vis_objs = []
        self.canvas = canvas
        self.control_panel = self.init_props_panel()

    def remove(self):
        for o in self.vis_objs:
            o.parent = None
        self.vis_objs.clear()

    def set_props(self, key, val):
        for o in self.vis_objs:
            setattr(o, key, val)

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
            if isinstance(color, dict):
                c = color.get(chrom, "#ff0000")
            else:
                c = color
            label = scene.visuals.Text(chrom, color=c, parent=self.canvas.view.scene, bold=bold)
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
        super().__init__(canvas)
        self.cache_props = {}
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
        for chrom in chr_colormap.keys():
            sdf = df[df['chrom'] == chrom]
            if sdf.shape[0] <= 1:
                continue
            pos = sdf[['x', 'y', 'z']].values
            color = chr_colormap.get(chrom, "#888888")
            def draw_line(p):
                if style == 'points':
                    line = scene.visuals.Markers(
                        pos=p, parent=self.canvas.view.scene, size=width,
                        face_color=Color(color), edge_width=0, spherical=True, scaling=True)
                elif style == 'tube':
                    radius = width / 2
                    line = scene.visuals.Tube(points=p, parent=self.canvas.view.scene, color=Color(color), radius=radius)
                else:
                    line = scene.visuals.Line(pos=p, parent=self.canvas.view.scene, color=Color(color), width=width)
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

