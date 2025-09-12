import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from .canvas_control_pyvista import CanvasControlPyVista


class CanvasPyVista(QWidget):
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.setup_plotter()
        
    def setup_ui(self):
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)
        self.size = 800, 600
        
    def setup_plotter(self):
        # Create PyVista plotter with Qt backend
        self.plotter = QtInteractor(self)
        self.layout.addWidget(self.plotter.interactor)
        
        # Configure plotter settings
        self.plotter.set_background('black')
        self.plotter.enable_depth_peeling()  # Better transparency handling
        
        # Setup camera
        self.view = self.plotter
        self.view.camera_position = 'xy'
        self.view.camera.distance = 50
        
        # Add axes (initially hidden)
        self.axis = self.plotter.add_axes()
        self.axis.SetVisibility(False)
        
        # Text overlay for layer title
        self.layer_title_actor = None
        self._label_margin = 10
        self._label_position = "Top Left"
        self._layer_title_text = ""
        self._layer_title_color = 'white'
        self._layer_title_size = 14
        
        # Control panel with PyVista support
        self.control_panel = CanvasControlPyVista(self)
        
        # Track actors for management
        self.actors = []
        
    def set_layer_title(self, text: str):
        if text is None:
            text = ''
        self._layer_title_text = str(text)
        self._update_layer_title()
        
    def _update_layer_title(self):
        # Remove existing title if present
        if self.layer_title_actor is not None:
            self.plotter.remove_actor(self.layer_title_actor)
            self.layer_title_actor = None
            
        if not self._layer_title_text:
            return
            
        # Calculate position based on settings
        position = self._calculate_text_position()
        
        # Add new text actor
        self.layer_title_actor = self.plotter.add_text(
            self._layer_title_text,
            position=position,
            font_size=self._layer_title_size,
            color=self._layer_title_color,
            font='arial'
        )
        
    def _calculate_text_position(self):
        positions = {
            "Top Left": "upper_left",
            "Top Right": "upper_right", 
            "Bottom Left": "lower_left",
            "Bottom Right": "lower_right",
            "Top Center": "upper_edge",
            "Bottom Center": "lower_edge"
        }
        return positions.get(self._label_position, "upper_left")
        
    def set_layer_title_font_size(self, size: float):
        try:
            self._layer_title_size = int(float(size))
            self._update_layer_title()
        except Exception:
            pass
            
    def set_layer_title_position(self, position: str):
        self._label_position = position
        self._update_layer_title()
        
    def set_layer_title_color(self, color_name: str):
        # Map color names to values (PyVista accepts both names and hex)
        color_map = {
            "White": "white", "Black": "black", "Red": "red", "Green": "green",
            "Blue": "blue", "Yellow": "yellow", "Cyan": "cyan", "Magenta": "magenta",
            "Orange": "orange", "Purple": "purple", "Brown": "brown", "Pink": "pink",
            "Gray": "gray", "Olive": "olive", "Navy": "navy", "Lime": "lime",
            "Maroon": "maroon", "Teal": "teal", "Silver": "silver", "Gold": "gold"
        }
        self._layer_title_color = color_map.get(color_name, "white")
        self._update_layer_title()
        
    def set_background_color(self, color_name: str):
        # Map background color names 
        bg_color_map = {
            "Black": "black",
            "White": "white",
            "Light Gray": "#C0C0C0",
        }
        color = bg_color_map.get(color_name, "black")
        self.plotter.set_background(color)
        
    def clear_actors(self):
        """Remove all actors from the scene"""
        for actor in self.actors:
            self.plotter.remove_actor(actor)
        self.actors.clear()
        
    def add_actor(self, actor):
        """Add an actor and track it"""
        self.actors.append(actor)
        return actor
        
    def render(self):
        """Force render update"""
        self.plotter.render()