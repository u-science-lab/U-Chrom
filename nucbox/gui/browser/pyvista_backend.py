"""
PyVista rendering backend for NucBrowser.
Provides high-performance 3D rendering using VTK through PyVista.
"""

import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QPalette, QColor
from typing import Optional, Tuple, List, Dict, Any
from matplotlib import colors as mpl_colors

from .rendering_backend import RenderingBackend


class PyVistaBackend(RenderingBackend):
    """PyVista implementation of the rendering backend."""
    
    def __init__(self, parent=None):
        """Initialize PyVista rendering backend."""
        self.parent = parent
        self.widget = QWidget()
        self.layout = QVBoxLayout(self.widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # Create PyVista plotter with Qt interactor
        # auto_update=True to ensure updates are shown
        self.plotter = QtInteractor(self.widget, auto_update=True)
        self.layout.addWidget(self.plotter)
        
        # Initialize plotter settings
        self.plotter.set_background('black')
        self.plotter.enable_trackball_style()
        
        # Optimize for interaction performance
        try:
            self.plotter.enable_depth_peeling(number_of_peels=4, occlusion_ratio=0.0)
        except:
            pass
        
        # Set render window update rates if available
        if hasattr(self.plotter.ren_win, 'SetDesiredUpdateRate'):
            self.plotter.ren_win.SetDesiredUpdateRate(30.0)  # Target 30 FPS during interaction
        
        # Store handles to objects
        self.objects = {}  # Maps our handle IDs to actor objects
        self.actor_names = {}  # Maps actor objects to their names in PyVista
        self.text_overlays = {}
        self.axes_actor = None
        self._handle_counter = 0
        
        # Text overlay widget (for 2D text)
        self.overlay_label = QLabel(self.widget)
        self.overlay_label.setStyleSheet("""
            QLabel {
                color: white;
                background-color: black;
                font-weight: bold;
                padding: 10px;
            }
        """)
        self.overlay_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.overlay_label.hide()
        
        # Mouse event callbacks
        self.on_click_callback = None
        self.on_move_callback = None
        self.on_wheel_callback = None
        
        # Connect Qt events
        self._connect_events()
        
        # Track camera state for synchronization
        self._camera_state = None
        
        # Set up interaction callbacks for performance optimization
        self._setup_interaction_callbacks()
        
        # Render batching / debouncing
        self._render_blocked = 0
        self._render_scheduled = False
        
    def get_native_widget(self):
        """Return the native Qt widget."""
        return self.widget
    
    def set_background_color(self, color: str):
        """Set the background color."""
        self.plotter.set_background(color)
        self.render()
    
    def set_camera_distance(self, distance: float):
        """Set camera distance from the scene center."""
        camera = self.plotter.camera
        position = np.array(camera.position)
        center = np.array(camera.focal_point)
        direction = position - center
        if np.linalg.norm(direction) > 0:
            direction = direction / np.linalg.norm(direction)
            new_position = center + direction * distance
            camera.position = new_position
            self.plotter.reset_camera_clipping_range()
            self.render()
    
    def get_camera_state(self) -> Dict[str, Any]:
        """Get the current camera state (robust across PyVista/VTK versions)."""
        cam = getattr(self.plotter, 'camera', None)
        if cam is None:
            return {}
        def _get(attr_name, default=None):
            # Try attribute
            try:
                val = getattr(cam, attr_name)
                return val
            except Exception:
                pass
            # Try VTK getter e.g. GetViewUp
            try:
                method_name = 'Get' + ''.join([p.capitalize() for p in attr_name.split('_')])
                method = getattr(cam, method_name, None)
                if callable(method):
                    return method()
            except Exception:
                pass
            # Known alias for view_up
            if attr_name == 'view_up':
                try:
                    return getattr(cam, 'up')
                except Exception:
                    pass
            return default
        return {
            'position': _get('position'),
            'focal_point': _get('focal_point'),
            'view_up': _get('view_up'),
            'clipping_range': _get('clipping_range'),
            'view_angle': _get('view_angle')
        }
    
    def set_camera_state(self, state: Dict[str, Any]):
        """Set the camera state (robust across PyVista/VTK versions)."""
        cam = getattr(self.plotter, 'camera', None)
        if cam is None or not isinstance(state, dict):
            return
        def _set(attr_name, value):
            try:
                setattr(cam, attr_name, value)
                return True
            except Exception:
                pass
            # Try VTK setter e.g. SetViewUp
            try:
                method_name = 'Set' + ''.join([p.capitalize() for p in attr_name.split('_')])
                method = getattr(cam, method_name, None)
                if callable(method):
                    method(value)
                    return True
            except Exception:
                pass
            # Known alias
            if attr_name == 'view_up':
                try:
                    setattr(cam, 'up', value)
                    return True
                except Exception:
                    pass
            return False
        for key in ['position', 'focal_point', 'view_up', 'view_angle', 'clipping_range']:
            if key in state and state[key] is not None:
                _set(key, state[key])
        try:
            self.plotter.reset_camera_clipping_range()
        except Exception:
            pass
        self.render()
    
    def add_line(self, points: np.ndarray, color=None, width: float = 1.0, opacity: float = 1.0) -> Any:
        """Add a line to the scene."""
        if points.shape[0] < 2:
            return None
            
        # Create a PolyData line
        line = pv.PolyData()
        line.points = points
        cells = np.full((points.shape[0] - 1, 3), 2, dtype=np.int_)
        cells[:, 1] = np.arange(0, points.shape[0] - 1, dtype=np.int_)
        cells[:, 2] = np.arange(1, points.shape[0], dtype=np.int_)
        line.lines = cells
        
        # Handle color
        if color is not None:
            if isinstance(color, np.ndarray) and color.ndim == 2:
                # Per-vertex colors
                if color.shape[1] == 4:
                    line['colors'] = (color[:, :3] * 255).astype(np.uint8)
                else:
                    line['colors'] = (color * 255).astype(np.uint8)
                scalars = 'colors'
            else:
                # Single color
                if isinstance(color, str):
                    color_rgb = mpl_colors.to_rgb(color)
                else:
                    color_rgb = color[:3] if len(color) >= 3 else color
                scalars = None
        else:
            color_rgb = (1, 1, 1)
            scalars = None
        
        # Add to plotter with a unique name
        name = f'line_{self._handle_counter}'
        # Use tube rendering for transparency or thicker widths to ensure blending works
        render_as_tubes = (width > 2.0) or (float(opacity) < 0.999)
        actor = self.plotter.add_mesh(
            line,
            name=name,
            color=color_rgb if scalars is None else None,
            scalars=scalars if scalars else None,
            line_width=width,
            rgb=True if scalars else False,
            opacity=float(opacity),
            render_lines_as_tubes=render_as_tubes
        )
        
        handle = self._handle_counter
        self._handle_counter += 1
        self.objects[handle] = actor
        self.actor_names[actor] = name
        # Don't render immediately for better batch performance
        return handle
    
    def add_tube(self, points: np.ndarray, color=None, radius: float = 0.5, opacity: float = 1.0) -> Any:
        """Add a tube to the scene."""
        if points.shape[0] < 2:
            return None
            
        # For better performance, use PolyLine directly without spline interpolation
        # This creates a simpler tube that renders faster
        polyline = pv.PolyData()
        polyline.points = points
        cells = np.full((points.shape[0] - 1, 3), 2, dtype=np.int_)
        cells[:, 1] = np.arange(0, points.shape[0] - 1, dtype=np.int_)
        cells[:, 2] = np.arange(1, points.shape[0], dtype=np.int_)
        polyline.lines = cells
        
        # Create tube with reduced complexity
        tube = polyline.tube(radius=radius, n_sides=6)  # Reduced to 6 sides for performance
        
        # Optionally decimate for very complex meshes
        try:
            if tube.n_cells > 2000:  # Only decimate if really needed
                tube = tube.decimate(0.5)  # Simple 50% reduction
        except:
            pass  # Skip if decimate fails
        
        # Handle color
        if isinstance(color, tuple) or isinstance(color, list):
            color_rgb = color[:3]
        elif isinstance(color, str):
            color_rgb = mpl_colors.to_rgb(color)
        else:
            color_rgb = (1, 1, 1)
        
        # Add to plotter with optimized settings for performance
        name = f'tube_{self._handle_counter}'
        actor = self.plotter.add_mesh(
            tube,
            name=name,
            color=color_rgb,
            smooth_shading=False,  # Disable for better performance
            specular=0.1,          # Reduce specular for simpler shading
            specular_power=10,     # Lower for faster rendering
            interpolate_before_map=False,  # Disable interpolation
            lighting=True,
            render_points_as_spheres=False,
            opacity=float(opacity)
        )
        
        handle = self._handle_counter
        self._handle_counter += 1
        self.objects[handle] = actor
        self.actor_names[actor] = name
        # Don't render immediately for better batch performance
        return handle
    
    def add_points(self, points: np.ndarray, color=None, size: float = 1.0, opacity: float = 1.0) -> Any:
        """Add points to the scene."""
        if points.shape[0] == 0:
            return None
            
        # Create point cloud
        point_cloud = pv.PolyData(points)
        
        # Handle color
        if color is not None:
            if isinstance(color, np.ndarray) and color.ndim == 2:
                # Per-vertex colors
                if color.shape[1] == 4:
                    point_cloud['colors'] = (color[:, :3] * 255).astype(np.uint8)
                else:
                    point_cloud['colors'] = (color * 255).astype(np.uint8)
                scalars = 'colors'
            else:
                # Single color
                if isinstance(color, str):
                    color_rgb = mpl_colors.to_rgb(color)
                else:
                    color_rgb = color[:3] if len(color) >= 3 else color
                scalars = None
        else:
            color_rgb = (1, 1, 1)
            scalars = None
        
        # Add spheres at each point for better visualization
        name = f'points_{self._handle_counter}'
        actor = self.plotter.add_mesh(
            point_cloud,
            name=name,
            color=color_rgb if scalars is None else None,
            scalars=scalars if scalars else None,
            point_size=size * 10,  # Scale up for visibility
            render_points_as_spheres=True,
            rgb=True if scalars else False,
            opacity=float(opacity)
        )
        
        handle = self._handle_counter
        self._handle_counter += 1
        self.objects[handle] = actor
        self.actor_names[actor] = name
        # Don't render immediately for better batch performance
        return handle

    def set_object_opacity(self, handle: Any, opacity: float):
        """Update opacity of an existing object without full redraw."""
        if handle in self.objects:
            actor = self.objects[handle]
            try:
                actor.GetProperty().SetOpacity(float(opacity))
                self.render()
            except Exception:
                pass
    
    def add_text(self, text: str, position: Tuple[float, float, float], 
                 color: str = '#FFFFFF', font_size: int = 12, bold: bool = False) -> Any:
        """Add 3D text to the scene."""
        # Use add_point_labels for better 3D text rendering
        name = f'text3d_{self._handle_counter}'
        
        # Convert position to numpy array
        import numpy as np
        points = np.array([position], dtype=np.float32)
        
        # Scale font_size appropriately (PyVista uses different scale)
        scaled_font_size = max(12, int(font_size / 10))  # Scale down from backend units
        
        # Add the label
        actor = self.plotter.add_point_labels(
            points,
            [text],
            name=name,
            font_size=scaled_font_size,
            text_color=mpl_colors.to_rgb(color),
            always_visible=True,
            show_points=False,  # Don't show the point markers
            shape_opacity=0,  # Hide the background shape
            bold=bold
        )
        
        handle = self._handle_counter
        self._handle_counter += 1
        self.objects[handle] = actor
        self.actor_names[actor] = name
        # Don't render immediately for better batch performance
        return handle
    
    def add_text_overlay(self, text: str, position: str = 'top-left', 
                        color: str = '#FFFFFF', font_size: int = 12) -> Any:
        """Add 2D text overlay."""
        # Use Qt label for overlay
        self.overlay_label.setText(text)
        background_color = self.plotter.background_color.hex_rgb
        self.overlay_label.setStyleSheet(f"""
            QLabel {{
                color: {color};
                background-color: {background_color};
                font-size: {font_size}pt;
                font-weight: bold;
                padding: 10px;
            }}
        """)
        # Ensure the label resizes to fit the new font size
        self.overlay_label.adjustSize()
        
        # Position the label
        self._position_overlay(position)
        self.overlay_label.show()
        
        handle = 'main_overlay'
        self.text_overlays[handle] = {
            'widget': self.overlay_label,
            'position': position
        }
        return handle
    
    def update_text_overlay(self, handle: Any, text: str = None, position: str = None,
                           color: str = None, font_size: int = None, force_update: bool = False):
        """Update text overlay properties."""
        self.begin_update()
        if handle not in self.text_overlays:
            self.end_update()
            return

        overlay = self.text_overlays[handle]
        widget = overlay['widget']
        
        if text is not None:
            widget.setText(text)
            # Text change can alter size
            widget.adjustSize()
        
        if position is not None:
            overlay['position'] = position
            self._position_overlay(position)
        
        # Update style if needed
        if color is not None or font_size is not None or force_update:
            current_color = color or widget.palette().color(QPalette.WindowText).name()
            # Only update font size if explicitly provided, otherwise preserve current size
            if font_size is not None:
                current_size = font_size
            else:
                # Get current font size from existing stylesheet or use default
                current_style = widget.styleSheet()
                import re
                size_match = re.search(r'font-size:\s*(\d+(?:\.\d+)?)pt', current_style)
                current_size = float(size_match.group(1)) if size_match else 12

            background_color = self.plotter.background_color.hex_rgb
            widget.setStyleSheet(f"""
                QLabel {{
                    color: {current_color};
                    background-color: {background_color};
                    font-size: {current_size}pt;
                    font-weight: bold;
                    padding: 10px;
                }}
            """)
            # Style change (e.g., font size) can alter size
            #widget.adjustSize()

        # Reposition after any potential size change to keep margins correct
        self._position_overlay(overlay['position'])
        self.end_update()
    
    def _position_overlay(self, position: str):
        """Position the overlay label based on position string."""
        widget_size = self.widget.size()
        label_size = self.overlay_label.sizeHint()
        
        x, y = 10, 10  # Default margins
        pos_lower = position.lower()
        
        # Parse position string correctly
        # Format: "vertical-horizontal" or "vertical horizontal"
        # e.g., "top-center", "bottom-right", "center"
        
        # Horizontal positioning
        if 'right' in pos_lower:
            x = widget_size.width() - label_size.width() - 10
        elif 'left' in pos_lower:
            x = 10
        elif 'center' in pos_lower or '-center' in pos_lower or ' center' in pos_lower:
            # Only center horizontally if center is specified for horizontal position
            x = (widget_size.width() - label_size.width()) // 2
        
        # Vertical positioning
        if 'bottom' in pos_lower:
            y = widget_size.height() - label_size.height() - 10
        elif 'top' in pos_lower:
            y = 10
        elif pos_lower == 'center' or pos_lower.startswith('center-') or pos_lower.startswith('center '):
            # Only center vertically if position is exactly "center" or starts with "center-"
            y = (widget_size.height() - label_size.height()) // 2
        
        self.overlay_label.move(x, y)
    
    def add_axes(self, visible: bool = True) -> Any:
        """Add coordinate axes."""
        if self.axes_actor is None:
            self.axes_actor = self.plotter.add_axes(
                xlabel='X',
                ylabel='Y', 
                zlabel='Z',
                line_width=3,
                labels_off=False
            )
        self.axes_actor.SetVisibility(visible)
        self.render()
        return self.axes_actor
    
    def set_axes_visibility(self, handle: Any, visible: bool):
        """Set axes visibility."""
        if handle:
            self.begin_update()
            handle.SetVisibility(visible)
            self.end_update()
    
    def remove_object(self, handle: Any):
        """Remove an object from the scene."""
        self.begin_update()
        if handle in self.objects:
            actor = self.objects[handle]
            # Get the name if we have it
            name = self.actor_names.get(actor)
            
            # Use PyVista's remove_actor - it can take either actor or name
            try:
                if name and name in self.plotter.renderer.actors:
                    # Remove by name is more reliable
                    self.plotter.remove_actor(name, render=False)
                else:
                    # Fallback to actor object
                    self.plotter.remove_actor(actor, render=False)
            except Exception:
                # If removal fails, at least hide it
                try:
                    actor.SetVisibility(False)
                except:
                    pass
            
            # Clean up our tracking
            del self.objects[handle]
            if actor in self.actor_names:
                del self.actor_names[actor]
            
            # Single render will be handled by end_update()
            
        elif handle in self.text_overlays:
            overlay = self.text_overlays[handle]
            overlay['widget'].hide()
            del self.text_overlays[handle]
        self.end_update()
    
    def clear_scene(self):
        """Clear all objects from the scene."""
        self.begin_update()
        # Remove each actor by name for reliability
        for handle, actor in list(self.objects.items()):
            name = self.actor_names.get(actor)
            try:
                if name:
                    self.plotter.remove_actor(name, render=False)
                else:
                    self.plotter.remove_actor(actor, render=False)
            except:
                try:
                    actor.SetVisibility(False)
                except:
                    pass
        
        # Clear our tracking
        self.objects.clear()
        self.actor_names.clear()
        
        # Hide overlay
        self.overlay_label.hide()
        self.text_overlays.clear()
        
        # Re-add axes if they were visible
        if self.axes_actor and self.axes_actor.GetVisibility():
            self.axes_actor = self.plotter.add_axes(
                xlabel='X',
                ylabel='Y',
                zlabel='Z',
                line_width=3
            )
        self.end_update()
    
    def render(self):
        """Debounced render update (coalesces multiple calls in same event loop)."""
        if self._render_blocked > 0:
            # Defer rendering until end_update()
            self._render_scheduled = True
            return
        if self._render_scheduled:
            return
        self._render_scheduled = True
        def _do_render():
            self._render_scheduled = False
            try:
                if hasattr(self.plotter, 'render'):
                    self.plotter.render()
            except Exception:
                pass
        # Schedule at end of event loop to collapse bursts
        QTimer.singleShot(0, _do_render)

    def begin_update(self):
        """Start a batch update to suppress intermediate renders."""
        self._render_blocked += 1

    def end_update(self):
        """End a batch update and render once if needed."""
        self._render_blocked = max(0, self._render_blocked - 1)
        if self._render_blocked == 0 and self._render_scheduled:
            self.render()
    
    def connect_mouse_events(self, on_click=None, on_move=None, on_wheel=None):
        """Connect mouse event handlers."""
        self.on_click_callback = on_click
        self.on_move_callback = on_move  
        self.on_wheel_callback = on_wheel
        
        # PyVista has its own event system
        if on_click:
            self.plotter.track_click_position(callback=self._on_click_wrapper, side='left')
    
    def _on_click_wrapper(self, pos):
        """Wrapper for click events."""
        if self.on_click_callback:
            # Create a mock event object similar to VisPy
            event = type('Event', (), {'pos': pos})
            self.on_click_callback(event)
    
    def _connect_events(self):
        """Connect internal Qt events."""
        # Handle widget resize
        self.widget.resizeEvent = self._on_resize
    
    def _setup_interaction_callbacks(self):
        """Set up callbacks to optimize rendering during interaction."""
        # Simplified - removed to avoid complexity and potential issues
        pass
    
    def _on_resize(self, event):
        """Handle widget resize."""
        # Reposition overlay
        if self.text_overlays:
            for overlay in self.text_overlays.values():
                self._position_overlay(overlay['position'])
        
        # Call original resize
        QWidget.resizeEvent(self.widget, event)
    
    def reset_camera(self):
        """Reset camera to default position."""
        self.plotter.reset_camera()
        self.render()
    
    def set_border_color(self, color: str):
        """Set viewport border color."""
        # PyVista doesn't directly support border color, 
        # but we can style the Qt widget
        if isinstance(color, str):
            qcolor = QColor(color)
            self.widget.setStyleSheet(f"border: 2px solid {color};")