from PyQt5.QtWidgets import (QListWidget, QWidget, QLabel, QHBoxLayout, QVBoxLayout, QStackedWidget)


class LayerPanel(QWidget):

    def __init__(self, parent=None):
        super(LayerPanel, self).__init__(parent)

        self.list = QListWidget()

        title_layout = QVBoxLayout()
        title_layout.addWidget(QLabel("<h2>Layers</h2>"))

        self.operation_stack = QStackedWidget()

        hbox = QHBoxLayout()
        hbox.addWidget(self.list)
        hbox.addWidget(self.operation_stack)

        vbox = QVBoxLayout()
        vbox.addLayout(title_layout)
        vbox.addLayout(hbox)

        self.setLayout(vbox)

    def set_operations_panel(self, widget=None):
        if (widget is not None) and (self.operation_stack.indexOf(widget) < 0):
            self.operation_stack.addWidget(widget)
        self.operation_stack.setCurrentWidget(widget)

    def remove_operations_panel(self, widget):
        self.operation_stack.removeWidget(widget)


class CanvasControl(QWidget):
    def __init__(self, canvas):
        super().__init__()
        self.canvas = canvas
        self.layers = []
        self.current_layer = None

        self.layer_control = LayerPanel()
        self.props_stack = QStackedWidget()
        self.layout: QVBoxLayout = QVBoxLayout()
        self.layout.addWidget(self.layer_control, 1)
        self.layout.addWidget(self.props_stack, 2)
        self.setLayout(self.layout)

        self.connect_events()

    def connect_events(self):
        self.layer_control.list.currentItemChanged.connect(self.change_current)

    def delete(self, layer):
        self.layer_control.remove_operations_panel(layer.control_panel.operations_panel)
        self.props_stack.removeWidget(layer.control_panel)
        idx = self.layers.index(layer)
        self.layers.pop(idx)
        layer.remove()
        list_item = self.layer_control.list.takeItem(idx)
        del list_item
        return idx

    def rename_item(self, layer, new_name: str):
        idx = self.layers.index(layer)
        layer.name = new_name
        list_item = self.layer_control.list.item(idx)
        list_item.setText(str(layer))

    def reset_current(self, idx=0):
        if len(self.layers) > 0:
            new_idx = max(idx-1, 0)
            self.current_layer = self.layers[new_idx]
            self.layer_control.list.setCurrentRow(new_idx)
        else:
            self.current_layer = None

    def delete_current(self):
        if self.current_layer is None:
            return
        idx = self.delete(self.current_layer)
        self.reset_current(idx)

    def set_props_panel(self, widget):
        if self.props_stack.indexOf(widget) < 0:
            self.props_stack.addWidget(widget)
        self.props_stack.setCurrentWidget(widget)

    def change_current(self, *args):
        if len(self.layers) == 0:
            return
        idx = self.layer_control.list.currentRow()
        try:
            self.current_layer = self.layers[idx]
            control_panel = self.current_layer.control_panel
            self.set_props_panel(control_panel)
            self.layer_control.set_operations_panel(control_panel.operations_panel)
        except:
            pass

    def add_chromatin_layer(self, df, chr_colormap, parent=None, name=None):
        from .layers import ChromatinLayer
        layer = ChromatinLayer(self.canvas, df, chr_colormap)
        layer.parent = parent
        layer.name = name
        self.layers.append(layer)
        self.current_layer = layer
        self.layer_control.list.addItem(str(layer))
        self.layer_control.list.setCurrentRow(len(self.layers)-1)
        return layer
