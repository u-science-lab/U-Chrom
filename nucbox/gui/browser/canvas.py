from vispy import scene
from PyQt5.QtGui import QFont, QFontMetrics

from .canvas_control import CanvasControl


class Canvas(scene.SceneCanvas):

    def __init__(self):
        scene.SceneCanvas.__init__(self, keys=None)
        self.size = 800, 600
        self.unfreeze()

        self.view = self.central_widget.add_view()
        self.view.bgcolor = "#000000"
        self.view.camera = 'turntable'
        self.view.camera.distance = 50

        # Add a 3D axis to keep us oriented
        self.axis = scene.visuals.XYZAxis(parent=self.view.scene)
        self.axis.visible = False

        # top-left overlay for current layer name
        self.layer_title = scene.visuals.Text('', parent=self.scene, color='#FFFFFF', bold=True, anchor_x='left', anchor_y='top')
        self.layer_title.font_size = 5
        # use pixel coordinates; update y on resize
        self.layer_title.transform = scene.transforms.STTransform()
        self._label_margin = 10
        self._label_position = "Top Left"  # Default position
        self.events.resize.connect(self._on_resize)
        self._on_resize(type('evt', (), {'size': self.size}))

        self.control_panel = CanvasControl(self)
        

        self.freeze()

    def _on_resize(self, event):
        try:
            w, h = event.size
        except Exception:
            w, h = self.size
        # Position text with enough margin for font size
        self._update_text_position()
        self._fit_label_within_canvas()

    def set_layer_title(self, text: str):
        if text is None:
            text = ''
        self.layer_title.text = str(text)
        self._fit_label_within_canvas()

    def set_layer_title_font_size(self, size: float):
        try:
            self.layer_title.font_size = float(size)
            self._fit_label_within_canvas(preferred_size=float(size))
            self._update_text_position()  # Reposition after size change
        except Exception:
            pass

    def set_layer_title_position(self, position: str):
        self._label_position = position
        self._update_text_anchors()
        self._update_text_position()

    def set_layer_title_color(self, color_name: str):
        # Map color names to hex values (matplotlib-inspired)
        color_map = {
            "White": "#FFFFFF", "Black": "#000000", "Red": "#FF0000", "Green": "#008000",
            "Blue": "#0000FF", "Yellow": "#FFFF00", "Cyan": "#00FFFF", "Magenta": "#FF00FF",
            "Orange": "#FFA500", "Purple": "#800080", "Brown": "#A52A2A", "Pink": "#FFC0CB",
            "Gray": "#808080", "Olive": "#808000", "Navy": "#000080", "Lime": "#00FF00",
            "Maroon": "#800000", "Teal": "#008080", "Silver": "#C0C0C0", "Gold": "#FFD700"
        }
        hex_color = color_map.get(color_name, "#FFFFFF")  # Default to white
        self.layer_title.color = hex_color

    def set_background_color(self, color_name: str):
        # Map background color names to hex values
        bg_color_map = {
            "Black": "#000000",
            "White": "#FFFFFF",
            "Light Gray": "#C0C0C0",
        }
        hex_color = bg_color_map.get(color_name, "#000000")  # Default to black
        self.view.bgcolor = hex_color

    def _fit_label_within_canvas(self, preferred_size: float = None):
        # Simple and safe approach: limit font size based on canvas dimensions
        try:
            w, h = self.size
        except Exception:
            return
        text = self.layer_title.text or ''
        if len(text) == 0:
            return
        
        # Extremely conservative limits to ensure no overflow
        margin = self._label_margin * 3  # Triple the margin for maximum safety
        
        # Much more conservative heuristic with safety factors
        available_width = max(20, w - margin * 2)
        available_height = max(20, h - margin * 2)
        
        # Very conservative estimates (assume each character takes 0.8x font size width)
        max_size_by_width = max(6, int(available_width / (max(1, len(text)) * 0.8)))
        # Assume text height is 1.5x font size
        max_size_by_height = max(6, int(available_height / 1.5))
        
        # Take the most restrictive constraint and apply additional safety factor
        max_safe_size = min(max_size_by_width, max_size_by_height, 30) * 0.7  # 30% safety margin
        
        # Use preferred size if provided, but always clamp to safe range
        if preferred_size is not None:
            target_size = min(preferred_size, max_safe_size)
        else:
            target_size = min(self.layer_title.font_size, max_safe_size)
        
        # Ensure minimum readable size but prioritize staying in bounds
        final_size = max(4.0, target_size)
        
        if abs(final_size - self.layer_title.font_size) > 0.5:
            self.layer_title.font_size = final_size

    def _update_text_anchors(self):
        # Update text anchors based on position
        position = self._label_position
        if "Left" in position:
            self.layer_title.anchors = ('left', self.layer_title.anchors[1])
        elif "Right" in position:
            self.layer_title.anchors = ('right', self.layer_title.anchors[1])
        else:  # Center
            self.layer_title.anchors = ('center', self.layer_title.anchors[1])
        
        if "Top" in position:
            self.layer_title.anchors = (self.layer_title.anchors[0], 'top')
        else:  # Bottom
            self.layer_title.anchors = (self.layer_title.anchors[0], 'bottom')

    def _update_text_position(self):
        # Position text based on selected position
        try:
            w, h = self.size
        except Exception:
            return
        
        font_size = self.layer_title.font_size
        margin = self._label_margin
        position = self._label_position
        
        # Calculate horizontal position
        if "Left" in position:
            x = margin
        elif "Right" in position:
            x = w - margin
        else:  # Center
            x = w / 2
        
        # Calculate vertical position
        if "Top" in position:
            # For top positions, move down by font size to keep text visible
            y = margin + font_size * 0.8
        else:  # Bottom
            # For bottom positions, move up by font size and margin to keep text visible
            y = h - margin - font_size * 0.8
        
        # Ensure positions are within bounds
        x = max(margin, min(x, w - margin))
        y = max(margin, min(y, h - margin))
        
        self.layer_title.pos = (x, y)


