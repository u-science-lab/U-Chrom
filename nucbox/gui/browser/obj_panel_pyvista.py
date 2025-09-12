"""
PyVista-compatible control panels for layers
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QComboBox, QPushButton
from PyQt5.QtCore import Qt


class LayerPropsPanelPyVista(QWidget):
    """Base control panel for PyVista layers"""
    
    def __init__(self):
        super().__init__()
        self.layer = None
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Add common controls
        layout.addWidget(QLabel("Layer Properties"))
        
    def connect_with(self, layer):
        self.layer = layer
        
    def update_params(self):
        """Update parameters without causing errors"""
        pass


class ChromatinPropsPyVista(LayerPropsPanelPyVista):
    """Control panel for chromatin layer in PyVista"""
    
    def setup_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Style selector
        style_layout = QHBoxLayout()
        style_layout.addWidget(QLabel("Style:"))
        self.style_combo = QComboBox()
        self.style_combo.addItems(['line', 'tube', 'points', 'ribbon', 'surface'])
        self.style_combo.currentTextChanged.connect(self.on_style_change)
        style_layout.addWidget(self.style_combo)
        layout.addLayout(style_layout)
        
        # Width control
        width_layout = QHBoxLayout()
        width_layout.addWidget(QLabel("Width:"))
        self.width_slider = QSlider(Qt.Horizontal)
        self.width_slider.setMinimum(1)
        self.width_slider.setMaximum(50)
        self.width_slider.setValue(20)
        self.width_slider.valueChanged.connect(self.on_width_change)
        self.width_label = QLabel("2.0")
        width_layout.addWidget(self.width_slider)
        width_layout.addWidget(self.width_label)
        layout.addLayout(width_layout)
        
        # Color mode
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Color:"))
        self.color_combo = QComboBox()
        self.color_combo.addItems(['Rainbow', 'Single - White', 'Single - Red', 
                                   'Single - Blue', 'Single - Green'])
        self.color_combo.currentTextChanged.connect(self.on_color_change)
        color_layout.addWidget(self.color_combo)
        layout.addLayout(color_layout)
        
        # Opacity control
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(QLabel("Opacity:"))
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setMinimum(0)
        self.opacity_slider.setMaximum(100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.valueChanged.connect(self.on_opacity_change)
        self.opacity_label = QLabel("1.0")
        opacity_layout.addWidget(self.opacity_slider)
        opacity_layout.addWidget(self.opacity_label)
        layout.addLayout(opacity_layout)
        
    def on_style_change(self):
        if self.layer:
            style = self.style_combo.currentText()
            self.layer.cache_props['style'] = style
            self.layer.re_render()
            
    def on_width_change(self):
        if self.layer:
            width = self.width_slider.value() / 10.0
            self.width_label.setText(f"{width:.1f}")
            self.layer.cache_props['width'] = width
            self.layer.re_render()
            
    def on_color_change(self):
        if self.layer:
            text = self.color_combo.currentText()
            if text == 'Rainbow':
                self.layer.cache_props['color_mode'] = 'rainbow'
            else:
                self.layer.cache_props['color_mode'] = 'single'
                color_map = {
                    'White': '#FFFFFF',
                    'Red': '#FF0000',
                    'Blue': '#0000FF',
                    'Green': '#00FF00'
                }
                color_name = text.replace('Single - ', '')
                self.layer.cache_props['single_color'] = color_map.get(color_name, '#FFFFFF')
            self.layer.re_render()
            
    def on_opacity_change(self):
        if self.layer:
            opacity = self.opacity_slider.value() / 100.0
            self.opacity_label.setText(f"{opacity:.2f}")
            # Note: Opacity changes would require re-rendering with PyVista
            # For now, store the value for future use
            self.layer.cache_props['opacity'] = opacity
            
    def update_params(self):
        """Update UI from layer properties"""
        if self.layer and hasattr(self.layer, 'cache_props'):
            props = self.layer.cache_props
            
            # Update style
            if 'style' in props:
                index = self.style_combo.findText(props['style'])
                if index >= 0:
                    self.style_combo.setCurrentIndex(index)
                    
            # Update width
            if 'width' in props:
                self.width_slider.setValue(int(props['width'] * 10))
                self.width_label.setText(f"{props['width']:.1f}")
                
            # Update color mode
            if props.get('color_mode') == 'rainbow':
                self.color_combo.setCurrentText('Rainbow')
            elif props.get('color_mode') == 'single':
                color = props.get('single_color', '#FFFFFF')
                for i in range(self.color_combo.count()):
                    if color in self.color_combo.itemText(i):
                        self.color_combo.setCurrentIndex(i)
                        break