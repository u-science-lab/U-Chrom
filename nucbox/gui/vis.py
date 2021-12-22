import random
import numpy as np
from vispy import scene, app
from vispy.color import Color
import fire

from sip import setapi
setapi("QVariant", 2)
setapi("QString", 2)

import PyQt5
from PyQt5 import QtCore
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QMainWindow, QWidget, QLabel, 
                             QGridLayout, QVBoxLayout, QCheckBox,
                             QSplitter)

from ..io import read_particles

# Provide automatic signal function selection for PyQtX/PySide2
pyqtsignal = QtCore.pyqtSignal if hasattr(QtCore, 'pyqtSignal') else QtCore.Signal


def random_color():
    return "#"+''.join([random.choice('0123456789ABCDEF') for j in range(6)])


class ObjectWidget(QWidget):
    signal_object_changed = pyqtsignal(name='objectChanged')

    def __init__(self, parent=None):
        super(ObjectWidget, self).__init__(parent)

        l_show_model = QLabel("Show model")
        self.show_model_ckbox = QCheckBox()
        self.show_model_ckbox.setChecked(True)
        self.show_model_ckbox.toggled.connect(self.signal_object_changed)

        l_show_axis = QLabel("Show axis")
        self.show_axis_ckbox = QCheckBox()
        self.show_axis_ckbox.toggled.connect(self.signal_object_changed)

        gbox = QGridLayout()
        gbox.addWidget(l_show_model, 0, 0)
        gbox.addWidget(self.show_model_ckbox, 0, 1)
        gbox.addWidget(l_show_axis, 1, 0)
        gbox.addWidget(self.show_axis_ckbox, 1, 1)

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
        self.props.signal_object_changed.connect(self.update_view)

        self.chr_colormap = {}
        self.load_model(path)
        self.canvas.draw_model(self.df, self.chr_colormap)
        self.canvas.set_model_visible(False)

        self.update_view()

    def update_view(self):
        if self.props.show_model_ckbox.isChecked():
            self.canvas.set_model_visible(True)
        else:
            self.canvas.set_model_visible(False)
        if self.props.show_axis_ckbox.isChecked():
            self.canvas.axis.visible = True
        else:
            self.canvas.axis.visible = False

    def load_model(self, path):
        self.df = df = read_particles(path)
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

    def draw_model(self, df, chr_colormap):
        lines = []
        for chrom in chr_colormap.keys():
            sdf = df[df['chrom'] == chrom]
            pos = sdf[['x', 'y', 'z']].values
            color = chr_colormap.get(chrom, "#888888")
            line = scene.visuals.Line(pos=pos, parent=self.view.scene, color=Color(color))
            lines.append(line)
        self.lines = lines

    def set_model_visible(self, val):
        for o in self.lines:
            o.visible = val


def read_and_show(path):
    qapp = PyQt5.QtWidgets.QApplication(["1"])
    win = MainWindow(path)
    win.show()
    app.run()



if __name__ == '__main__':
    fire.Fire(read_and_show)
