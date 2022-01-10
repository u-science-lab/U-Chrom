import numpy as np
from vispy import scene
from vispy.color import Color


class Canvas(scene.SceneCanvas):

    def __init__(self):
        scene.SceneCanvas.__init__(self, keys=None)
        self.size = 800, 600
        self.unfreeze()
        self.info = {
            'df': None,
            'show_only_ranges': set(),
        }
        self.cache_props = {}
        self.view = self.central_widget.add_view()
        self.view.bgcolor = "#000000"
        self.view.camera = 'turntable'
        self.view.camera.distance = 50

        self.lines = []
        self.labels = []
        self.label_ori_pos = []

        # Add a 3D axis to keep us oriented
        self.axis = scene.visuals.XYZAxis(parent=self.view.scene)
        self.axis.visible = False

        self.freeze()

    def draw_model(self, **props):
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
            # calculate breaks
            first_row = sdf.iloc[0, :]
            bin_size = first_row['end'] - first_row['start']
            starts = sdf['start'].values
            diff = starts[1:] - starts[:-1]
            breaks = np.where(diff > (bin_size+10))[0] + 1
            def draw_line(p):
                if style == 'points':
                    line = scene.visuals.Markers(
                        pos=p, parent=self.view.scene, size=width,
                        face_color=Color(color), edge_width=0, spherical=True, scaling=True)
                elif style == 'tube':
                    radius = width / 2
                    line = scene.visuals.Tube(points=p, parent=self.view.scene, color=Color(color), radius=radius)
                else:
                    line = scene.visuals.Line(pos=p, parent=self.view.scene, color=Color(color), width=width)
                self.lines.append(line)
            if breaks.shape[0] <= 0:
                draw_line(pos)
            else:
                ob = 0
                for b in list(breaks) + [pos.shape[0]]:
                    s_pos = pos[ob:b]
                    draw_line(s_pos)
                    ob = b

    def set_model_props(self, key, val):
        for o in self.lines:
            setattr(o, key, val)

    def draw_label(self, df, shift_factor=0.05, color="#ff0000", font_size=400, bold=True):
        labels = []
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
            label = scene.visuals.Text(chrom, color=c, parent=self.view.scene, bold=bold)
            label.pos = tuple(label_pos)
            label.font_size = font_size
            label.set_gl_state(depth_test=True)
            labels.append(label)
        self.labels = labels

    def set_label_props(self, key, val):
        for o in self.labels:
            setattr(o, key, val)

    def remove_model(self):
        for o in self.lines:
            o.parent = None
        self.lines.clear()

    def remove_label(self):
        for o in self.labels:
            o.parent = None
        self.labels = []
        self.label_ori_pos = []
