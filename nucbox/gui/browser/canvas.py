from turtle import width
from vispy import scene
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QStackedWidget)

from nucbox.gui.browser.layer_panel import LayerPanel


class Canvas(scene.SceneCanvas):

    def __init__(self):
        scene.SceneCanvas.__init__(self, keys=None)
        self.size = 800, 600
        self.unfreeze()

        self.view = self.central_widget.add_view()
        self.view.bgcolor = "#000000"
        self.view.camera = 'turntable'
        self.view.camera.distance = 50

        # Add a 3D axis to keep us oriented
        self.axis = scene.visuals.XYZAxis(parent=self.view.scene)
        self.axis.visible = False

        self.control_panel = CanvasControl(self)

        self.freeze()


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
        self.layer_control.del_btn.clicked.connect(self.delete_current)
        self.layer_control.list.currentItemChanged.connect(self.change_current)

    def delete_current(self):
        if self.current_layer is None:
            return
        self.props_stack.removeWidget(self.current_layer.control_panel)
        idx = self.layers.index(self.current_layer)
        self.layers.pop(idx)
        self.current_layer.remove()
        list_item = self.layer_control.list.takeItem(idx)
        del list_item
        if len(self.layers) > 0:
            new_idx = max(idx-1, 0)
            self.current_layer = self.layers[new_idx]
            self.layer_control.list.setCurrentRow(new_idx)
        else:
            self.current_layer = None

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
        except:
            pass

    def add_chromatin_layer(self, df, chr_colormap):
        from .layers import ChromatinLayer
        layer = ChromatinLayer(self.canvas, df, chr_colormap)
        self.layers.append(layer)
        self.current_layer = layer
        self.layer_control.list.addItem(str(layer))
        self.layer_control.list.setCurrentRow(len(self.layers)-1)
