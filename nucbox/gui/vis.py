import random
from vispy import scene, app
from vispy.color import Color
import fire

from sip import setapi
setapi("QVariant", 2)
setapi("QString", 2)

import PyQt5
from PyQt5 import QtCore
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDoubleSpinBox, QMainWindow, QSpinBox, QWidget, QLabel, 
                             QGridLayout, QVBoxLayout, QCheckBox,
                             QSplitter)

from ..io import read_particles

# Provide automatic signal function selection for PyQtX/PySide2
pyqtsignal = QtCore.pyqtSignal if hasattr(QtCore, 'pyqtSignal') else QtCore.Signal


def random_color():
    return "#"+''.join([random.choice('0123456789ABCDEF') for j in range(6)])


class ObjectWidget(QWidget):
    signal_show_model = pyqtsignal(name='show_model')
    signal_show_axis = pyqtsignal(name='show_axis')
    signal_width = pyqtsignal(name="width")
    signal_opacity = pyqtsignal(name='opacity')

    def __init__(self, parent=None):
        super(ObjectWidget, self).__init__(parent)

        l_show_model = QLabel("Show model")
        self.show_model_ckbox = QCheckBox()
        self.show_model_ckbox.setChecked(True)
        self.show_model_ckbox.toggled.connect(self.signal_show_model)

        l_show_axis = QLabel("Show axis")
        self.show_axis_ckbox = QCheckBox()
        self.show_axis_ckbox.toggled.connect(self.signal_show_axis)

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

        gbox = QGridLayout()
        gbox.addWidget(l_show_model, 0, 0)
        gbox.addWidget(self.show_model_ckbox, 0, 1)
        gbox.addWidget(l_show_axis, 1, 0)
        gbox.addWidget(self.show_axis_ckbox, 1, 1)
        gbox.addWidget(l_width, 2, 0)
        gbox.addWidget(self.width_control, 2, 1)
        gbox.addWidget(l_opacity, 3, 0)
        gbox.addWidget(self.opacity_control, 3, 1)

        vbox = QVBoxLayout()
        vbox.addLayout(gbox)
        vbox.addStretch(1)
        self.setLayout(vbox)

    def update_param(self, option):
        self.signal_object_changed.emit()


class MainWindow(QMainWindow):

    def __init__(self, path):
        QMainWindow.__init__(self)

        self.resize(700, 500)
        self.setWindowTitle('NucBrowser')

        splitter = QSplitter(Qt.Horizontal)

        self.canvas = Canvas()
        self.canvas.create_native()
        self.canvas.native.setParent(self)

        self.props = ObjectWidget()
        splitter.addWidget(self.props)
        splitter.addWidget(self.canvas.native)
        self.setCentralWidget(splitter)

        self.props.signal_show_model.connect(self.on_toggle_show_model)
        self.props.signal_show_axis.connect(self.on_toggle_show_axis)
        self.props.signal_width.connect(self.on_width_changed)
        self.props.signal_opacity.connect(self.on_opacity_changed)

        self.chr_colormap = {}
        self.chroms = []

    def draw_model(self):
        self.canvas.draw_model(self.df, self.chr_colormap)
        self.canvas.set_model_props('visible', False)
        self.update_view()

    def update_view(self):
        self.on_toggle_show_model()
        self.on_toggle_show_axis()
        self.on_width_changed()
        self.on_opacity_changed()

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

    def remove_model(self):
        for o in self.lines:
            o.parent = None
        self.lines = []

    def set_model_props(self, key, val):
        for o in self.lines:
            setattr(o, key, val)


def read_and_show(path):
    df = read_particles(path)
    qapp = PyQt5.QtWidgets.QApplication(["1"])
    win = MainWindow(path)
    win.load_model(df)
    win.draw_model()
    win.show()
    app.run()


if __name__ == '__main__':
    fire.Fire(read_and_show)
