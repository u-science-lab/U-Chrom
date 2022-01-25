from PyQt5.QtWidgets import (QComboBox, QDoubleSpinBox, QSpinBox, QWidget, QLabel, 
                             QGridLayout, QVBoxLayout, QCheckBox, QPushButton)


class LayerPropsPanel(QWidget):
    def __init__(self, parent=None, grid_table=[], operation_widgets=[], title="Properties"):
        super().__init__(parent)
        self.top_layout = QVBoxLayout()
        self.title = QLabel(f"<h2>{title}</h2>")
        self.top_layout.addWidget(self.title)
        self.grid_layout = QGridLayout()
        for i, row in enumerate(grid_table):
            for j, _obj in enumerate(row):
                self.grid_layout.addWidget(_obj, i, j)
        self.top_layout.addLayout(self.grid_layout)
        self.top_layout.addStretch()
        self.setLayout(self.top_layout)
        self.layers = []
        self.operation_widgets = []
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self.on_delete_btn)
        self.operation_widgets.append(self.delete_btn)
        self.operation_widgets += operation_widgets
        self.operations_panel = QWidget()
        vbox = QVBoxLayout()
        for op in self.operation_widgets:
            vbox.addWidget(op)
        vbox.addStretch()
        self.operations_panel.setLayout(vbox)

    def on_delete_btn(self):
        for layer in self.layers:
            idx = layer.canvas.control_panel.delete(layer)
            layer.canvas.control_panel.reset_current(idx)

    def connect_with(self, layer):
        self.layers.append(layer)


class ChromatinProps(LayerPropsPanel):
    def __init__(self):

        l_show_model = QLabel("Show model")
        self.show_model_ckbox = QCheckBox()
        self.show_model_ckbox.setChecked(True)
        self.show_model_ckbox.toggled.connect(self.on_toggle_show_model)

        l_style = QLabel("Model style")
        self.model_style_select = QComboBox()
        self.model_style_select.addItem("line")
        self.model_style_select.addItem("points")
        self.model_style_select.addItem("tube")
        self.model_style_select.currentIndexChanged.connect(self.on_model_style_change)

        l_width = QLabel("Width/Radius")
        self.width_control = QDoubleSpinBox()
        self.width_control.setMaximum(10.0)
        self.width_control.setMinimum(0.0)
        self.width_control.setSingleStep(0.2)
        self.width_control.setValue(1.0)
        self.width_control.valueChanged.connect(self.on_width_changed)

        l_opacity = QLabel("Opacity")
        self.opacity_control = QDoubleSpinBox()
        self.opacity_control.setMaximum(1.0)
        self.opacity_control.setMinimum(0.0)
        self.opacity_control.setSingleStep(0.05)
        self.opacity_control.setValue(1.0)
        self.opacity_control.valueChanged.connect(self.on_opacity_changed)
 
        layout_table = [
            [l_show_model, self.show_model_ckbox],
            [l_style, self.model_style_select],
            [l_width, self.width_control],
            [l_opacity, self.opacity_control],
        ]

        self.subset_btn = QPushButton("Subset")
        super().__init__(grid_table=layout_table, operation_widgets=[self.subset_btn])

    def on_toggle_show_model(self):
        val = self.show_model_ckbox.isChecked()
        for layer in self.layers:
            layer.set_props('visible', val)

    def on_width_changed(self):
        style = self.model_style_select.currentText()
        width = self.width_control.value()
        for layer in self.layers:
            layer.cache_props['width'] = width
            for o in layer.vis_objs:
                if style == "line":
                    o.set_data(width=width)
                else:
                    layer.remove()
                    layer.draw(width=width)
        self.on_opacity_changed()

    def on_opacity_changed(self):
        val = self.opacity_control.value()
        for layer in self.layers:
            layer.set_props('opacity', val)
            layer.cache_props['opacity'] = val

    def on_model_style_change(self):
        style = self.model_style_select.currentText()
        for layer in self.layers:
            layer.remove()
            layer.draw(style=style)
            if style == 'line':
                self.width_control.setMaximum(20.0)
                self.width_control.setMinimum(1.0)
                self.width_control.setSingleStep(1.0)
                self.width_control.setValue(1.0)
            elif style == 'points':
                self.width_control.setMaximum(2.0)
                self.width_control.setMinimum(0)
                self.width_control.setSingleStep(0.1)
                self.width_control.setValue(0.5)
            elif style == 'tube':
                self.width_control.setMaximum(2.0)
                self.width_control.setMinimum(0)
                self.width_control.setSingleStep(0.05)
                self.width_control.setValue(0.1)



class ChrLabelProps(LayerPropsPanel):
    def __init__(self):
        l_show_label = QLabel("Show label")
        self.show_label_ckbox = QCheckBox()
        self.show_label_ckbox.toggled.connect(self.on_toggle_show_label)

        l_label_size = QLabel("Label size")
        self.label_size_control = QSpinBox()
        self.label_size_control.setMaximum(10000)
        self.label_size_control.setMinimum(1)
        self.label_size_control.setSingleStep(100)
        self.label_size_control.setValue(1000)
        self.label_size_control.valueChanged.connect(self.on_label_size_changed)

        l_label_shift = QLabel("Label shift")
        self.label_shift_control = QDoubleSpinBox()
        self.label_shift_control.setMaximum(1.0)
        self.label_shift_control.setMinimum(-1.0)
        self.label_shift_control.setSingleStep(0.01)
        self.label_shift_control.setValue(0.05)
        self.label_shift_control.valueChanged.connect(self.on_label_shift_changed)

        layout_table = [
            [l_show_label, self.show_label_ckbox],
            [l_label_size, self.label_size_control],
            [l_label_shift, self.label_shift_control],
        ]

        super().__init__(grid_table=layout_table)

    def on_toggle_show_label(self):
        val = self.show_label_ckbox.isChecked()
        for layer in self.layers:
            layer.set_props('visible', val)

    def on_label_size_changed(self):
        val = self.label_size_control.value()
        for layer in self.layers:
            layer.set_label_props('font_size', val)

    def on_label_shift_changed(self):
        val = self.label_shift_control.value()
        for layer in self.layers:
            for i, l in enumerate(layer.vis_objs):
                ori = layer.label_ori_pos[i]
                l.pos = ori * (1+val)


