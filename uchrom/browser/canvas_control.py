from PyQt5.QtWidgets import (QListWidget, QWidget, QLabel, QHBoxLayout, QVBoxLayout, QStackedWidget, QListWidgetItem, QCheckBox, QPushButton, QLineEdit, QDialog, QToolButton)
from PyQt5.QtCore import Qt, QSize, QPoint
from PyQt5.QtGui import QIcon


class LayerPanel(QWidget):

    def __init__(self, parent=None):
        super(LayerPanel, self).__init__(parent)

        self.list = QListWidget()
        # Style: items blend with background; only selected item shows subtle highlight
        self.list.setStyleSheet(
            "QListWidget::item{background:transparent;border:none;padding:4px;}"
            "QListWidget::item:selected{background:rgba(255,255,255,0.08);}"
            "QListWidget::item:hover{background:rgba(255,255,255,0.04);}" )
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setMinimumWidth(260)

        title_layout = QVBoxLayout()
        title_layout.addWidget(QLabel("<h2>Layers</h2>"))

        self.operation_stack = QStackedWidget()

        hbox = QHBoxLayout()
        hbox.addWidget(self.list)
        hbox.addWidget(self.operation_stack)
        # Give the list more space than the right-side operations panel
        hbox.setStretch(0, 3)
        hbox.setStretch(1, 2)

        vbox = QVBoxLayout()
        vbox.addLayout(title_layout)
        vbox.addLayout(hbox)

        self.setLayout(vbox)

    def _icon_path(self, name: str) -> str:
        # Resolve icon path relative to this file
        try:
            import os, os.path as osp
            here = osp.dirname(osp.abspath(__file__))
            return osp.join(here, 'icons', name)
        except Exception:
            return name

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
        # Ensure label shrinks first to keep action buttons visible on narrow widths
        from PyQt5.QtWidgets import QSizePolicy
        name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        name_label.setMinimumWidth(10)
        name_label.setToolTip(str(layer))

        # Show/Hide button with icon
        show_btn = QToolButton()
        show_btn.setCheckable(True)
        show_btn.setChecked(True)
        show_btn.setIcon(QIcon(self._icon_path('eye.svg')))
        show_btn.setIconSize(QSize(16, 16))
        show_btn.setFixedSize(24, 24)
        show_btn.setAutoRaise(True)
        show_btn.setToolTip('Hide layer')
        show_btn.setCursor(Qt.PointingHandCursor)
        show_btn.setStyleSheet("QToolButton{border:none;background:transparent;} QToolButton:hover{background:transparent;} QToolButton:checked{background:transparent;} QToolButton:pressed{background:transparent;} QToolTip{font-size:12px;color:#fff;background:#222;border:1px solid #555;}")
        
        top_row.addWidget(name_label, 1)
        top_row.addWidget(show_btn)
        
        rename_btn = QToolButton()
        rename_btn.setIcon(QIcon(self._icon_path('rename.svg')))
        rename_btn.setToolTip('Rename layer')
        rename_btn.setAutoRaise(True)
        rename_btn.setCursor(Qt.PointingHandCursor)
        rename_btn.setFixedSize(24, 24)
        rename_btn.setIconSize(QSize(16, 16))
        rename_btn.setStyleSheet("QToolButton{border:none;background:transparent;} QToolButton:hover{background:transparent;} QToolButton:pressed{background:transparent;} QToolTip{font-size:12px;color:#fff;background:#222;border:1px solid #555;}")
        rename_btn.setObjectName('rename_btn')
        
        delete_btn = QToolButton()
        delete_btn.setIcon(QIcon(self._icon_path('delete.svg')))
        delete_btn.setToolTip('Delete layer')
        delete_btn.setAutoRaise(True)
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setFixedSize(24, 24)
        delete_btn.setIconSize(QSize(16, 16))
        delete_btn.setStyleSheet("QToolButton{border:none;background:transparent;} QToolButton:hover{background:transparent;} QToolButton:pressed{background:transparent;} QToolTip{font-size:12px;color:#fff;background:#222;border:1px solid #555;}")
        delete_btn.setObjectName('delete_btn')
        
        top_row.addSpacing(8)
        top_row.addWidget(rename_btn)
        top_row.addWidget(delete_btn)
        # subset action moved to Region Management; removed from layer row
        
        main_layout.addLayout(top_row)
        
        row.setLayout(main_layout)
        # Ensure row height is enough to display icons without clipping
        item.setSizeHint(QSize(row.sizeHint().width(), max(36, row.sizeHint().height())))
        self.list.addItem(item)
        self.list.setItemWidget(item, row)
        
        return item, show_btn, rename_btn, delete_btn

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
        # Chromosome label overlay settings
        self.chr_label_layer = None
        self.chr_label_color_mode = 'follow'  # 'follow' | 'white' | 'black'
        self.chr_labels_enabled = True
        self.chr_label_font_size = 150  # Default font size

        self.layer_control = LayerPanel()
        self.props_stack = QStackedWidget()
        self.layout: QVBoxLayout = QVBoxLayout()
        self.layout.addWidget(self.layer_control, 1)
        self.layout.addWidget(self.props_stack, 2)
        self.setLayout(self.layout)

        self.connect_events()

        # Context menu for layer list (useful when action buttons are partially hidden)
        try:
            self.layer_control.list.setContextMenuPolicy(Qt.CustomContextMenu)
            self.layer_control.list.customContextMenuRequested.connect(self._open_layer_context_menu)
        except Exception:
            pass

    def _icon_path(self, name: str) -> str:
        # Resolve icon path inside package resources
        # Icons expected at uchrom/browser/icons/
        try:
            import os, os.path as osp
            here = osp.dirname(osp.abspath(__file__))
            return osp.join(here, 'icons', name)
        except Exception:
            return name

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
        
        # Remove chromosome labels that are tied to the current layer context
        # Safer behavior: whenever a layer is deleted, remove existing chr labels
        # and let subsequent current-layer selection decide whether to rebuild
        try:
            if self.chr_label_layer is not None:
                self.chr_label_layer.remove()
                self.chr_label_layer = None
        except Exception:
            pass
        
        # Force render to ensure deletion is visible
        if hasattr(self.canvas, 'backend') and hasattr(self.canvas.backend, 'render'):
            self.canvas.backend.render()
        elif hasattr(self.canvas, 'update'):
            self.canvas.update()
        
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

    def _open_layer_context_menu(self, pos: QPoint):
        try:
            from PyQt5.QtWidgets import QMenu
            index = self.layer_control.list.indexAt(pos)
            row = index.row()
            if row < 0 or row >= len(self.layers):
                return
            layer = self.layers[row]
            menu = QMenu(self)
            act_toggle = menu.addAction('Hide layer' if layer.is_visible else 'Show layer')
            act_rename = menu.addAction('Rename...')
            act_delete = menu.addAction('Delete')
            action = menu.exec_(self.layer_control.list.mapToGlobal(pos))
            if action == act_toggle:
                layer.set_visible(not layer.is_visible)
                # sync UI selection
                if row == self.layer_control.list.currentRow():
                    self._update_chr_labels_for_current_layer()
            elif action == act_rename:
                self._show_rename_dialog(layer)
            elif action == act_delete:
                idx = self.delete(layer)
                # keep selection reasonable
                self.reset_current(idx)
        except Exception:
            pass

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
            # Sync UI controls with actual rendering state
            if hasattr(control_panel, 'sync_ui_from_cache'):
                control_panel.sync_ui_from_cache()
            self.canvas.set_layer_title(str(self.current_layer))
            self._update_list_item_styles()
            # Update chromosome numbers for the newly selected layer
            self._update_chr_labels_for_current_layer()
        except:
            pass

    def add_chromatin_layer(self, df, chr_colormap, parent=None, name=None, width=None, style=None):
        from .layers import ChromatinLayer
        from .layers import ChrLabelLayer
        
        # Use provided width/style or defaults
        if width is None:
            width = parent.cache_props.get('width', 1.0) if parent and hasattr(parent, 'cache_props') else 1.0
        if style is None:
            style = parent.cache_props.get('style', 'line') if parent and hasattr(parent, 'cache_props') else 'line'
        
        layer = ChromatinLayer(self.canvas, df, chr_colormap, width=width, style=style)
        layer.parent = parent
        if name is not None:
            layer.name = name
        else:
            # Derive default name
            try:
                if parent is not None and hasattr(df, 'shape'):
                    # Could be a region or chromosome subset – parent naming already indicates
                    layer.name = str(parent.name)
                else:
                    layer.name = "Chromatin"
            except Exception:
                layer.name = "Chromatin"
        self.layers.append(layer)
        self.current_layer = layer
        # custom list item with visibility and action buttons
        item, show_btn, rename_btn, delete_btn = self.layer_control.add_list_item(layer)
        
        def on_toggle_show():
            checked = show_btn.isChecked()
            layer.set_visible(checked)
            # update tooltip and icon based on state
            if checked:
                show_btn.setToolTip('Hide layer')
                show_btn.setIcon(QIcon(self._icon_path('eye.svg')))
            else:
                show_btn.setToolTip('Show layer')
                show_btn.setIcon(QIcon(self._icon_path('eye-off.svg')))
            # Update chromosome numbers when visibility changes
            if layer == self.current_layer:
                self._update_chr_labels_for_current_layer()
        def on_rename_layer():
            self._show_rename_dialog(layer)
        def on_delete_layer():
            idx = self.delete(layer)
            self.reset_current(idx)
        show_btn.clicked.connect(on_toggle_show)
        rename_btn.clicked.connect(on_rename_layer)
        delete_btn.clicked.connect(on_delete_layer)
        # hide subset for multi-chromosome layers (e.g., initial import of all chromosomes)
        # no per-layer subset button; region management handles subsets
        self.layer_control.list.setCurrentRow(len(self.layers)-1)
        self.canvas.set_layer_title(str(layer))
        self._update_list_item_styles()

        # Update chromosome number labels overlay for the new layer
        self._update_chr_labels_for_current_layer()
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

    def _update_list_item_styles(self):
        # Visually distinguish the selected layer
        try:
            current = self.layer_control.list.currentRow()
            for i in range(len(self.layers)):
                item = self.layer_control.list.item(i)
                if item is None:
                    continue
                w = self.layer_control.list.itemWidget(item)
                if w is None:
                    continue
                if i == current:
                    w.setStyleSheet("background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.25); border-radius: 6px;")
                else:
                    w.setStyleSheet("background: transparent; border: 1px solid rgba(255,255,255,0.08); border-radius: 6px;")
        except Exception:
            pass

    # ---------- Chromosome labels overlay ----------
    def _update_chr_labels(self, df, chr_colormap):
        from .layers import ChrLabelLayer
        try:
            # Check if current layer is visible
            layer_visible = (self.current_layer and 
                           hasattr(self.current_layer, 'is_visible') and 
                           self.current_layer.is_visible)
            
            if self.chr_labels_enabled and layer_visible and int(df['chrom'].nunique()) > 1:
                if self.chr_label_layer is None:
                    self.chr_label_layer = ChrLabelLayer(self.canvas)
                else:
                    self.chr_label_layer.remove()
                if self.chr_label_color_mode == 'follow':
                    color = chr_colormap
                elif self.chr_label_color_mode == 'white':
                    color = '#FFFFFF'
                else:
                    color = '#000000'
                self.chr_label_layer.draw(df, color=color, font_size=self.chr_label_font_size)
                self.chr_label_layer.name = 'Chr labels'
            else:
                if self.chr_label_layer is not None:
                    self.chr_label_layer.remove()
                    self.chr_label_layer = None
        except Exception:
            pass

    def set_chr_label_color_mode(self, mode: str):
        self.chr_label_color_mode = mode
        try:
            layer = self.current_layer
            if layer is not None and hasattr(layer, 'df'):
                df = layer.df
                cmap = layer.cache_props.get('chr_colormap', {}) if hasattr(layer, 'cache_props') else {}
                self._update_chr_labels(df, cmap)
        except Exception:
            pass

    def set_chr_labels_enabled(self, enabled: bool):
        self.chr_labels_enabled = bool(enabled)
        try:
            layer = self.current_layer
            if layer is not None and hasattr(layer, 'df'):
                df = layer.df
                cmap = layer.cache_props.get('chr_colormap', {}) if hasattr(layer, 'cache_props') else {}
                self._update_chr_labels(df, cmap)
        except Exception:
            pass
    
    def set_chr_label_font_size(self, font_size: int):
        self.chr_label_font_size = font_size
        try:
            layer = self.current_layer
            if layer is not None and hasattr(layer, 'df'):
                df = layer.df
                cmap = layer.cache_props.get('chr_colormap', {}) if hasattr(layer, 'cache_props') else {}
                self._update_chr_labels(df, cmap)
        except Exception:
            pass
    
    def _update_chr_labels_for_current_layer(self):
        """Update chromosome labels based on the current layer's data and visibility."""
        try:
            # Only show chromosome labels if:
            # 1. Current layer exists and has data
            # 2. Current layer is visible
            # 3. Chromosome labels are enabled
            if (self.current_layer is not None and 
                hasattr(self.current_layer, 'df') and 
                hasattr(self.current_layer, 'is_visible') and 
                self.current_layer.is_visible and
                self.chr_labels_enabled):
                df = self.current_layer.df
                cmap = self.current_layer.cache_props.get('chr_colormap', {}) if hasattr(self.current_layer, 'cache_props') else {}
                self._update_chr_labels(df, cmap)
            else:
                # Layer is hidden or no data, remove chromosome numbers
                if self.chr_label_layer is not None:
                    self.chr_label_layer.remove()
                    self.chr_label_layer = None
        except Exception:
            pass
