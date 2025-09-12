"""
Canvas control panel compatible with PyVista layers
"""

from .canvas_control import CanvasControl as BaseCanvasControl
from .layers_pyvista import ChromatinLayerPyVista, ChrLabelLayerPyVista


class CanvasControlPyVista(BaseCanvasControl):
    """Extended canvas control for PyVista support"""
    
    def add_chromatin_layer(self, df, chr_colormap, parent=None, name=None):
        """Add chromatin layer using PyVista renderer"""
        # Create PyVista layer
        layer = ChromatinLayerPyVista(self.canvas, df, chr_colormap)
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
        
        # Add to UI list
        item, show_btn, rename_btn, delete_btn = self.layer_control.add_list_item(layer)
        
        # Connect UI controls
        def on_toggle_show():
            checked = show_btn.isChecked()
            layer.set_visible(checked)
            # Update tooltip and icon based on state
            if checked:
                show_btn.setToolTip('Hide layer')
                from PyQt5.QtGui import QIcon
                show_btn.setIcon(QIcon(self._icon_path('eye.svg')))
            else:
                show_btn.setToolTip('Show layer')
                from PyQt5.QtGui import QIcon
                show_btn.setIcon(QIcon(self._icon_path('eye-off.svg')))
                
        def on_rename_layer():
            self._show_rename_dialog(layer)
            
        def on_delete_layer():
            idx = self.delete(layer)
            self.reset_current(idx)
            
        show_btn.clicked.connect(on_toggle_show)
        rename_btn.clicked.connect(on_rename_layer)
        delete_btn.clicked.connect(on_delete_layer)
        
        # Select the new layer
        self.layer_control.list.setCurrentRow(len(self.layers)-1)
        self.canvas.set_layer_title(str(layer))
        self._update_list_item_styles()
        
        # Update chromosome labels if needed
        self._update_chr_numbers_pyvista(df, chr_colormap)
        
        return layer
        
    def _update_chr_numbers_pyvista(self, df, chr_colormap):
        """Update chromosome number labels using PyVista"""
        try:
            if self.chr_numbers_enabled and int(df['chrom'].nunique()) > 1:
                if self.chr_number_layer is None:
                    self.chr_number_layer = ChrLabelLayerPyVista(self.canvas)
                else:
                    self.chr_number_layer.remove()
                    
                if self.chr_number_color_mode == 'follow':
                    color = chr_colormap
                elif self.chr_number_color_mode == 'white':
                    color = '#FFFFFF'
                else:
                    color = '#000000'
                    
                self.chr_number_layer.draw(df, color=color)
                self.chr_number_layer.name = 'Chr numbers'
            else:
                if self.chr_number_layer is not None:
                    self.chr_number_layer.remove()
                    self.chr_number_layer = None
        except Exception as e:
            print(f"Error updating chr numbers: {e}")
            
    def set_chr_number_color_mode(self, mode: str):
        """Override to use PyVista update method"""
        self.chr_number_color_mode = mode
        try:
            layer = self.current_layer
            if layer is not None and hasattr(layer, 'df'):
                df = layer.df
                cmap = layer.cache_props.get('chr_colormap', {}) if hasattr(layer, 'cache_props') else {}
                self._update_chr_numbers_pyvista(df, cmap)
        except Exception:
            pass
            
    def set_chr_numbers_enabled(self, enabled: bool):
        """Override to use PyVista update method"""
        self.chr_numbers_enabled = bool(enabled)
        try:
            layer = self.current_layer
            if layer is not None and hasattr(layer, 'df'):
                df = layer.df
                cmap = layer.cache_props.get('chr_colormap', {}) if hasattr(layer, 'cache_props') else {}
                self._update_chr_numbers_pyvista(df, cmap)
        except Exception:
            pass