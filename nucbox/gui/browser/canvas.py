"""
Canvas implementation using the PyVista rendering backend (no abstraction layer).
Maintains the same public interface expected by the rest of the app.
"""

from .canvas_control import CanvasControl
from .pyvista_backend import PyVistaBackend


class Canvas:
    """
    Drop-in replacement for the original Canvas class.
    Uses PyVista backend only.
    """
    
    def __init__(self):
        """
        Initialize Canvas (PyVista-only backend).
        """
        # Backend
        self.backend_name = 'pyvista'
        self.backend = PyVistaBackend()
        self.native = self.backend.get_native_widget()
        
        # Size
        self.size = 800, 600
        if hasattr(self.native, 'resize'):
            self.native.resize(800, 600)
        
        # Background and axes
        self.backend.set_background_color("#000000")
        self._axis_handle = self.backend.add_axes(visible=False)
        self._axis_visible = False
        
        # Camera compatibility object
        self.camera = type('Camera', (), {
            'distance': 50,
            'reset': self.backend.reset_camera
        })
        
        # View compatibility object
        self.view = type('View', (), {})
        self.view.bgcolor = "#000000"
        self.view.camera = self.camera
        self.view.scene = self
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
        
        # Border color property exposed on view
        self._border_color = None
        def set_border_color(color):
            self.border_color = color
        self.view.border_color = property(lambda: self._border_color, set_border_color)
        
        # Axis proxy with .visible property
        class _AxisProxy:
            def __init__(self, canvas):
                self._c = canvas
            @property
            def visible(self):
                return self._c._axis_visible
            @visible.setter
            def visible(self, value):
                self._c._axis_visible = bool(value)
                if self._c._axis_handle:
                    self._c.backend.set_axes_visibility(self._c._axis_handle, self._c._axis_visible)
        self.axis = _AxisProxy(self)
        
        # Overlay label (title)
        self.layer_title = type('LayerTitle', (), {
            'text': '',
            'font_size': 5,
            'color': '#FFFFFF',
            'pos': (10, 10)
        })
        self._layer_title_handle = None
        self._label_margin = 10
        self._label_position = "Top Left"
        
        # Control panel
        self.control_panel = CanvasControl(self)
        
        # Connect double-click to reset camera (uses Qt native event)
        self.backend.on_double_click_callback = self._on_double_click
        
        # Misc
        self.info = {}
        self.frozen = False
    
    def create_native(self):
        """Create native widget - compatibility method."""
        # Already created in parent __init__
        pass
    
    def _on_double_click(self):
        """Reset camera to default position on double-click."""
        self.backend.reset_camera()
    
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
    
    # ----- Title overlay -----
    def update_layer_title(self, **kwargs):
        if self._layer_title_handle:
            self.backend.update_text_overlay(self._layer_title_handle, force_update=True, **kwargs)

    def set_layer_title(self, text: str):
        """Set layer title text."""
        if text is None:
            text = ''
        if self._layer_title_handle is None and text:
            self._layer_title_handle = self.backend.add_text_overlay(
                text,
                position=self._label_position.lower().replace(' ', '-'),
                color='#CD18FC',
                font_size=20.0
            )
        elif self._layer_title_handle:
            self.backend.update_text_overlay(self._layer_title_handle, text=text)
        self.layer_title.text = text if text else ''
    
    def set_layer_title_font_size(self, size: float):
        """Set layer title font size."""
        if self._layer_title_handle:
            self.backend.update_text_overlay(self._layer_title_handle, font_size=size)
        self.layer_title.font_size = size
    
    def set_layer_title_color(self, color_name: str):
        """Set layer title color."""
        # Backend update
        color_map = {
            "White": "#FFFFFF", "Black": "#000000", "Red": "#FF0000", "Green": "#008000",
            "Blue": "#0000FF", "Yellow": "#FFFF00", "Cyan": "#00FFFF", "Magenta": "#FF00FF",
            "Orange": "#FFA500", "Purple": "#800080", "Brown": "#A52A2A", "Pink": "#FFC0CB",
            "Gray": "#808080", "Olive": "#808000", "Navy": "#000080", "Lime": "#00FF00",
            "Maroon": "#800000", "Teal": "#008080", "Silver": "#C0C0C0", "Gold": "#FFD700"
        }
        hex_color = color_map.get(color_name, "#FFFFFF")
        if self._layer_title_handle:
            self.backend.update_text_overlay(self._layer_title_handle, color=hex_color)
        # Internal state
        color_map = {
            "White": "#FFFFFF", "Black": "#000000", "Red": "#FF0000", "Green": "#008000",
            "Blue": "#0000FF", "Yellow": "#FFFF00", "Cyan": "#00FFFF", "Magenta": "#FF00FF",
            "Orange": "#FFA500", "Purple": "#800080", "Brown": "#A52A2A", "Pink": "#FFC0CB",
            "Gray": "#808080", "Olive": "#808000", "Navy": "#000080", "Lime": "#00FF00",
            "Maroon": "#800000", "Teal": "#008080", "Silver": "#C0C0C0", "Gold": "#FFD700"
        }
        self.layer_title.color = color_map.get(color_name, "#FFFFFF")

    def set_layer_title_color_hex(self, hex_color: str):
        """Set layer title color using hex color code."""
        if self._layer_title_handle:
            self.backend.update_text_overlay(self._layer_title_handle, color=hex_color)
        self.layer_title.color = hex_color
    
    def set_layer_title_position(self, position: str):
        """Set layer title position."""
        self._label_position = position
        if self._layer_title_handle:
            pos_key = position.lower().replace(' ', '-')
            self.backend.update_text_overlay(self._layer_title_handle, position=pos_key)
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

    # ----- Background / border / camera -----
    def set_background_color(self, color_name: str):
        """Set background color by name (compatibility helper)."""
        bg_color_map = {
            "Black": "#000000",
            "White": "#FFFFFF",
            "Light Gray": "#C0C0C0",
        }
        hex_color = bg_color_map.get(color_name, "#000000")
        self.backend.set_background_color(hex_color)
        if hasattr(self, 'view'):
            self.view.bgcolor = hex_color

    @property
    def border_color(self):
        return self._border_color

    @border_color.setter
    def border_color(self, color):
        self._border_color = color
        color_str = getattr(color, 'hex', None) if hasattr(color, 'hex') else None
        if color_str is None:
            color_str = str(color)
        self.backend.set_border_color(color_str)

    @property
    def camera_distance(self):
        return self.camera.distance

    @camera_distance.setter
    def camera_distance(self, value):
        self.camera.distance = value
        self.backend.set_camera_distance(value)