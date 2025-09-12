import random
import itertools
import os.path as osp
import os

from PyQt5 import QtGui
import numpy as np
from vispy.color import Color

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QFileDialog, QMainWindow, QSplitter, QStackedWidget, 
                             QAction, QMessageBox, QMenuBar, QDockWidget, QTabWidget)

from nucbox.utils.io import read_particles
from .canvas_pyvista import CanvasPyVista
from .layers_pyvista import ChromatinLayerPyVista, ChrLabelLayerPyVista, LayerPyVista
from .menubar import MenuBar
from .layers import ChromatinLayer, ChrLabelLayer
from .range_list import RangeList


HERE = osp.dirname(osp.abspath(__file__))


def random_color():
    return "#"+''.join([random.choice('0123456789ABCDEF') for _ in range(6)])


class MainWindowPyVista(QMainWindow):
    
    def __init__(self, canvas_only=False):
        QMainWindow.__init__(self)
        
        self.chr_colormap = {}
        self.layers = []  # Track layers
        self.current_layer = None
        self.current_ix = (0, 0)  # For compatibility
        
        self.resize(1100, 700)
        self.setWindowTitle('NucBrowser - PyVista Enhanced')
        
        # Main splitter for canvas and control panel
        self.splitter = QSplitter(Qt.Horizontal)
        self.control_stack = QStackedWidget()
        
        # Canvas grid for multi-view support (currently single canvas)
        self.canvas_grid = []
        self.canvas_grid_widget = QSplitter(Qt.Horizontal)
        
        # Create PyVista canvas
        self.canvas = CanvasPyVista()
        self.canvas_grid = [[self.canvas]]  # Single canvas for now
        
        # Add canvas to splitter
        self.splitter.addWidget(self.canvas)
        
        # Set as central widget
        self.setCentralWidget(self.splitter)
        self.setWindowIcon(QtGui.QIcon(osp.join(HERE, '../nucbox.svg')))
        
        # Setup menu bar with original MenuBar class
        self.menubar = MenuBar(self)
        self.setMenuBar(self.menubar)
        
        if not canvas_only:
            self.add_widgets()
            
    def setup_menubar(self):
        """Setup the menu bar with file operations"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('File')
        
        # Open action
        open_action = QAction('Open CSV', self)
        open_action.setShortcut('Ctrl+O')
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)
        
        # Save screenshot action
        screenshot_action = QAction('Save Screenshot', self)
        screenshot_action.setShortcut('Ctrl+S')
        screenshot_action.triggered.connect(self.save_screenshot)
        file_menu.addAction(screenshot_action)
        
        # Exit action
        exit_action = QAction('Exit', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # View menu
        view_menu = menubar.addMenu('View')
        
        # Toggle axes
        axes_action = QAction('Toggle Axes', self)
        axes_action.triggered.connect(self.toggle_axes)
        view_menu.addAction(axes_action)
        
        # Reset camera
        reset_camera_action = QAction('Reset Camera', self)
        reset_camera_action.triggered.connect(self.reset_camera)
        view_menu.addAction(reset_camera_action)
        
        # Rendering menu
        render_menu = menubar.addMenu('Rendering')
        
        # Enable/disable depth peeling
        depth_peeling_action = QAction('Toggle Depth Peeling', self)
        depth_peeling_action.triggered.connect(self.toggle_depth_peeling)
        render_menu.addAction(depth_peeling_action)
        
        # Enable/disable anti-aliasing
        aa_action = QAction('Toggle Anti-Aliasing', self)
        aa_action.triggered.connect(self.toggle_antialiasing)
        render_menu.addAction(aa_action)
        
    def add_widgets(self):
        """Add control widgets and setup UI layout"""
        # Add control stack to splitter
        self.splitter.addWidget(self.control_stack)
        self.splitter.setSizes([850, 250])
        
        # Add canvas control panel to stack
        self.control_stack.addWidget(self.canvas.control_panel)
        self.control_stack.setCurrentWidget(self.canvas.control_panel)
        
        # Connect menu bar events
        self._connect_events()
        
    def _connect_events(self):
        """Connect menu bar events"""
        self.menubar.action_open.triggered.connect(self.open_file_dialog)
        self.menubar.action_show_axis.triggered.connect(self.on_toggle_show_axis)
        # Add more event connections as needed
        
    @property
    def link_canvas(self):
        """Property for canvas linking compatibility"""
        return self.menubar.link_canvas if hasattr(self.menubar, 'link_canvas') else False
        
    def open_file_dialog(self):
        """Open file dialog compatible with original interface"""
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        path, _ = QFileDialog.getOpenFileName(self, "Open", "", "All Files (*);;CSV Files(*.csv)", options=options)
        if path:
            try:
                print(f"Loading: {path}")
                df = read_particles(path)
                self.load_model(df, path)
                self.init_draw()
            except Exception as e:
                QMessageBox.critical(self, 'Error', f'Failed to load file: {str(e)}')
                print(str(e))
                
    def open_file(self):
        """Alias for compatibility"""
        self.open_file_dialog()
                
    def load_model(self, df, path: str = None):
        """Load model compatible with original interface"""
        random.seed(0)
        
        # Generate colormap for chromosomes
        for c in df['chrom'].unique():
            if c not in self.chr_colormap:
                self.chr_colormap[c] = random_color()
                
        # Extract name from path
        name = None
        try:
            if path is not None:
                base = osp.basename(path)
                name = osp.splitext(base)[0]
        except Exception:
            pass
            
        # Add chromatin layer through control panel
        if hasattr(self.canvas, 'control_panel'):
            self.canvas.control_panel.add_chromatin_layer(df, self.chr_colormap, name=name)
        else:
            # Direct creation if no control panel
            self.clear_all_layers()
            chromatin_layer = ChromatinLayerPyVista(
                self.canvas, df, self.chr_colormap, width=2.0, style='tube'
            )
            chromatin_layer.name = name or "Chromatin"
            self.layers.append(chromatin_layer)
            self.current_layer = chromatin_layer
            
        # Update canvas title
        if name:
            self.canvas.set_layer_title(name)
            
    def init_draw(self):
        """Initialize drawing for all layers"""
        if hasattr(self.canvas, 'control_panel'):
            for layer in self.canvas.control_panel.layers:
                layer.draw()
        else:
            for layer in self.layers:
                layer.draw()
                
        # Reset camera
        self.canvas.plotter.reset_camera()
        self.canvas.render()
        
    def load_particles(self, filename):
        """Load particle data from CSV file - wrapper for compatibility"""
        df = read_particles(filename)
        self.load_model(df, filename)
        self.init_draw()
        
    def clear_all_layers(self):
        """Remove all layers"""
        for layer in self.layers:
            layer.remove()
        self.layers.clear()
        self.current_layer = None
        
    def save_screenshot(self):
        """Save a screenshot of the current view"""
        filename, _ = QFileDialog.getSaveFileName(
            self, 'Save Screenshot', '', 'PNG Files (*.png);;All Files (*)'
        )
        
        if filename:
            try:
                self.canvas.plotter.screenshot(filename)
                QMessageBox.information(self, 'Success', f'Screenshot saved to {filename}')
            except Exception as e:
                QMessageBox.critical(self, 'Error', f'Failed to save screenshot: {str(e)}')
                
    def on_toggle_show_axis(self, *args):
        """Toggle axes visibility - compatible with original interface"""
        val = self.menubar.show_axis if hasattr(self.menubar, 'show_axis') else False
        if hasattr(self.canvas, 'axis'):
            self.canvas.axis.SetVisibility(val)
            self.canvas.render()
            
    def toggle_axes(self):
        """Toggle axes visibility"""
        if hasattr(self.canvas, 'axis'):
            current_visibility = self.canvas.axis.GetVisibility()
            self.canvas.axis.SetVisibility(not current_visibility)
            self.canvas.render()
            
    def reset_camera(self):
        """Reset camera to default position"""
        self.canvas.plotter.reset_camera()
        self.canvas.render()
        
    def toggle_depth_peeling(self):
        """Toggle depth peeling for better transparency"""
        # PyVista depth peeling is typically always on
        # This is a placeholder for the feature
        pass
        
    def toggle_antialiasing(self):
        """Toggle anti-aliasing"""
        current = self.canvas.plotter.ren_win.GetMultiSamples()
        if current > 0:
            self.canvas.plotter.ren_win.SetMultiSamples(0)
        else:
            self.canvas.plotter.ren_win.SetMultiSamples(8)
        self.canvas.render()
        
    def set_render_style(self, style):
        """Change rendering style for current layer"""
        if self.current_layer and hasattr(self.current_layer, 'cache_props'):
            self.current_layer.cache_props['style'] = style
            self.current_layer.re_render()
            self.canvas.render()
            
    def set_render_width(self, width):
        """Change line/point width for current layer"""
        if self.current_layer and hasattr(self.current_layer, 'cache_props'):
            self.current_layer.cache_props['width'] = width
            self.current_layer.re_render()
            self.canvas.render()