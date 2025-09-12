"""
New Canvas implementation that uses the abstract rendering backend.
This provides a drop-in replacement for the original Canvas class with PyVista support.
"""

from .canvas_abstract import AbstractCanvas
from .canvas_control_new import CanvasControl


class Canvas(AbstractCanvas):
    """
    Drop-in replacement for the original Canvas class.
    Uses PyVista by default for better performance but can switch to VisPy if needed.
    """
    
    def __init__(self, backend='pyvista'):
        """
        Initialize Canvas with specified backend.
        
        Args:
            backend: 'pyvista' (default) or 'vispy'
                    PyVista provides better performance and rendering quality
        """
        # Initialize with chosen backend
        super().__init__(backend=backend)
        
        # Set default size
        self.size = 800, 600
        if hasattr(self.native, 'resize'):
            self.native.resize(800, 600)
        
        # Initialize view properties for compatibility
        self.view = type('View', (), {})
        self.view.bgcolor = "#000000"
        self.view.camera = self.camera
        self.view.scene = self
        
        # Add view.events for compatibility
        self.view.events = type('ViewEvents', (), {
            'mouse_press': type('Event', (), {
                'connect': lambda f: self.backend.connect_mouse_events(on_click=f),
                'callbacks': []
            }),
            'mouse_move': type('Event', (), {
                'connect': lambda f: self.backend.connect_mouse_events(on_move=f),
                'callbacks': []
            }),
            'mouse_wheel': type('Event', (), {
                'connect': lambda f: self.backend.connect_mouse_events(on_wheel=f),
                'callbacks': []
            })
        })
        
        # Border color setter for view
        def set_border_color(color):
            self.border_color = color
        self.view.border_color = property(lambda: self._border_color, set_border_color)
        
        # Layer title setup
        self.layer_title = type('LayerTitle', (), {
            'text': '',
            'font_size': 5,
            'color': '#FFFFFF',
            'pos': (10, 10)
        })
        
        # Initialize control panel
        self.control_panel = CanvasControl(self)
        
        # Info dict for compatibility
        self.info = {}
        
        # Freeze/unfreeze methods for compatibility
        self.frozen = False
    
    def create_native(self):
        """Create native widget - compatibility method."""
        # Already created in parent __init__
        pass
    
    def freeze(self):
        """Freeze canvas updates - compatibility method."""
        self.frozen = True
    
    def unfreeze(self):
        """Unfreeze canvas updates - compatibility method."""
        self.frozen = False
        self.render()
    
    def update(self):
        """Update canvas."""
        if not self.frozen:
            self.render()
    
    # Override layer title methods to update internal state
    def set_layer_title(self, text: str):
        """Set layer title text."""
        super().set_layer_title(text)
        self.layer_title.text = text if text else ''
    
    def set_layer_title_font_size(self, size: float):
        """Set layer title font size."""
        super().set_layer_title_font_size(size)
        self.layer_title.font_size = size
    
    def set_layer_title_color(self, color_name: str):
        """Set layer title color."""
        super().set_layer_title_color(color_name)
        # Update internal state
        color_map = {
            "White": "#FFFFFF", "Black": "#000000", "Red": "#FF0000", "Green": "#008000",
            "Blue": "#0000FF", "Yellow": "#FFFF00", "Cyan": "#00FFFF", "Magenta": "#FF00FF",
            "Orange": "#FFA500", "Purple": "#800080", "Brown": "#A52A2A", "Pink": "#FFC0CB",
            "Gray": "#808080", "Olive": "#808000", "Navy": "#000080", "Lime": "#00FF00",
            "Maroon": "#800000", "Teal": "#008080", "Silver": "#C0C0C0", "Gold": "#FFD700"
        }
        self.layer_title.color = color_map.get(color_name, "#FFFFFF")
    
    def set_layer_title_position(self, position: str):
        """Set layer title position."""
        super().set_layer_title_position(position)
        # Could update layer_title.pos here if needed
    
    def _fit_label_within_canvas(self, preferred_size: float = None):
        """Compatibility method for fitting label within canvas."""
        # This is handled by the backend now
        pass
    
    def _update_text_anchors(self):
        """Compatibility method for updating text anchors."""
        # Handled by backend
        pass
    
    def _update_text_position(self):
        """Compatibility method for updating text position."""
        # Handled by backend
        pass
    
    def _on_resize(self, event):
        """Handle resize event - compatibility method."""
        # Handled internally by backend
        pass