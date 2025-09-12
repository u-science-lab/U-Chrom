"""
Abstract Canvas implementation that can use different rendering backends.
This maintains compatibility with the existing control interface while allowing
backend switching between VisPy and PyVista.
"""

import os
from PyQt5.QtCore import pyqtSignal, QObject

from .rendering_backend import RenderingBackend
from .vispy_backend import VisPyBackend
from .pyvista_backend import PyVistaBackend


class AbstractCanvas(QObject):
    """
    Canvas abstraction that maintains the same interface as the original Canvas
    but can use different rendering backends.
    """
    
    # Signal for backend changes
    backend_changed = pyqtSignal(str)
    
    def __init__(self, backend='pyvista'):
        """
        Initialize the canvas with specified backend.
        
        Args:
            backend: 'vispy' or 'pyvista' (default: 'pyvista' for better performance)
        """
        super().__init__()
        
        # Select and initialize backend
        self.backend_name = backend
        if backend == 'vispy':
            self.backend = VisPyBackend()
        elif backend == 'pyvista':
            self.backend = PyVistaBackend()
        else:
            # Default to PyVista for better performance
            self.backend = PyVistaBackend()
            self.backend_name = 'pyvista'
        
        # Get native widget
        self.native = self.backend.get_native_widget()
        
        # Initialize properties to match original Canvas
        self.size = 800, 600
        self.view = self  # Compatibility: self acts as view
        
        # Axes handle
        self.axis = None
        self._axis_visible = False
        
        # Layer title (overlay text)
        self.layer_title = None
        self._layer_title_handle = None
        self._label_margin = 10
        self._label_position = "Top Left"
        
        # Set initial background
        self.backend.set_background_color("#000000")
        
        # Initialize axes (hidden by default)
        self.axis = self.backend.add_axes(visible=False)
        
        # Camera compatibility
        self.camera = type('Camera', (), {
            'distance': 50,
            'reset': self.backend.reset_camera
        })
        
        # Events compatibility
        self.events = type('Events', (), {
            'mouse_press': type('Event', (), {'connect': lambda f: self.backend.connect_mouse_events(on_click=f)}),
            'mouse_move': type('Event', (), {'connect': lambda f: self.backend.connect_mouse_events(on_move=f)}),
            'mouse_wheel': type('Event', (), {'connect': lambda f: self.backend.connect_mouse_events(on_wheel=f)}),
            'resize': type('Event', (), {'connect': lambda f: None})  # Handled internally
        })
        
        # Scene compatibility
        self.scene = self
        
        # Border color property
        self._border_color = None
    
    def switch_backend(self, backend_name: str):
        """
        Switch to a different rendering backend.
        
        Args:
            backend_name: 'vispy' or 'pyvista'
        """
        if backend_name == self.backend_name:
            return
        
        # Save current camera state
        camera_state = self.backend.get_camera_state()
        
        # Save current scene objects (would need more complex state transfer for full scenes)
        # For now, this is a simplified version
        
        # Clean up old backend
        old_native = self.native
        
        # Create new backend
        if backend_name == 'vispy':
            self.backend = VisPyBackend()
        elif backend_name == 'pyvista':
            self.backend = PyVistaBackend()
        else:
            return
        
        self.backend_name = backend_name
        self.native = self.backend.get_native_widget()
        
        # Restore camera state
        self.backend.set_camera_state(camera_state)
        
        # Restore axes visibility
        if self._axis_visible:
            self.axis = self.backend.add_axes(visible=True)
        
        # Emit signal
        self.backend_changed.emit(backend_name)
        
        # Note: In production, you'd need to handle widget replacement in the parent container
    
    def create_native(self):
        """Create native widget - compatibility method."""
        # Already created in __init__
        pass
    
    def set_layer_title(self, text: str):
        """Set the layer title overlay text."""
        if text is None:
            text = ''
        
        if self._layer_title_handle is None and text:
            # Create overlay
            self._layer_title_handle = self.backend.add_text_overlay(
                text, 
                position=self._label_position.lower().replace(' ', '-'),
                color='#FFFFFF',
                font_size=12
            )
        elif self._layer_title_handle:
            # Update existing overlay
            self.backend.update_text_overlay(self._layer_title_handle, text=text)
    
    def set_layer_title_font_size(self, size: float):
        """Set layer title font size."""
        if self._layer_title_handle:
            self.backend.update_text_overlay(self._layer_title_handle, font_size=int(size))
    
    def set_layer_title_position(self, position: str):
        """Set layer title position."""
        self._label_position = position
        if self._layer_title_handle:
            pos_key = position.lower().replace(' ', '-')
            self.backend.update_text_overlay(self._layer_title_handle, position=pos_key)
    
    def set_layer_title_color(self, color_name: str):
        """Set layer title color."""
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
    
    def set_background_color(self, color_name: str):
        """Set background color."""
        bg_color_map = {
            "Black": "#000000",
            "White": "#FFFFFF",
            "Light Gray": "#C0C0C0",
        }
        hex_color = bg_color_map.get(color_name, "#000000")
        self.backend.set_background_color(hex_color)
        
        # Update view bgcolor for compatibility
        if hasattr(self, 'view'):
            self.view.bgcolor = hex_color
    
    @property
    def border_color(self):
        """Get border color."""
        return self._border_color
    
    @border_color.setter
    def border_color(self, color):
        """Set border color."""
        self._border_color = color
        if hasattr(color, 'hex'):
            color_str = color.hex
        else:
            color_str = str(color)
        self.backend.set_border_color(color_str)
    
    # Proxy properties for camera
    @property
    def camera_distance(self):
        """Get camera distance."""
        return self.camera.distance
    
    @camera_distance.setter
    def camera_distance(self, value):
        """Set camera distance."""
        self.camera.distance = value
        self.backend.set_camera_distance(value)
    
    # Axis visibility property
    @property
    def axis_visible(self):
        """Get axis visibility."""
        return self._axis_visible
    
    @axis_visible.setter  
    def axis_visible(self, value):
        """Set axis visibility."""
        self._axis_visible = value
        if self.axis:
            self.backend.set_axes_visibility(self.axis, value)
    
    # Make axis.visible work
    def __getattr__(self, name):
        """Handle axis.visible attribute access."""
        if name == 'axis':
            if not hasattr(self, '_axis_obj'):
                self._axis_obj = type('Axis', (), {})
                self._axis_obj.visible = self._axis_visible
                # Override visible setter
                def set_visible(value):
                    self._axis_visible = value
                    if self.axis:
                        self.backend.set_axes_visibility(self.axis, value)
                self._axis_obj.__class__.visible = property(
                    lambda self: self.parent._axis_visible,
                    lambda self, value: set_visible(value)
                )
                self._axis_obj.parent = self
            return self._axis_obj
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
    
    def render(self):
        """Force render update."""
        self.backend.render()
    
    def update(self):
        """Update canvas - compatibility method."""
        self.render()