"""
Modified CanvasControl that works with both original and abstract layers.
Automatically selects the appropriate layer implementation based on the canvas backend.
"""

from PyQt5.QtGui import QIcon
from .canvas_control import CanvasControl as OriginalCanvasControl


class CanvasControl(OriginalCanvasControl):
    """
    Extended CanvasControl that automatically uses the correct layer implementation
    based on the canvas backend (VisPy or PyVista).
    """
    
    def __init__(self, canvas):
        """Initialize control panel with backend-aware layer support."""
        super().__init__(canvas)
        
        # Detect backend type
        self.use_abstract_layers = hasattr(canvas, 'backend_name')
    
    def add_chromatin_layer(self, df, chr_colormap, parent=None, name=None, width=None, style=None):
        """Add chromatin layer using appropriate implementation."""
        if self.use_abstract_layers:
            # Use abstract layers for new backend system
            from .layers_abstract import ChromatinLayer, ChrLabelLayer
        else:
            # Use original layers for VisPy
            from .layers import ChromatinLayer, ChrLabelLayer
        
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
                    layer.name = str(parent.name)
                else:
                    layer.name = "Chromatin"
            except Exception:
                layer.name = "Chromatin"
        
        self.layers.append(layer)
        self.current_layer = layer
        
        # Store dataframe in canvas info for compatibility
        if not hasattr(self.canvas, 'info'):
            self.canvas.info = {}
        self.canvas.info['df'] = df
        
        # Add to UI with controls
        item, show_btn, rename_btn, delete_btn = self.layer_control.add_list_item(layer)
        
        # Connect button handlers
        def on_toggle_show():
            checked = show_btn.isChecked()
            layer.set_visible(checked)
            if checked:
                show_btn.setToolTip('Hide layer')
                show_btn.setIcon(QIcon(self._icon_path('eye.svg')))
            else:
                show_btn.setToolTip('Show layer')
                show_btn.setIcon(QIcon(self._icon_path('eye-off.svg')))
            # Update chromosome numbers when visibility changes
            if layer == self.current_layer and hasattr(self, '_update_chr_labels_for_current_layer'):
                self._update_chr_labels_for_current_layer()
        
        def on_rename_layer():
            self._show_rename_dialog(layer)
        
        def on_delete_layer():
            idx = self.delete(layer)
            self.reset_current(idx)
        
        show_btn.clicked.connect(on_toggle_show)
        rename_btn.clicked.connect(on_rename_layer)
        delete_btn.clicked.connect(on_delete_layer)
        
        # Set as current
        self.layer_control.list.setCurrentRow(len(self.layers)-1)
        self.canvas.set_layer_title(str(layer))
        self._update_list_item_styles()
        
        # Update chromosome labels
        self._update_chr_labels(df, chr_colormap)
        
        # Single render after all initialization
        if hasattr(self.canvas.backend, 'render'):
            self.canvas.backend.render()
        
        return layer
    
    def _update_chr_labels(self, df, chr_colormap):
        """Update chromosome number labels using appropriate layer type."""
        if self.use_abstract_layers:
            from .layers_abstract import ChrLabelLayer
        else:
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
                
                # Get font size from parent class
                font_size = getattr(self, 'chr_label_font_size', 150)
                self.chr_label_layer.draw(df, color=color, font_size=font_size)
                self.chr_label_layer.name = 'Chr labels'
            else:
                if self.chr_label_layer is not None:
                    self.chr_label_layer.remove()
                    self.chr_label_layer = None
        except Exception:
            pass