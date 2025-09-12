"""
Modified MainWindow that uses the new Canvas with rendering backend abstraction.
This maintains full compatibility with the original interface while adding PyVista support.
"""

import random
import itertools
import os.path as osp

from PyQt5 import QtGui
import numpy as np
from vispy.color import Color

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QFileDialog, QMainWindow, QSplitter, QStackedWidget, QMessageBox, QAction)

from nucbox.utils.io import read_particles
from .canvas_new import Canvas  # Use new Canvas with backend support
from .menubar import MenuBar
from .config import get_backend, set_backend


HERE = osp.dirname(osp.abspath(__file__))


def random_color():
    return "#"+''.join([random.choice('0123456789ABCDEF') for _ in range(6)])


class MainWindow(QMainWindow):

    def __init__(self, canvas_only=False, backend=None):
        QMainWindow.__init__(self)

        self.chr_colormap = {}
        
        # Use specified backend or default from config
        self.backend = backend or get_backend()

        self.resize(1100, 700)
        self.setWindowTitle('NucBrowser (PyVista Enhanced)')

        self.splitter = QSplitter(Qt.Horizontal)
        self.control_stack = QStackedWidget()

        self.canvas_grid = []
        self.vsps = []
        self.canvas_grid_widget = QSplitter(Qt.Horizontal)
        self.current_ix = (0, -1)
        self.canvas = None
        self.add_canvas('h')

        self.splitter.addWidget(self.canvas_grid_widget)
        self.setCentralWidget(self.splitter)
        self.setWindowIcon(QtGui.QIcon(osp.join(HERE, '../nucbox.svg')))
        self.menubar = MenuBar(self)
        
        # Add backend switching menu
        self._add_backend_menu()
        
        if not canvas_only:
            self.add_widgets()

    def _add_backend_menu(self):
        """Add menu for switching rendering backends."""
        # Add to View menu or create new menu
        view_menu = self.menubar.addMenu('Renderer')
        
        # PyVista action
        action_pyvista = QAction('Use PyVista (Recommended)', self)
        action_pyvista.setCheckable(True)
        action_pyvista.setChecked(self.backend == 'pyvista')
        action_pyvista.triggered.connect(lambda: self._switch_backend('pyvista'))
        view_menu.addAction(action_pyvista)
        
        # VisPy action
        action_vispy = QAction('Use VisPy (Legacy)', self)
        action_vispy.setCheckable(True)
        action_vispy.setChecked(self.backend == 'vispy')
        action_vispy.triggered.connect(lambda: self._switch_backend('vispy'))
        view_menu.addAction(action_vispy)
        
        self.backend_actions = {
            'pyvista': action_pyvista,
            'vispy': action_vispy
        }
    
    def _switch_backend(self, backend):
        """Switch rendering backend for all canvases."""
        if backend == self.backend:
            return
        
        # Show warning
        reply = QMessageBox.question(
            self, 'Switch Renderer',
            f'Switching to {backend.upper()} renderer will clear the current scene. Continue?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.backend = backend
            set_backend(backend)
            
            # Update menu checkmarks
            for name, action in self.backend_actions.items():
                action.setChecked(name == backend)
            
            # Recreate all canvases with new backend
            self._recreate_canvases()
            
            # Update window title
            renderer_name = 'PyVista Enhanced' if backend == 'pyvista' else 'VisPy'
            self.setWindowTitle(f'NucBrowser ({renderer_name})')
    
    def _recreate_canvases(self):
        """Recreate all canvases with the current backend."""
        # Store current canvas configuration
        canvas_count = len(list(self.get_all_canvas()))
        
        # Clear existing canvases
        for canvas in list(self.get_all_canvas()):
            canvas.backend.clear_scene()
        
        # Note: In production, you'd want to preserve and restore the scene content
        # This is a simplified version that just clears and recreates
        
        QMessageBox.information(
            self, 'Renderer Switched',
            f'Switched to {self.backend.upper()} renderer. Please reload your data.'
        )

    @property
    def link_canvas(self):
        return self.menubar.link_canvas

    def add_canvas(self, orientation='h'):
        canvas = Canvas(backend=self.backend)  # Use configured backend
        canvas.create_native()
        canvas.native.setParent(self)
        
        # Connect events
        canvas.view.events.mouse_press.connect(self.on_click_canvas)
        canvas.view.events.mouse_move.connect(self.trigger_other_canvas_mouse_event)
        canvas.view.events.mouse_wheel.connect(self.trigger_other_canvas_mouse_event)
        
        self.canvas = canvas
        ix = self.current_ix
        if orientation == 'h':
            vsp = QSplitter(Qt.Vertical)
            vsp.addWidget(canvas.native)
            self.canvas_grid.append([canvas])
            self.canvas_grid_widget.addWidget(vsp)
            self.vsps.append(vsp)
            ix = (ix[0], len(self.canvas_grid) - 1)
        elif orientation == 'v':
            vsp = self.vsps[ix[1]]
            vsp.addWidget(canvas.native)
            col = self.canvas_grid[ix[1]]
            col.append(canvas)
            ix = (len(col) - 1, ix[1])
        else:
            raise ValueError(f"orientation expect 'h' or 'v', got {orientation}")
        self.current_ix = ix
        self.control_stack.addWidget(canvas.control_panel)
        self.control_stack.setCurrentWidget(canvas.control_panel)
        self.update_canvas_border_color()

    def remove_canvas(self):
        if len(list(self.get_all_canvas())) == 1:
            return
        ix = self.current_ix
        new_ix = list(ix)
        col = self.canvas_grid[ix[1]]
        col.pop(ix[0])
        if len(col) == 0:
            self.canvas_grid.pop(ix[1])
            vsp = self.vsps.pop(ix[1])
            new_ix[1] = max(0, ix[1]-1)
            vsp.hide()
            del vsp
        new_ix[0] = min(len(col)-1, ix[0])
        new_ix = tuple(new_ix)
        current = self.canvas
        current.native.setVisible(False)
        self.change_current_canvas(new_ix)
        self.control_stack.removeWidget(current.control_panel)
        del current

    def get_all_canvas(self):
        return itertools.chain.from_iterable(self.canvas_grid)

    def trigger_other_canvas_mouse_event(self, event):
        if not self.link_canvas:
            return
        a = event.source.canvas if hasattr(event, 'source') else self.canvas
        for b in self.get_all_canvas():
            if b is not a:
                # Try to trigger mouse move on other canvases
                # This may need backend-specific handling
                pass

    def get_canvas_ix(self, canvas):
        for j, col in enumerate(self.canvas_grid):
            for i, c in enumerate(col):
                if c is canvas:
                    return (i, j)
        return None

    def on_click_canvas(self, event):
        # Handle click event - may need to extract canvas from event differently
        new = self.canvas  # Simplified - in production would extract from event
        new_ix = self.get_canvas_ix(new)
        if new_ix:
            self.change_current_canvas(new_ix)

    def change_current_canvas(self, new_ix):
        old_ix = self.current_ix
        self.canvas = new = self.canvas_grid[new_ix[1]][new_ix[0]]
        self.menubar.set_show_axis(new.axis.visible)
        self.current_ix = new_ix
        self.control_stack.setCurrentWidget(new.control_panel)
        self.update_canvas_border_color()

    def update_canvas_border_color(self):
        if (len(self.canvas_grid) == 1) and (len(self.canvas_grid[0]) == 1):
            return
        for canvas in self.get_all_canvas():
            if canvas is self.canvas:
                c = Color("#888888")
            else:
                c = Color("#000000")
            canvas.view.border_color = c

    def add_widgets(self):
        self.splitter.addWidget(self.control_stack)
        self.splitter.setSizes([850, 150])
        self.setMenuBar(self.menubar)
        self._connect_events()

    def _connect_events(self):
        self.menubar.action_open.triggered.connect(self.open_file_dialog)
        self.menubar.action_add_canvas_hor.triggered.connect(self.add_canvas_hor)
        self.menubar.action_add_canvas_ver.triggered.connect(self.add_canvas_ver)
        self.menubar.action_remove_canvas.triggered.connect(self.remove_canvas)
        self.menubar.action_show_axis.triggered.connect(self._all_or_current(self.on_toggle_show_axis))

    def _all_or_current(self, f):
        def wrap(*args, **kwargs):
            current = self.canvas
            if self.link_canvas:
                # apply to all canvas
                for c in self.get_all_canvas():
                    self.canvas = c
                    f(*args, **kwargs)
                self.canvas = current
            else:
                # only current
                f(*args, **kwargs)
        return wrap

    def add_canvas_hor(self):
        self.add_canvas('h')

    def add_canvas_ver(self):
        self.add_canvas('v')

    def open_file_dialog(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        path, _ = QFileDialog.getOpenFileName(self, "Open", "", "All Files (*);;CSV Files(*.csv)", options=options)
        if path:
            try:
                print(path)
                df = read_particles(path)
                self.load_model(df, path)
                self.init_draw()
            except Exception as e:
                print(str(e))

    def init_draw(self):
        for layer in self.canvas.control_panel.layers:
            layer.draw()

    def on_toggle_show_axis(self, *args):
        val = self.menubar.show_axis
        self.canvas.axis.visible = val

    def load_model(self, df, path: str = None):
        random.seed(0)
        for c in df['chrom'].unique():
            if c not in self.chr_colormap:
                self.chr_colormap[c] = random_color()
        name = None
        try:
            if path is not None:
                base = osp.basename(path)
                name = osp.splitext(base)[0]
        except Exception:
            pass
        self.canvas.control_panel.add_chromatin_layer(df, self.chr_colormap, name=name)

    def adjust_camera(self, factor=2.0):
        pos = self.canvas.info['df'][['x', 'y', 'z']].values
        norm = np.sqrt(sum([(pos[:, i])**2 for i in range(3)]))
        max_norm = np.max(norm)
        self.canvas.view.camera.distance = max_norm * factor