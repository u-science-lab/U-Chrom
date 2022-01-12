from PyQt5.QtWidgets import (QComboBox, QDoubleSpinBox, QPushButton, QSpinBox, QWidget, QLabel, 
                             QGridLayout, QVBoxLayout, QCheckBox)
from .utils import pyqtsignal


class ObjPropPanel(QWidget):
    signal_show_model = pyqtsignal(name='show_model')
    signal_width = pyqtsignal(name='width')
    signal_opacity = pyqtsignal(name='opacity')
    signal_show_label = pyqtsignal(name='show_label')
    signal_label_font_size = pyqtsignal(name="label_font_size")
    signal_label_shift = pyqtsignal(name="label_shift")
    signal_show_only = pyqtsignal(name="show_only")
    signal_change_style = pyqtsignal(name="change_style")

    def __init__(self, parent=None):
        super(ObjPropPanel, self).__init__(parent)

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

        title_layout = QVBoxLayout()
        title_layout.addWidget(QLabel("<h2>Properties</h2"))

        gbox = QGridLayout()
        layout_table = [
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
        vbox.addLayout(title_layout)
        vbox.addLayout(gbox)
        vbox.addStretch(1)
        self.setLayout(vbox)

    def update_param(self, option):
        self.signal_object_changed.emit()
