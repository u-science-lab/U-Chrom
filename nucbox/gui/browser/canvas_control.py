from PyQt5.QtWidgets import (QListWidget, QWidget, QLabel, QHBoxLayout, QVBoxLayout, QStackedWidget, QListWidgetItem, QCheckBox, QPushButton, QLineEdit, QDialog)


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

    def add_list_item(self, layer):
        item = QListWidgetItem()
        row = QWidget()
        
        # Main layout - vertical to accommodate two rows
        main_layout = QVBoxLayout()
        main_layout.setSpacing(2)
        main_layout.setContentsMargins(4, 2, 4, 2)
        
        # Top row: name and show/lock controls
        top_row = QHBoxLayout()
        top_row.setSpacing(4)
        
        name_label = QLabel(str(layer))
        name_label.setObjectName('name_label')
        show_cb = QCheckBox()
        show_cb.setChecked(True)
        lock_cb = QCheckBox()
        lock_cb.setChecked(False)
        show_label = QLabel('Show')
        lock_label = QLabel('Lock')
        
        top_row.addWidget(name_label, 1)
        top_row.addWidget(show_label)
        top_row.addWidget(show_cb)
        top_row.addSpacing(6)
        top_row.addWidget(lock_label)
        top_row.addWidget(lock_cb)
        
        # Bottom row: action buttons
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(2)
        
        rename_btn = QPushButton("Rename")
        rename_btn.setMaximumHeight(20)
        rename_btn.setObjectName('rename_btn')
        
        delete_btn = QPushButton("Delete")
        delete_btn.setMaximumHeight(20)
        delete_btn.setObjectName('delete_btn')
        
        subset_btn = QPushButton("Subset")
        subset_btn.setMaximumHeight(20)
        subset_btn.setObjectName('subset_btn')
        
        bottom_row.addWidget(rename_btn)
        bottom_row.addWidget(delete_btn)
        bottom_row.addWidget(subset_btn)
        
        main_layout.addLayout(top_row)
        main_layout.addLayout(bottom_row)
        
        row.setLayout(main_layout)
        item.setSizeHint(row.sizeHint())
        self.list.addItem(item)
        self.list.setItemWidget(item, row)
        
        return item, show_cb, lock_cb, rename_btn, delete_btn, subset_btn

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
        w = self.layer_control.list.itemWidget(list_item)
        if w is not None:
            lbl = w.findChild(QLabel, 'name_label')
            if lbl is not None:
                lbl.setText(str(layer))
        if self.current_layer is layer:
            self.canvas.set_layer_title(str(layer))

    def reset_current(self, idx=0):
        if len(self.layers) > 0:
            new_idx = max(idx-1, 0)
            self.current_layer = self.layers[new_idx]
            self.layer_control.list.setCurrentRow(new_idx)
            self.canvas.set_layer_title(str(self.current_layer))
        else:
            self.current_layer = None
            self.canvas.set_layer_title('')

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
            self.canvas.set_layer_title(str(self.current_layer))
        except:
            pass

    def add_chromatin_layer(self, df, chr_colormap, parent=None, name=None):
        from .layers import ChromatinLayer
        layer = ChromatinLayer(self.canvas, df, chr_colormap)
        layer.parent = parent
        layer.name = name
        self.layers.append(layer)
        self.current_layer = layer
        # custom list item with visibility, lock, and action buttons
        item, show_cb, lock_cb, rename_btn, delete_btn, subset_btn = self.layer_control.add_list_item(layer)
        
        def on_toggle_show(val):
            visible = bool(val)
            layer.set_visible(visible)
        def on_toggle_lock(val):
            locked = bool(val)
            layer.set_locked(locked)
            # disable its control panel when locked
            layer.control_panel.setDisabled(locked)
        def on_rename_layer():
            self._show_rename_dialog(layer)
        def on_delete_layer():
            idx = self.delete(layer)
            self.reset_current(idx)
        def on_subset_layer():
            self._show_subset_dialog(layer)
            
        show_cb.toggled.connect(on_toggle_show)
        lock_cb.toggled.connect(on_toggle_lock)
        rename_btn.clicked.connect(on_rename_layer)
        delete_btn.clicked.connect(on_delete_layer)
        subset_btn.clicked.connect(on_subset_layer)
        self.layer_control.list.setCurrentRow(len(self.layers)-1)
        self.canvas.set_layer_title(str(layer))
        return layer

    def _show_rename_dialog(self, layer):
        # Create simple rename dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Rename Layer")
        dialog.setModal(True)
        dialog.resize(300, 100)
        
        layout = QVBoxLayout()
        layout.addWidget(QLabel("New name:"))
        
        name_input = QLineEdit(str(layer))
        layout.addWidget(name_input)
        
        # Buttons
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        
        def on_ok():
            new_name = name_input.text().strip()
            if new_name:
                self.rename_item(layer, new_name)
            dialog.accept()
        
        ok_btn.clicked.connect(on_ok)
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        dialog.setLayout(layout)
        dialog.exec_()

    def _show_subset_dialog(self, layer):
        # Show the layer's subset window directly
        if hasattr(layer, 'control_panel') and hasattr(layer.control_panel, 'subset_window'):
            layer.control_panel.subset_window.show()
        else:
            print(f"Layer {layer} does not support subset creation")
