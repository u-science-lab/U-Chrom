"""
Abstract rendering backend interface for U-Chrom Browser.
This allows switching between different rendering engines (VisPy, PyVista, etc.)
while maintaining the same control interface.
"""

from abc import ABC, abstractmethod
import numpy as np
from typing import Optional, Tuple, List, Dict, Any


class RenderingBackend(ABC):
    """Abstract base class for rendering backends."""
    
    @abstractmethod
    def __init__(self, parent=None):
        """Initialize the rendering backend."""
        pass
    
    @abstractmethod
    def get_native_widget(self):
        """Return the native widget that can be embedded in Qt."""
        pass
    
    @abstractmethod
    def set_background_color(self, color: str):
        """Set the background color of the scene."""
        pass
    
    @abstractmethod
    def set_camera_distance(self, distance: float):
        """Set the camera distance from the scene center."""
        pass
    
    @abstractmethod
    def get_camera_state(self) -> Dict[str, Any]:
        """Get the current camera state."""
        pass
    
    @abstractmethod
    def set_camera_state(self, state: Dict[str, Any]):
        """Set the camera state."""
        pass
    
    @abstractmethod
    def add_line(self, points: np.ndarray, color=None, width: float = 1.0) -> Any:
        """Add a line to the scene."""
        pass
    
    @abstractmethod
    def add_tube(self, points: np.ndarray, color=None, radius: float = 0.5) -> Any:
        """Add a tube to the scene."""
        pass
    
    @abstractmethod
    def add_points(self, points: np.ndarray, color=None, size: float = 1.0) -> Any:
        """Add points to the scene."""
        pass
    
    @abstractmethod
    def add_text(self, text: str, position: Tuple[float, float, float], 
                 color: str = '#FFFFFF', font_size: int = 12, bold: bool = False) -> Any:
        """Add 3D text to the scene."""
        pass
    
    @abstractmethod
    def add_text_overlay(self, text: str, position: str = 'top-left', 
                        color: str = '#FFFFFF', font_size: int = 12) -> Any:
        """Add 2D text overlay to the scene."""
        pass
    
    @abstractmethod
    def update_text_overlay(self, handle: Any, text: str = None, position: str = None,
                           color: str = None, font_size: int = None):
        """Update properties of a text overlay."""
        pass
    
    @abstractmethod
    def add_axes(self, visible: bool = True) -> Any:
        """Add coordinate axes to the scene."""
        pass
    
    @abstractmethod
    def set_axes_visibility(self, handle: Any, visible: bool):
        """Set the visibility of axes."""
        pass
    
    @abstractmethod
    def remove_object(self, handle: Any):
        """Remove an object from the scene."""
        pass
    
    @abstractmethod
    def clear_scene(self):
        """Clear all objects from the scene."""
        pass
    
    @abstractmethod
    def render(self):
        """Force a render update."""
        pass
    
    @abstractmethod
    def connect_mouse_events(self, on_click=None, on_move=None, on_wheel=None):
        """Connect mouse event handlers."""
        pass
    
    @abstractmethod
    def reset_camera(self):
        """Reset camera to default position."""
        pass
    
    @abstractmethod
    def set_border_color(self, color: str):
        """Set the border color of the viewport."""
        pass