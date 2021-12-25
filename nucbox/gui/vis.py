import random
import os.path as osp

from PyQt5 import QtGui
import pandas as pd
import numpy as np
from vispy import scene, app
from vispy.color import Color
import fire

import PyQt5
from PyQt5 import QtCore
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QAction, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLineEdit, QMainWindow, QMenu, QMenuBar, QPushButton, QSpinBox, QTextBrowser, QWidget, QLabel, 
                             QGridLayout, QVBoxLayout, QCheckBox,
                             QSplitter)

from ..io import read_particles


HERE = osp.dirname(osp.abspath(__file__))

# Provide automatic signal function selection for PyQtX/PySide2
pyqtsignal = QtCore.pyqtSignal if hasattr(QtCore, 'pyqtSignal') else QtCore.Signal


def random_color():
    return "#"+''.join([random.choice('0123456789ABCDEF') for j in range(6)])


class ObjectWidget(QWidget):
    signal_show_model = pyqtsignal(name='show_model')
    signal_show_axis = pyqtsignal(name='show_axis')
    signal_width = pyqtsignal(name='width')
    signal_opacity = pyqtsignal(name='opacity')
    signal_show_label = pyqtsignal(name='show_label')
    signal_label_font_size = pyqtsignal(name="label_font_size")
    signal_label_shift = pyqtsignal(name="label_shift")
    signal_show_only = pyqtsignal(name="show_only")

    def __init__(self, parent=None):
        super(ObjectWidget, self).__init__(parent)

        l_show_axis = QLabel("Show axis")
        self.show_axis_ckbox = QCheckBox()
        self.show_axis_ckbox.toggled.connect(self.signal_show_axis)

        l_show_model = QLabel("Show model")
        self.show_model_ckbox = QCheckBox()
        self.show_model_ckbox.setChecked(True)
        self.show_model_ckbox.toggled.connect(self.signal_show_model)

        l_width = QLabel("Width")
        self.width_control = QSpinBox()
        self.width_control.setMaximum(10)
        self.width_control.setMinimum(1)
        self.width_control.valueChanged.connect(self.signal_width)
        
        l_opacity = QLabel("Opacity")
        self.opacity_control = QDoubleSpinBox()
        self.opacity_control.setMaximum(1.0)
        self.opacity_control.setMinimum(0.0)
        self.opacity_control.setSingleStep(0.1)
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
        gbox.addWidget(l_show_axis, 0, 0)
        gbox.addWidget(self.show_axis_ckbox, 0, 1)
        gbox.addWidget(l_show_model, 1, 0)
        gbox.addWidget(self.show_model_ckbox, 1, 1)
        gbox.addWidget(l_width, 2, 0)
        gbox.addWidget(self.width_control, 2, 1)
        gbox.addWidget(l_opacity, 3, 0)
        gbox.addWidget(self.opacity_control, 3, 1)
        gbox.addWidget(l_show_label, 4, 0)
        gbox.addWidget(self.show_label_ckbox, 4, 1)
        gbox.addWidget(l_label_size, 5, 0)
        gbox.addWidget(self.label_size_control, 5, 1)
        gbox.addWidget(l_label_shift, 6, 0)
        gbox.addWidget(self.label_shift_control, 6, 1)
        gbox.addWidget(l_show_only, 7, 0)
        gbox.addWidget(self.show_only_btn, 7, 1)

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

        self.canvas = Canvas()
        self.canvas.create_native()
        self.canvas.native.setParent(self)

        self.props = ObjectWidget()
        self.splitter.addWidget(self.canvas.native)
        self.setCentralWidget(self.splitter)
        self.setWindowIcon(QtGui.QIcon(osp.join(HERE, 'nucbox.svg')))

        if not canvas_only:
            self.add_widgets()

    def add_widgets(self):
        self.splitter.addWidget(self.props)
        self.show_only_ranges = RangeList("Show only ranges", self.chroms)
        self._create_actions()
        self._create_menubar()
        self._connect_events()

    def _create_actions(self):
        self.open_action = QAction("&Open...", self)

    def _create_menubar(self):
        menubar = QMenuBar(self)
        file_menu = QMenu("&File", self)
        file_menu.addAction(self.open_action)
        menubar.addMenu(file_menu)
        help_menu = QMenu("&Help", self)
        menubar.addMenu(help_menu)
        self.setMenuBar(menubar)

    def _connect_events(self):
        self.props.signal_show_model.connect(self.on_toggle_show_model)
        self.props.signal_show_axis.connect(self.on_toggle_show_axis)
        self.props.signal_width.connect(self.on_width_changed)
        self.props.signal_opacity.connect(self.on_opacity_changed)
        self.props.signal_show_label.connect(self.on_toggle_show_label)
        self.props.signal_label_font_size.connect(self.on_label_size_changed)
        self.props.signal_label_shift.connect(self.on_label_shift_changed)
        self.open_action.triggered.connect(self.open_file_dialog)
        self.props.signal_show_only.connect(self.open_show_only)
        self.show_only_ranges.signal_item_changed.connect(self.on_show_only_ranges_changed)

    def on_show_only_ranges_changed(self):
        ranges = self.show_only_ranges.ranges
        self.remove()
        df = self.df
        if len(ranges) == 0:
            self.draw(df)
        else:
            sub_dfs = []
            for gr in ranges:
                sdf = df[(df['chrom'] == gr.chr) & (df['start'] >= gr.start) & (df['end'] <= gr.end)]
                sub_dfs.append(sdf)
            df_ = pd.concat(sub_dfs).sort_values(by="start")
            self.draw(df_)

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
            self.remove()
            self.draw()

    def draw(self, df=None):
        if df is None:
            df = self.df
        self.canvas.draw_model(df, self.chr_colormap)
        self.on_toggle_show_model()
        self.canvas.draw_label(df, color=self.chr_colormap)
        self.on_toggle_show_label()

    def remove(self):
        self.canvas.remove_model()
        self.canvas.remove_label()

    def update_view(self):
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

    def on_width_changed(self):
        self.canvas.remove_model()
        width = self.props.width_control.value()
        self.canvas.draw_model(self.canvas.df, self.chr_colormap, width=width)
        self.on_opacity_changed()

    def on_toggle_show_model(self):
        val = self.props.show_model_ckbox.isChecked()
        self.canvas.set_model_props('visible', val)

    def on_toggle_show_axis(self):
        val = self.props.show_axis_ckbox.isChecked()
        self.canvas.axis.visible = val

    def load_model(self, df):
        self.df = df
        self.chroms.clear()
        for chr in list(df['chrom'].unique()):
            self.chroms.append(chr)
        for c in self.chroms:
            if c not in self.chr_colormap:
                self.chr_colormap[c] = random_color()

    def adjust_camera(self, factor=2.0):
        pos = self.df[['x', 'y', 'z']].values
        norm = np.sqrt(sum([(pos[:, i])**2 for i in range(3)]))
        max_norm = np.max(norm)
        self.canvas.view.camera.distance = max_norm * factor


class Canvas(scene.SceneCanvas):

    def __init__(self):
        scene.SceneCanvas.__init__(self, keys=None)
        self.size = 800, 600
        self.unfreeze()
        self.df = None
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

    def draw_model(self, df, chr_colormap, **props):
        self.df = df
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
                line = scene.visuals.Line(pos=p, parent=self.view.scene, color=Color(color), **props)
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
        l = QLabel("Input genome range, like: chr1:10000-200000 press Enter")
        self.le = QLineEdit()
        self.le.returnPressed.connect(self.append)
        self.add_btn = QPushButton("Add")
        self.add_btn.pressed.connect(self.append)
        add_hbox = QHBoxLayout()
        add_hbox.addWidget(self.le, stretch=2)
        add_hbox.addWidget(self.add_btn, stretch=1)
        self.tb = QTextBrowser()
        self.tb.textChanged.connect(self.signal_item_changed)
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.pressed.connect(self.clear)
        vbox = QVBoxLayout()
        vbox.addWidget(l, 0)
        vbox.addLayout(add_hbox, 1)
        vbox.addWidget(self.tb, 2)
        vbox.addWidget(self.clear_btn, 3)
        self.setLayout(vbox)
        self.setWindowTitle(self.title)
        self.setGeometry(300, 300, 300, 300)

    def append(self):
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


def read_and_show(path):
    df = read_particles(path)
    qapp = PyQt5.QtWidgets.QApplication(["1"])
    win = MainWindow()
    win.load_model(df)
    win.draw()
    win.update_view()
    win.show()
    app.run()


if __name__ == '__main__':
    fire.Fire(read_and_show)
