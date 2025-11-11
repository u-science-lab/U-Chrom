import random
import itertools
import os.path as osp
import json

from PyQt5 import QtGui
import numpy as np

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QFileDialog, QMainWindow, QSplitter, QStackedWidget,
                             QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton)

from nucbox.io import read_particles
from .canvas import Canvas
from .menubar import MenuBar


HERE = osp.dirname(osp.abspath(__file__))


def random_color():
    return "#"+''.join([random.choice('0123456789ABCDEF') for _ in range(6)])


class MainWindow(QMainWindow):

    def __init__(self, canvas_only=False):
        QMainWindow.__init__(self)

        self.chr_colormap = {}

        self.resize(1100, 700)
        self.setWindowTitle('NucBrowser')

        self.splitter = QSplitter(Qt.Horizontal)
        self.control_stack = QStackedWidget()

        self.canvas_grid = []
        self.vsps = []
        self.canvas_grid_widget = QSplitter(Qt.Horizontal)
        self.current_ix = (0, -1)
        self.canvas = None
        self.add_canvas('h')

        self.splitter.addWidget(self.canvas_grid_widget)

        # Create a container widget for central widget
        self.central_container = QWidget()
        self.central_layout = QVBoxLayout(self.central_container)
        self.central_layout.setContentsMargins(0, 0, 0, 0)
        self.central_layout.addWidget(self.splitter)

        # Create navigation panel (will be overlaid on top)
        self.navigation_panel = self._create_navigation_panel()

        self.setCentralWidget(self.central_container)
        self.setWindowIcon(QtGui.QIcon(osp.join(HERE, 'nucbox.svg')))
        self.menubar = MenuBar(self)
        if not canvas_only:
            self.add_widgets()

    @property
    def link_canvas(self):
        return self.menubar.link_canvas

    def _create_navigation_panel(self):
        """Create the initial navigation panel displayed at startup."""
        panel = QWidget()
        panel.setObjectName("NavigationPanel")

        # Set a fixed width for the panel to ensure proper centering
        panel.setFixedWidth(400)

        # Main layout
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("NucBox")
        title.setStyleSheet("font-size: 48px; font-weight: bold; color: #FFFFFF;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Version
        try:
            from nucbox import __version__
            version_text = f"version: {__version__}"
        except:
            version_text = "version: 0.1.1"

        version = QLabel(version_text)
        version.setStyleSheet("font-size: 18px; color: #888888;")
        version.setAlignment(Qt.AlignCenter)
        layout.addWidget(version)

        # Add spacing before buttons
        layout.addSpacing(20)

        # Buttons container
        buttons_layout = QHBoxLayout()
        buttons_layout.setAlignment(Qt.AlignCenter)
        buttons_layout.setSpacing(15)

        # Open structure button
        btn_open = QPushButton("Open a structure")
        btn_open.setFixedSize(165, 50)
        btn_open.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 2px solid #FFFFFF;
                color: #FFFFFF;
                font-size: 14px;
                padding: 10px 20px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """)
        btn_open.clicked.connect(self.open_file_dialog)
        buttons_layout.addWidget(btn_open)

        # Load session button
        btn_load = QPushButton("Load session")
        btn_load.setFixedSize(165, 50)
        btn_load.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 2px solid #FFFFFF;
                color: #FFFFFF;
                font-size: 14px;
                padding: 10px 20px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """)
        btn_load.clicked.connect(self.load_session_dialog)
        buttons_layout.addWidget(btn_load)

        layout.addLayout(buttons_layout)

        panel.setLayout(layout)

        # Position panel in the center of main window
        panel.setParent(self.central_container)
        panel.setAttribute(Qt.WA_StyledBackground, True)
        # Initially hidden, will be shown in add_widgets
        panel.hide()

        return panel

    def _center_navigation_panel(self):
        """Center the navigation panel on the main window."""
        if self.navigation_panel and self.central_container:
            # Ensure the panel has been laid out and has a proper size
            self.navigation_panel.adjustSize()

            container_size = self.central_container.size()
            panel_size = self.navigation_panel.size()

            x = (container_size.width() - panel_size.width()) // 2
            y = (container_size.height() - panel_size.height()) // 2

            self.navigation_panel.move(max(0, x), max(0, y))
            self.navigation_panel.raise_()  # Ensure panel is on top

    def _show_navigation_panel(self):
        """Show the navigation panel."""
        if self.navigation_panel:
            self.navigation_panel.show()
            # Use a timer to ensure the layout is complete before centering
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, self._center_navigation_panel)

    def _hide_navigation_panel(self):
        """Hide the navigation panel."""
        if self.navigation_panel:
            self.navigation_panel.hide()

    def resizeEvent(self, event):
        """Handle window resize to keep navigation panel centered."""
        super().resizeEvent(event)
        if self.navigation_panel and self.navigation_panel.isVisible():
            self._center_navigation_panel()

    def add_canvas(self, orientation='h'):
        canvas = Canvas()
        canvas.create_native()
        canvas.native.setParent(self)
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
        a = event.source.canvas
        for b in self.get_all_canvas():
            if b is not a:
                for wref, name in b.view.events.mouse_move.callbacks:
                    if name == "viewbox_mouse_event":
                        wref().viewbox_mouse_event(event)
                        break

    def get_canvas_ix(self, canvas):
        for j, col in enumerate(self.canvas_grid):
            for i, c in enumerate(col):
                if c is canvas:
                    return (i, j)
        return None

    def on_click_canvas(self, event):
        new = event.source.canvas
        new_ix = self.get_canvas_ix(new)
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
            canvas.view.border_color = "#888888" if canvas is self.canvas else "#000000"

    def add_widgets(self):
        self.splitter.addWidget(self.control_stack)
        self.splitter.setSizes([850, 150])
        # Hide the entire splitter (canvas + layers panel) initially until a structure is loaded
        self.splitter.setVisible(False)
        # Show the navigation panel initially
        self._show_navigation_panel()
        self.setMenuBar(self.menubar)
        self._connect_events()

    def _connect_events(self):
        self.menubar.action_open.triggered.connect(self.open_file_dialog)
        self.menubar.action_save_session.triggered.connect(self.save_session_dialog)
        self.menubar.action_load_session.triggered.connect(self.load_session_dialog)
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

    def save_session_dialog(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        path, _ = QFileDialog.getSaveFileName(self, "Save Session", "", "NucBrowser Session (*.json);;All Files (*)", options=options)
        if path:
            try:
                self.save_session(path)
            except Exception as e:
                print(str(e))

    def load_session_dialog(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        path, _ = QFileDialog.getOpenFileName(self, "Load Session", "", "NucBrowser Session (*.json);;All Files (*)", options=options)
        if path:
            try:
                # Open session in a new window instead of current
                win = MainWindow()
                win.load_session_file(path)
                win.show()
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
        layer = self.canvas.control_panel.add_chromatin_layer(df, self.chr_colormap, name=name)
        try:
            if path is not None and hasattr(layer, 'cache_props'):
                layer.cache_props['data_path'] = path
        except Exception:
            pass
        # Hide navigation panel and show the canvas and layers panel when a structure is loaded
        self._hide_navigation_panel()
        self.splitter.setVisible(True)
        self.control_stack.setVisible(True)

    def save_session(self, path: str):
        try:
            def _records_from_df(df):
                try:
                    # Only keep common columns to keep size reasonable
                    cols = [c for c in ['x', 'y', 'z', 'chrom', 'start', 'end'] if c in df.columns]
                    if len(cols) == 0:
                        return None
                    return df[cols].to_dict('records')
                except Exception:
                    return None

            canvases = []
            for cv in self.get_all_canvas():
                # Serialize layers
                cv_layers = []
                try:
                    for layer in getattr(cv.control_panel, 'layers', []):
                        try:
                            entry = {
                                'type': 'Chromatin',
                                'name': getattr(layer, 'name', None),
                                'locked': getattr(layer, 'locked', False),
                            }
                            cache = getattr(layer, 'cache_props', {}) if hasattr(layer, 'cache_props') else {}
                            if isinstance(cache, dict):
                                entry['style'] = cache.get('style')
                                entry['width'] = cache.get('width')
                                entry['opacity'] = cache.get('opacity')
                                entry['color_mode'] = cache.get('color_mode')
                                entry['single_color'] = cache.get('single_color')
                                entry['chr_colormap'] = cache.get('chr_colormap', {})
                                entry['data_path'] = cache.get('data_path')
                                # Include a compact props copy for easy restore
                                entry['props'] = {
                                    k: v for k, v in cache.items() if k in ['style', 'width', 'opacity', 'color_mode', 'single_color']
                                }
                            # Embed data if available
                            df = getattr(layer, 'df', None)
                            if df is not None:
                                records = _records_from_df(df)
                                entry['df_records'] = records
                            cv_layers.append(entry)
                        except Exception:
                            continue
                except Exception:
                    pass

                # Camera approximation and axis visibility
                try:
                    dist = float(getattr(cv.view.camera, 'distance', 50.0))
                except Exception:
                    dist = 50.0
                canvas_entry = {
                    'layers': cv_layers,
                    'camera': {
                        # Approximate position with distance along Z
                        'position': [0.0, 0.0, dist]
                    },
                    'axis_visible': bool(getattr(cv.axis, 'visible', False))
                }
                canvases.append(canvas_entry)

            data = {
                'version': 1,
                'chr_colormap': self.chr_colormap,
                'canvases': canvases
            }

            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(str(e))

    def load_session_file(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Basic validation
            if not isinstance(data, dict):
                print("Invalid session format: root is not an object")
                return
            version = data.get("version")
            try:
                print(f"Loaded session: {version}")
            except Exception:
                pass

            canvases = data.get("canvases", [])
            if not isinstance(canvases, list):
                print("Invalid session format: 'canvases' is not a list")
                return

            # Helper to coerce a DataFrame from records
            def _df_from_records(records):
                try:
                    import pandas as pd
                    if not isinstance(records, list):
                        return None
                    df = pd.DataFrame.from_records(records)
                    # Ensure required columns exist
                    for col in ["chrom", "x", "y", "z"]:
                        if col not in df.columns:
                            return None
                    # Normalize types
                    df["chrom"] = df["chrom"].astype(str)
                    return df
                except Exception:
                    return None

            # Iterate canvases as stored
            for i, cv in enumerate(canvases):
                if i > 0:
                    # Create a new canvas to the right for each additional canvas
                    self.add_canvas('h')
                # Each canvas becomes current via add_canvas; apply per-canvas settings below
                layers = []
                try:
                    layers = cv.get("layers", []) if isinstance(cv, dict) else []
                except Exception:
                    layers = []

                # Restore layers
                for layer_desc in layers:
                    try:
                        if not isinstance(layer_desc, dict):
                            continue
                        layer_type = layer_desc.get("type")
                        if layer_type != "Chromatin":
                            continue
                        df = None
                        data_path = layer_desc.get("data_path")
                        if isinstance(data_path, str) and len(data_path) > 0:
                            try:
                                df = read_particles(data_path)
                            except Exception as e:
                                print(f"Failed to read data_path: {e}")
                        if df is None:
                            df_records = layer_desc.get("df_records")
                            df = _df_from_records(df_records)
                        if df is None:
                            # Skip if no data available
                            continue

                        # Colormap: prefer layer-specific; fallback to global if present
                        layer_colormap = layer_desc.get("chr_colormap")
                        if not isinstance(layer_colormap, dict):
                            layer_colormap = data.get("chr_colormap", {}) if isinstance(data.get("chr_colormap"), dict) else {}

                        # Basic props
                        width = layer_desc.get("width")
                        style = layer_desc.get("style")
                        name = layer_desc.get("name")
                        if not isinstance(width, (int, float)):
                            width = None
                        if not isinstance(style, str):
                            style = None

                        # Add layer
                        new_layer = self.canvas.control_panel.add_chromatin_layer(
                            df, layer_colormap, parent=None, name=name, width=width, style=style
                        )

                        # Apply extended props if provided
                        props = layer_desc.get("props") if isinstance(layer_desc.get("props"), dict) else {}
                        color_mode = props.get("color_mode", layer_desc.get("color_mode"))
                        single_color = props.get("single_color", layer_desc.get("single_color"))
                        opacity = props.get("opacity", layer_desc.get("opacity"))

                        try:
                            if isinstance(color_mode, str):
                                new_layer.cache_props["color_mode"] = color_mode
                            if isinstance(single_color, str):
                                new_layer.cache_props["single_color"] = single_color
                            if isinstance(opacity, (int, float)):
                                new_layer.cache_props["opacity"] = float(opacity)
                            # Ensure current colormap persists
                            new_layer.cache_props["chr_colormap"] = layer_colormap
                            # Redraw to apply props
                            new_layer.remove()
                            new_layer.draw()
                        except Exception as e:
                            print(f"Failed to apply layer props: {e}")
                    except Exception as e:
                        print(f"Failed to restore a layer: {e}")

                # Restore per-canvas axis visibility
                try:
                    axis_vis = cv.get("axis_visible") if isinstance(cv, dict) else None
                    if isinstance(axis_vis, bool):
                        self.canvas.axis.visible = axis_vis
                except Exception:
                    pass

                # Restore camera (approximate distance from position if provided)
                try:
                    cam = cv.get("camera") if isinstance(cv, dict) else None
                    if isinstance(cam, dict):
                        pos = cam.get("position")
                        if isinstance(pos, list) and len(pos) == 3:
                            try:
                                import math
                                dist = math.sqrt(sum([float(pos[i])**2 for i in range(3)]))
                                self.canvas.view.camera.distance = dist
                            except Exception:
                                pass
                except Exception:
                    pass

            # Hide navigation panel and show the canvas and layers panel when a session is loaded (if any layers were loaded)
            if len(canvases) > 0:
                has_layers = False
                for cv in canvases:
                    layers = cv.get("layers", []) if isinstance(cv, dict) else []
                    if len(layers) > 0:
                        has_layers = True
                        break
                if has_layers:
                    self._hide_navigation_panel()
                    self.splitter.setVisible(True)
                    self.control_stack.setVisible(True)
        except Exception as e:
            print(str(e))

    def adjust_camera(self, factor=2.0):
        pos = self.canvas.info['df'][['x', 'y', 'z']].values
        norm = np.sqrt(sum([(pos[:, i])**2 for i in range(3)]))
        max_norm = np.max(norm)
        self.canvas.view.camera.distance = max_norm * factor

