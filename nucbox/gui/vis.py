import random
import itertools
import os.path as osp
from copy import copy

from PyQt5 import QtGui
import pandas as pd
import numpy as np
from vispy import scene, app
from vispy.color import Color
import fire

import PyQt5
from PyQt5 import QtCore
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QAction, QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLineEdit, QMainWindow, QMenu, QMenuBar, QPushButton, QSpinBox, QTextBrowser, QWidget, QLabel, 
                             QGridLayout, QVBoxLayout, QCheckBox,
                             QSplitter)

from ..io import read_particles


HERE = osp.dirname(osp.abspath(__file__))

# Provide automatic signal function selection for PyQtX/PySide2
pyqtsignal = QtCore.pyqtSignal if hasattr(QtCore, 'pyqtSignal') else QtCore.Signal


def random_color():
    return "#"+''.join([random.choice('0123456789ABCDEF') for j in range(6)])


class ObjPropPanel(QWidget):
    signal_show_model = pyqtsignal(name='show_model')
    signal_show_axis = pyqtsignal(name='show_axis')
    signal_width = pyqtsignal(name='width')
    signal_opacity = pyqtsignal(name='opacity')
    signal_show_label = pyqtsignal(name='show_label')
    signal_label_font_size = pyqtsignal(name="label_font_size")
    signal_label_shift = pyqtsignal(name="label_shift")
    signal_show_only = pyqtsignal(name="show_only")
    signal_change_style = pyqtsignal(name="change_style")

    def __init__(self, parent=None):
        super(ObjPropPanel, self).__init__(parent)

        l_show_axis = QLabel("Show axis")
        self.show_axis_ckbox = QCheckBox()
        self.show_axis_ckbox.toggled.connect(self.signal_show_axis)

        l_show_model = QLabel("Show model")
        self.show_model_ckbox = QCheckBox()
        self.show_model_ckbox.setChecked(True)
        self.show_model_ckbox.toggled.connect(self.signal_show_model)

        l_style = QLabel("Model style")
        self.model_style_select = QComboBox()
        self.model_style_select.addItem("line")
        self.model_style_select.addItem("points")
        self.model_style_select.addItem("tube")
        self.model_style_select.currentIndexChanged.connect(self.signal_change_style)

        l_width = QLabel("Width/Radius")
        self.width_control = QDoubleSpinBox()
        self.width_control.setMaximum(10.0)
        self.width_control.setMinimum(0.0)
        self.width_control.setSingleStep(0.2)
        self.width_control.setValue(1.0)
        self.width_control.valueChanged.connect(self.signal_width)
        
        l_opacity = QLabel("Opacity")
        self.opacity_control = QDoubleSpinBox()
        self.opacity_control.setMaximum(1.0)
        self.opacity_control.setMinimum(0.0)
        self.opacity_control.setSingleStep(0.05)
        self.opacity_control.setValue(1.0)
        self.opacity_control.valueChanged.connect(self.signal_opacity)
 
        l_show_label = QLabel("Show label")
        self.show_label_ckbox = QCheckBox()
        self.show_label_ckbox.toggled.connect(self.signal_show_label)

        l_label_size = QLabel("Label size")
        self.label_size_control = QSpinBox()
        self.label_size_control.setMaximum(10000)
        self.label_size_control.setMinimum(1)
        self.label_size_control.setSingleStep(100)
        self.label_size_control.setValue(1000)
        self.label_size_control.valueChanged.connect(self.signal_label_font_size)

        l_label_shift = QLabel("Label shift")
        self.label_shift_control = QDoubleSpinBox()
        self.label_shift_control.setMaximum(1.0)
        self.label_shift_control.setMinimum(-1.0)
        self.label_shift_control.setSingleStep(0.01)
        self.label_shift_control.setValue(0.05)
        self.label_shift_control.valueChanged.connect(self.signal_label_shift)

        l_show_only = QLabel("Show only")
        self.show_only_btn = QPushButton("Edit")
        self.show_only_btn.clicked.connect(self.signal_show_only)

        gbox = QGridLayout()
        layout_table = [
            [l_show_axis, self.show_axis_ckbox],
            [l_show_model, self.show_model_ckbox],
            [l_style, self.model_style_select],
            [l_width, self.width_control],
            [l_opacity, self.opacity_control],
            [l_show_label, self.show_label_ckbox],
            [l_label_size, self.label_size_control],
            [l_label_shift, self.label_shift_control],
            [l_show_only, self.show_only_btn],
        ]
        for i, row in enumerate(layout_table):
            for j, _obj in enumerate(row):
                gbox.addWidget(_obj, i, j)

        vbox = QVBoxLayout()
        vbox.addLayout(gbox)
        vbox.addStretch(1)
        self.setLayout(vbox)

    def update_param(self, option):
        self.signal_object_changed.emit()


class MainWindow(QMainWindow):

    def __init__(self, canvas_only=False):
        QMainWindow.__init__(self)

        self.chr_colormap = {}
        self.chroms = []

        self.resize(700, 500)
        self.setWindowTitle('NucBrowser')

        self.splitter = QSplitter(Qt.Horizontal)

        self.canvas_grid = []
        self.vsps = []
        self.canvas_grid_widget = QSplitter(Qt.Horizontal)
        self.current_ix = (0, -1)
        self.canvas = None
        self.add_canvas('h')
        self.link_canvas = False

        self.splitter.addWidget(self.canvas_grid_widget)
        self.setCentralWidget(self.splitter)
        self.setWindowIcon(QtGui.QIcon(osp.join(HERE, 'nucbox.svg')))
        self.props = ObjPropPanel()
        if not canvas_only:
            self.add_widgets()

    def add_canvas(self, orientation='h'):
        canvas = Canvas()
        canvas.create_native()
        canvas.native.setParent(self)
        canvas.view.events.mouse_press.connect(self.on_click_canvas)
        canvas.view.events.mouse_move.connect(self.trigger_other_canvas_mouse_event)
        canvas.view.events.mouse_wheel.connect(self.trigger_other_canvas_mouse_event)
        self.canvas = canvas
        ix = self.current_ix
        if orientation == 'h':
            vsp = QSplitter(Qt.Vertical)
            vsp.addWidget(canvas.native)
            self.canvas_grid.append([canvas])
            self.canvas_grid_widget.addWidget(vsp)
            self.vsps.append(vsp)
            ix = (ix[0], len(self.canvas_grid) - 1)
        elif orientation == 'v':
            vsp = self.vsps[ix[1]]
            vsp.addWidget(canvas.native)
            col = self.canvas_grid[ix[1]]
            col.append(canvas)
            ix = (len(col) - 1, ix[1])
        else:
            raise ValueError(f"orientation expect 'h' or 'v', got {orientation}")
        self.current_ix = ix
        self.update_canvas_border_color()

    def remove_canvas(self):
        if len(list(self.get_all_canvas())) == 1:
            return
        ix = self.current_ix
        new_ix = list(ix)
        col = self.canvas_grid[ix[1]]
        col.pop(ix[0])
        if len(col) == 0:
            self.canvas_grid.pop(ix[1])
            vsp = self.vsps.pop(ix[1])
            new_ix[1] = max(0, ix[1]-1)
            vsp.hide()
            del vsp
        new_ix[0] = min(len(col)-1, ix[0])
        new_ix = tuple(new_ix)
        self.canvas.native.setVisible(False)
        del self.canvas
        self.change_current_canvas(new_ix, force_update_props=True)

    def get_all_canvas(self):
        return itertools.chain.from_iterable(self.canvas_grid)

    def trigger_other_canvas_mouse_event(self, event):
        if not self.link_canvas:
            return
        a = event.source.canvas
        for b in self.get_all_canvas():
            if b is not a:
                for wref, name in b.view.events.mouse_move.callbacks:
                    if name == "viewbox_mouse_event":
                        wref().viewbox_mouse_event(event)
                        break

    def get_canvas_ix(self, canvas):
        for j, col in enumerate(self.canvas_grid):
            for i, c in enumerate(col):
                if c is canvas:
                    return (i, j)
        return None

    def on_click_canvas(self, event):
        new = event.source.canvas
        new_ix = self.get_canvas_ix(new)
        self.change_current_canvas(new_ix)

    def change_current_canvas(self, new_ix, force_update_props=False):
        old_ix = self.current_ix
        self.canvas = new = self.canvas_grid[new_ix[1]][new_ix[0]]
        if (force_update_props or (new_ix != old_ix)) and (new.info['df'] is not None):
            self.props.model_style_select.setCurrentText(new.cache_props['style'])
            self.props.width_control.setValue(new.cache_props['width'])
            self.props.opacity_control.setValue(new.cache_props['opacity'])
            self.show_only_ranges.setRanges(new.info['show_only_ranges'], block_signal=True)
        self.current_ix = new_ix
        self.update_canvas_border_color()

    def update_canvas_border_color(self):
        if (len(self.canvas_grid) == 1) and (len(self.canvas_grid[0]) == 1):
            return
        for canvas in self.get_all_canvas():
            if canvas is self.canvas:
                c = Color("#ff0000")
            else:
                c = Color("#000000")
            canvas.view.border_color = c

    def add_widgets(self):
        self.splitter.addWidget(self.props)
        self.show_only_ranges = RangeList("Show only ranges", self.chroms)
        self._create_actions()
        self._create_menubar()
        self._connect_events()

    def _create_actions(self):
        self.action_open = QAction("&Open...", self)
        self.action_add_canvas_hor = QAction("&Add canvas(right)", self)
        self.action_add_canvas_ver = QAction("&Add canvas(below)", self)
        self.action_remove_canvas = QAction("&Remove canvas", self)
        self.action_change_link_status = QAction("&Link canvases", self)

    def _create_menubar(self):
        menubar = QMenuBar(self)
        file_menu = QMenu("&File", self)
        file_menu.addAction(self.action_open)
        menubar.addMenu(file_menu)
        canvas_menu = QMenu("&Canvas", self)
        canvas_menu.addAction(self.action_add_canvas_hor)
        canvas_menu.addAction(self.action_add_canvas_ver)
        canvas_menu.addAction(self.action_remove_canvas)
        canvas_menu.addAction(self.action_change_link_status)
        menubar.addMenu(canvas_menu)
        help_menu = QMenu("&Help", self)
        menubar.addMenu(help_menu)
        self.setMenuBar(menubar)

    def _connect_events(self):
        self.props.signal_show_model.connect(self._all_or_current(self.on_toggle_show_model))
        self.props.signal_show_axis.connect(self._all_or_current(self.on_toggle_show_axis))
        self.props.signal_width.connect(self._all_or_current(self.on_width_changed))
        self.props.signal_opacity.connect(self._all_or_current(self.on_opacity_changed))
        self.props.signal_show_label.connect(self._all_or_current(self.on_toggle_show_label))
        self.props.signal_label_font_size.connect(self._all_or_current(self.on_label_size_changed))
        self.props.signal_label_shift.connect(self._all_or_current(self.on_label_shift_changed))
        self.props.signal_show_only.connect(self._all_or_current(self.open_show_only))
        self.props.signal_change_style.connect(self._all_or_current(self.on_model_style_change))
        self.show_only_ranges.signal_item_changed.connect(self._all_or_current(self.on_show_only_ranges_changed))
        self.action_open.triggered.connect(self.open_file_dialog)
        self.action_add_canvas_hor.triggered.connect(self.add_canvas_hor)
        self.action_add_canvas_ver.triggered.connect(self.add_canvas_ver)
        self.action_change_link_status.triggered.connect(self.change_canvas_link)
        self.action_remove_canvas.triggered.connect(self.remove_canvas)

    def _all_or_current(self, f):
        def wrap(*args, **kwargs):
            current = self.canvas
            if self.link_canvas:
                # apply to all canvas
                for c in self.get_all_canvas():
                    self.canvas = c
                    f(*args, **kwargs)
                self.canvas = current
            else:
                # only current
                f(*args, **kwargs)
        return wrap

    def change_canvas_link(self):
        self.link_canvas = not self.link_canvas
        if self.link_canvas:
            self.action_change_link_status.setText("&Unlink canvases")
        else:
            self.action_change_link_status.setText("&Link canvases")

    def add_canvas_hor(self):
        self.add_canvas('h')

    def add_canvas_ver(self):
        self.add_canvas('v')

    def on_model_style_change(self):
        style = self.props.model_style_select.currentText()
        self.canvas.remove_model()
        self.canvas.draw_model(style=style)
        if style == 'line':
            self.props.width_control.setMaximum(20.0)
            self.props.width_control.setMinimum(1.0)
            self.props.width_control.setSingleStep(1.0)
            self.props.width_control.setValue(1.0)
        elif style == 'points':
            self.props.width_control.setMaximum(2.0)
            self.props.width_control.setMinimum(0)
            self.props.width_control.setSingleStep(0.1)
            self.props.width_control.setValue(0.5)
        elif style == 'tube':
            self.props.width_control.setMaximum(2.0)
            self.props.width_control.setMinimum(0)
            self.props.width_control.setSingleStep(0.05)
            self.props.width_control.setValue(0.1)

    def on_show_only_ranges_changed(self):
        ranges = self.show_only_ranges.ranges
        self.canvas.info['show_only_ranges'] = copy(ranges)
        df = self.canvas.info['df']
        if len(ranges) == 0:
            df_ = df
        elif self.show_only_ranges.reverse_ck.isChecked():
            ix = np.full(df.shape[0], True)
            for gr in ranges:
                sdf = df[(df['chrom'] == gr.chr) & (df['start'] >= gr.start) & (df['end'] <= gr.end)]
                ix[sdf.index] = False
            df_ = df[ix]
        else:
            sub_dfs = []
            for gr in ranges:
                sdf = df[(df['chrom'] == gr.chr) & (df['start'] >= gr.start) & (df['end'] <= gr.end)]
                sub_dfs.append(sdf)
            df_ = pd.concat(sub_dfs).sort_values(by="start")
        self.on_data_changed(df_)

    def open_show_only(self):
        self.show_only_ranges.show()

    def open_file_dialog(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        path, _ = QFileDialog.getOpenFileName(self, "Open", "", "All Files (*);;CSV Files(*.csv)", options=options)
        if path:
            print(path)
            df = read_particles(path)
            self.load_model(df)
            self.init_draw()
            self.update_view()

    def init_draw(self):
        self.canvas.remove_model()
        self.canvas.draw_model(df=self.canvas.info['df'], chr_colormap=self.chr_colormap, style='line', width=1)
        self.canvas.draw_label(self.canvas.info['df'], color=self.chr_colormap)

    def on_data_changed(self, df=None):
        if df is None:
            df = self.canvas.info['df']
        self.canvas.remove_model()
        self.canvas.remove_label()
        self.canvas.draw_model(df=df)
        self.on_toggle_show_model()
        self.canvas.draw_label(df, color=self.chr_colormap)
        self.on_toggle_show_label()

    def update_view(self):
        self.on_model_style_change()
        self.on_toggle_show_model()
        self.on_toggle_show_axis()
        self.on_width_changed()
        self.on_opacity_changed()
        self.on_toggle_show_label()
        self.on_label_size_changed()
        self.on_label_shift_changed()

    def on_label_shift_changed(self):
        val = self.props.label_shift_control.value()
        for i, l in enumerate(self.canvas.labels):
            ori = self.canvas.label_ori_pos[i]
            l.pos = ori * (1+val)

    def on_label_size_changed(self):
        val = self.props.label_size_control.value()
        self.canvas.set_label_props('font_size', val)

    def on_toggle_show_label(self):
        val = self.props.show_label_ckbox.isChecked()
        self.canvas.set_label_props('visible', val)

    def on_opacity_changed(self):
        val = self.props.opacity_control.value()
        self.canvas.set_model_props('opacity', val)
        self.canvas.cache_props['opacity'] = val

    def on_width_changed(self):
        style = self.props.model_style_select.currentText()
        width = self.props.width_control.value()
        self.canvas.cache_props['width'] = width
        for l in self.canvas.lines:
            if style == "line":
                l.set_data(width=width)
            else:
                self.canvas.remove_model()
                self.canvas.draw_model(width=width)
                self.on_opacity_changed()

    def on_toggle_show_model(self):
        val = self.props.show_model_ckbox.isChecked()
        self.canvas.set_model_props('visible', val)

    def on_toggle_show_axis(self):
        val = self.props.show_axis_ckbox.isChecked()
        self.canvas.axis.visible = val

    def load_model(self, df):
        self.canvas.info['df'] = df
        self.chroms.clear()
        for chr in list(df['chrom'].unique()):
            self.chroms.append(chr)
        for c in self.chroms:
            if c not in self.chr_colormap:
                self.chr_colormap[c] = random_color()

    def adjust_camera(self, factor=2.0):
        pos = self.canvas.info['df'][['x', 'y', 'z']].values
        norm = np.sqrt(sum([(pos[:, i])**2 for i in range(3)]))
        max_norm = np.max(norm)
        self.canvas.view.camera.distance = max_norm * factor


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


class GenomeRange(object):
    SUPER_MAX = 100000000000000000000

    def __init__(self, chr, start=0, end=SUPER_MAX):
        self.chr = chr
        if (start is not None) and (end is not None):
            self.start = int(start)
            self.end = int(end)
            assert self.end > self.start >= 0

    @staticmethod
    def parse_text(text, valid_chr_names=None):
        if ":" in text:
            assert "-" in text
            tp1 = text.split(":")
            chr = tp1[0]
            start, end = tp1[1].split("-")
            gr = GenomeRange(chr, start, end)
        else:
            gr = GenomeRange(text)
        if valid_chr_names is not None:
            assert gr.chr in valid_chr_names
        return gr

    def __str__(self):
        if (self.start == 0) and (self.end == self.SUPER_MAX):
            return self.chr
        else:
            return f"{self.chr}:{self.start}-{self.end}"

    def __repr__(self):
        return f"GenomeRange({str(self)})"

    def __hash__(self):
        return hash(str(self))

    def __eq__(self, other):
        return str(self) == str(other)

    def __gt__(self, other):
        return (self.start > other.start) and (self.end > other.end)

    def __lt__(self, other):
        return (self.start < other.start) and (self.end < other.end)


class RangeList(QWidget):

    signal_item_changed = pyqtsignal(name="item_changed")

    def __init__(self, title, chr_names=None):
        super().__init__()
        self.title = title
        self.init_UI()
        self.ranges = set()
        self.chr_names = chr_names

    def init_UI(self):
        l_reverse = QLabel("Reverse mode: not show the selected regions")
        self.reverse_ck = QCheckBox()
        reverse_hbox = QHBoxLayout()
        reverse_hbox.addWidget(l_reverse)
        reverse_hbox.addWidget(self.reverse_ck)
        l = QLabel("Input genome range, like: chr1:10000-200000")
        self.le = QLineEdit()
        self.le.returnPressed.connect(self.append)
        self.add_btn = QPushButton("Add")
        self.add_btn.pressed.connect(self.append)
        add_hbox = QHBoxLayout()
        add_hbox.addWidget(self.le, stretch=2)
        add_hbox.addWidget(self.add_btn, stretch=1)
        self.tb = QTextBrowser()
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.pressed.connect(self.clear)
        vbox = QVBoxLayout()
        vbox.addWidget(l, 0)
        vbox.addLayout(add_hbox, 1)
        vbox.addWidget(self.tb, 2)
        vbox.addLayout(reverse_hbox, 3)
        vbox.addWidget(self.clear_btn, 4)
        self.setLayout(vbox)
        self.setWindowTitle(self.title)
        self.setGeometry(300, 300, 300, 300)
        self._connect_change()

    def _connect_change(self):
        self.reverse_ck.toggled.connect(self.signal_item_changed)
        self.tb.textChanged.connect(self.signal_item_changed)

    def _disconnect_change(self):
        self.reverse_ck.toggled.disconnect()
        self.tb.textChanged.disconnect()

    def append(self, text=None):
        if text is None:
            text = self.le.text()
        try:
            gr = GenomeRange.parse_text(text, self.chr_names)
            if gr not in self.ranges:
                self.ranges.add(gr)
                self.tb.append(str(gr))
                self.le.setStyleSheet("")
        except Exception as e:
            print(f"{text} is not a valid genome range")
            print(str(e))
            self.le.setStyleSheet("border: 1px solid red;")

    def clear(self):
        self.ranges.clear()
        self.tb.clear()

    def setRanges(self, ranges, block_signal=False):
        if block_signal:
            self._disconnect_change()
        self.clear()
        for r in ranges:
            self.append(str(r))
        if block_signal:
            self._connect_change()


def read_and_show(path):
    df = read_particles(path)
    qapp = PyQt5.QtWidgets.QApplication(["1"])
    win = MainWindow()
    win.load_model(df)
    win.init_draw()
    win.update_view()
    win.show()
    app.run()


if __name__ == '__main__':
    fire.Fire(read_and_show)
