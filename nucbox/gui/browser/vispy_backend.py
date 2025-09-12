"""
VisPy rendering backend for NucBrowser.
Wraps the existing VisPy implementation to match the abstract interface.
"""

import numpy as np
from vispy import scene
from vispy.color import Color
from typing import Optional, Tuple, List, Dict, Any

from .rendering_backend import RenderingBackend


class VisPyBackend(RenderingBackend):
    """VisPy implementation of the rendering backend."""
    
    def __init__(self, parent=None):
        """Initialize VisPy rendering backend."""
        self.canvas = scene.SceneCanvas(keys=None)
        self.canvas.size = 800, 600
        self.canvas.unfreeze()
        
        self.view = self.canvas.central_widget.add_view()
        self.view.bgcolor = "#000000"
        self.view.camera = 'turntable'
        self.view.camera.distance = 50
        
        # Axes
        self.axis = scene.visuals.XYZAxis(parent=self.view.scene)
        self.axis.visible = False
        
        # Text overlay
        self.text_overlay = scene.visuals.Text('', parent=self.canvas.scene, 
                                               color='#FFFFFF', bold=True, 
                                               anchor_x='left', anchor_y='top')
        self.text_overlay.font_size = 5
        self.text_overlay.transform = scene.transforms.STTransform()
        
        # Object tracking
        self.objects = {}
        
        # Connect resize event
        self.canvas.events.resize.connect(self._on_resize)
        self._on_resize(type('evt', (), {'size': self.canvas.size}))
        
        self.canvas.freeze()
        
        # Text overlay settings
        self._label_margin = 10
        self._label_position = "Top Left"
    
    def get_native_widget(self):
        """Return the native widget."""
        return self.canvas.native
    
    def set_background_color(self, color: str):
        """Set background color."""
        self.view.bgcolor = color
    
    def set_camera_distance(self, distance: float):
        """Set camera distance."""
        self.view.camera.distance = distance
    
    def get_camera_state(self) -> Dict[str, Any]:
        """Get camera state."""
        camera = self.view.camera
        return {
            'distance': getattr(camera, 'distance', None),
            'elevation': getattr(camera, 'elevation', None),
            'azimuth': getattr(camera, 'azimuth', None),
            'fov': getattr(camera, 'fov', None),
            'center': getattr(camera, 'center', None)
        }
    
    def set_camera_state(self, state: Dict[str, Any]):
        """Set camera state."""
        camera = self.view.camera
        for key, value in state.items():
            if hasattr(camera, key) and value is not None:
                setattr(camera, key, value)
    
    def add_line(self, points: np.ndarray, color=None, width: float = 1.0) -> Any:
        """Add line to scene."""
        if color is None:
            color = '#FFFFFF'
        
        # Handle per-vertex colors
        if isinstance(color, np.ndarray) and color.ndim == 2:
            # Per-vertex colors already in the right format for VisPy
            line_color = color
        else:
            line_color = Color(color) if isinstance(color, str) else color
        
        line = scene.visuals.Line(pos=points, parent=self.view.scene, 
                                 color=line_color, width=width)
        
        handle = len(self.objects)
        self.objects[handle] = line
        return handle
    
    def add_tube(self, points: np.ndarray, color=None, radius: float = 0.5) -> Any:
        """Add tube to scene."""
        if color is None:
            color = '#FFFFFF'
        
        tube = scene.visuals.Tube(points=points, parent=self.view.scene,
                                 color=Color(color) if isinstance(color, str) else color,
                                 radius=radius, tube_points=8)
        
        handle = len(self.objects)
        self.objects[handle] = tube
        return handle
    
    def add_points(self, points: np.ndarray, color=None, size: float = 1.0) -> Any:
        """Add points to scene."""
        if color is None:
            color = '#FFFFFF'
        
        # Handle per-vertex colors
        if isinstance(color, np.ndarray) and color.ndim == 2:
            markers_color = color
        else:
            markers_color = Color(color) if isinstance(color, str) else color
        
        markers = scene.visuals.Markers(pos=points, parent=self.view.scene,
                                       size=size, face_color=markers_color,
                                       edge_width=0, spherical=True, scaling=True)
        
        handle = len(self.objects)
        self.objects[handle] = markers
        return handle
    
    def add_text(self, text: str, position: Tuple[float, float, float],
                 color: str = '#FFFFFF', font_size: int = 12, bold: bool = False) -> Any:
        """Add 3D text to scene."""
        text_visual = scene.visuals.Text(text, color=color, parent=self.view.scene, bold=bold)
        text_visual.pos = position
        text_visual.font_size = font_size
        text_visual.set_gl_state(depth_test=True)
        
        handle = len(self.objects)
        self.objects[handle] = text_visual
        return handle
    
    def add_text_overlay(self, text: str, position: str = 'top-left',
                        color: str = '#FFFFFF', font_size: int = 12) -> Any:
        """Add 2D text overlay."""
        self.text_overlay.text = text
        self.text_overlay.color = color
        self.text_overlay.font_size = font_size
        self._label_position = position.replace('-', ' ').title()
        self._update_text_anchors()
        self._update_text_position()
        return self.text_overlay
    
    def update_text_overlay(self, handle: Any, text: str = None, position: str = None,
                           color: str = None, font_size: int = None):
        """Update text overlay."""
        if text is not None:
            self.text_overlay.text = text
        if color is not None:
            self.text_overlay.color = color
        if font_size is not None:
            # Accept float sizes to avoid rounding artifacts during small increments
            self.text_overlay.font_size = float(font_size)
            # Font size affects position margins; recompute
            self._update_text_position()
        if position is not None:
            self._label_position = position.replace('-', ' ').title()
            self._update_text_anchors()
            self._update_text_position()
    
    def add_axes(self, visible: bool = True) -> Any:
        """Add axes to scene."""
        self.axis.visible = visible
        return self.axis
    
    def set_axes_visibility(self, handle: Any, visible: bool):
        """Set axes visibility."""
        if handle:
            handle.visible = visible
    
    def remove_object(self, handle: Any):
        """Remove object from scene."""
        if handle in self.objects:
            obj = self.objects[handle]
            obj.parent = None
            del self.objects[handle]
    
    def clear_scene(self):
        """Clear all objects."""
        for obj in self.objects.values():
            obj.parent = None
        self.objects.clear()
        self.text_overlay.text = ''
    
    def render(self):
        """Force render update."""
        self.canvas.update()
    
    def connect_mouse_events(self, on_click=None, on_move=None, on_wheel=None):
        """Connect mouse events."""
        if on_click:
            self.view.events.mouse_press.connect(on_click)
        if on_move:
            self.view.events.mouse_move.connect(on_move)
        if on_wheel:
            self.view.events.mouse_wheel.connect(on_wheel)
    
    def reset_camera(self):
        """Reset camera."""
        self.view.camera.reset()
    
    def set_border_color(self, color: str):
        """Set border color."""
        self.view.border_color = Color(color)
    
    def _on_resize(self, event):
        """Handle resize event."""
        try:
            w, h = event.size
        except Exception:
            w, h = self.canvas.size
        self._update_text_position()
    
    def _update_text_anchors(self):
        """Update text anchors based on position."""
        position = self._label_position
        if "Left" in position:
            self.text_overlay.anchors = ('left', self.text_overlay.anchors[1])
        elif "Right" in position:
            self.text_overlay.anchors = ('right', self.text_overlay.anchors[1])
        else:
            self.text_overlay.anchors = ('center', self.text_overlay.anchors[1])
        
        if "Top" in position:
            self.text_overlay.anchors = (self.text_overlay.anchors[0], 'top')
        else:
            self.text_overlay.anchors = (self.text_overlay.anchors[0], 'bottom')
    
    def _update_text_position(self):
        """Update text position."""
        try:
            w, h = self.canvas.size
        except Exception:
            return
        
        font_size = self.text_overlay.font_size
        margin = self._label_margin
        position = self._label_position
        
        if "Left" in position:
            x = margin
        elif "Right" in position:
            x = w - margin
        else:
            x = w / 2
        
        if "Top" in position:
            y = margin + font_size * 0.8
        else:
            y = h - margin - font_size * 0.8
        
        x = max(margin, min(x, w - margin))
        y = max(margin, min(y, h - margin))
        
        self.text_overlay.pos = (x, y)