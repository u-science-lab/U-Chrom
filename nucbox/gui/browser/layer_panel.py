from PyQt5.QtWidgets import (QComboBox, QDoubleSpinBox, QPushButton, QSpinBox, QWidget, QLabel, 
                             QGridLayout, QVBoxLayout, QCheckBox)
from .utils import pyqtsignal


class LayerPanel(QWidget):

    def __init__(self, parent=None):
        super(LayerPanel, self).__init__(parent)

        l_show_axis = QLabel("Show axis")
        self.show_axis_ckbox = QCheckBox()

        gbox = QGridLayout()
        layout_table = [
            [l_show_axis, self.show_axis_ckbox],
        ]
        for i, row in enumerate(layout_table):
            for j, _obj in enumerate(row):
                gbox.addWidget(_obj, i, j)

        title_layout = QVBoxLayout()
        title_layout.addWidget(QLabel("<h2>Layers</h2>"))

        vbox = QVBoxLayout()
        vbox.addLayout(title_layout)
        vbox.addLayout(gbox)
        vbox.addStretch(1)
        self.setLayout(vbox)
