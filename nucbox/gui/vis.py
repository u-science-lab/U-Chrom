import random
import os.path as osp
from PyQt5 import QtGui

import numpy as np
from vispy import scene, app
from vispy.color import Color
import fire

import PyQt5
from PyQt5 import QtCore
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QAction, QDoubleSpinBox, QFileDialog, QMainWindow, QMenu, QMenuBar, QSpinBox, QWidget, QLabel, 
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

        vbox = QVBoxLayout()
        vbox.addLayout(gbox)
        vbox.addStretch(1)
        self.setLayout(vbox)

    def update_param(self, option):
        self.signal_object_changed.emit()


class MainWindow(QMainWindow):

    def __init__(self, canvas_only=False):
        QMainWindow.__init__(self)

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

        self.chr_colormap = {}
        self.chroms = []

    def add_widgets(self):
        self.splitter.addWidget(self.props)
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

    def open_file_dialog(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        path, _ = QFileDialog.getOpenFileName(self, "Open", "", "All Files (*);;CSV Files(*.csv)", options=options)
        if path:
            print(path)
            df = read_particles(path)
            self.load_model(df)
            self.canvas.remove_model()
            self.canvas.remove_label()
            self.draw_model()

    def draw_model(self):
        self.canvas.draw_model(self.df, self.chr_colormap)
        self.canvas.set_model_props('visible', False)
        self.canvas.draw_label(self.df, color=self.chr_colormap)
        self.update_view()

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
        self.canvas.draw_model(self.df, self.chr_colormap, width=width)
        self.on_opacity_changed()

    def on_toggle_show_model(self):
        val = self.props.show_model_ckbox.isChecked()
        self.canvas.set_model_props('visible', val)

    def on_toggle_show_axis(self):
        val = self.props.show_axis_ckbox.isChecked()
        self.canvas.axis.visible = val

    def load_model(self, df):
        self.df = df
        self.chroms = chroms = list(df['chrom'].unique())
        for c in chroms:
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
        lines = []
        for chrom in chr_colormap.keys():
            sdf = df[df['chrom'] == chrom]
            pos = sdf[['x', 'y', 'z']].values
            color = chr_colormap.get(chrom, "#888888")
            line = scene.visuals.Line(pos=pos, parent=self.view.scene, color=Color(color), **props)
            lines.append(line)
        self.lines = lines

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
        self.lines = []

    def remove_label(self):
        for o in self.labels:
            o.parent = None
        self.labels = []
        self.label_ori_pos = []


def read_and_show(path):
    df = read_particles(path)
    qapp = PyQt5.QtWidgets.QApplication(["1"])
    win = MainWindow()
    win.load_model(df)
    win.draw_model()
    win.show()
    app.run()


if __name__ == '__main__':
    fire.Fire(read_and_show)
