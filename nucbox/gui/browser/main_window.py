import random
import itertools
import os.path as osp
from copy import copy

from PyQt5 import QtGui
import pandas as pd
import numpy as np
from vispy.color import Color

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QFileDialog, QMainWindow, QSplitter, QVBoxLayout, QWidget)

from nucbox.io import read_particles
from .canvas import Canvas
from .range_list import RangeList
from .obj_panel import ObjPropPanel
from .layer_panel import LayerPanel
from .menubar import MenuBar


HERE = osp.dirname(osp.abspath(__file__))


def random_color():
    return "#"+''.join([random.choice('0123456789ABCDEF') for _ in range(6)])


class ControlPanel(QWidget):
    def __init__(self, obj_panel, layer_panel):
        super().__init__()
        layout = QVBoxLayout()
        layout.addWidget(layer_panel, 1)
        layout.addWidget(obj_panel, 2)
        self.setLayout(layout)


class MainWindow(QMainWindow):

    def __init__(self, canvas_only=False):
        QMainWindow.__init__(self)

        self.chr_colormap = {}
        self.chroms = []

        self.resize(1100, 700)
        self.setWindowTitle('NucBrowser')

        self.splitter = QSplitter(Qt.Horizontal)

        self.canvas_grid = []
        self.vsps = []
        self.canvas_grid_widget = QSplitter(Qt.Horizontal)
        self.current_ix = (0, -1)
        self.canvas = None
        self.add_canvas('h')
        self.link_canvas = False

        self.splitter.addWidget(self.canvas_grid_widget)
        self.setCentralWidget(self.splitter)
        self.setWindowIcon(QtGui.QIcon(osp.join(HERE, '../nucbox.svg')))
        self.menubar = MenuBar(self)
        self.props = ObjPropPanel()
        self.layer_panel = LayerPanel()
        self.control_panel = ControlPanel(self.props, self.layer_panel)
        if not canvas_only:
            self.add_widgets()

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
        self.canvas.native.setVisible(False)
        del self.canvas
        self.change_current_canvas(new_ix, force_update_props=True)

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

    def change_current_canvas(self, new_ix, force_update_props=False):
        old_ix = self.current_ix
        self.canvas = new = self.canvas_grid[new_ix[1]][new_ix[0]]
        if (force_update_props or (new_ix != old_ix)) and (new.info['df'] is not None):
            self.props.model_style_select.setCurrentText(new.cache_props['style'])
            self.props.width_control.setValue(new.cache_props['width'])
            self.props.opacity_control.setValue(new.cache_props['opacity'])
            self.show_only_ranges.setRanges(new.info['show_only_ranges'], block_signal=True)
        self.current_ix = new_ix
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
        self.splitter.addWidget(self.control_panel)
        self.show_only_ranges = RangeList("Show only ranges", self.chroms)
        self.setMenuBar(self.menubar)
        self._connect_events()

    def _connect_events(self):
        self.props.signal_show_model.connect(self._all_or_current(self.on_toggle_show_model))
        self.props.signal_show_axis.connect(self._all_or_current(self.on_toggle_show_axis))
        self.props.signal_width.connect(self._all_or_current(self.on_width_changed))
        self.props.signal_opacity.connect(self._all_or_current(self.on_opacity_changed))
        self.props.signal_show_label.connect(self._all_or_current(self.on_toggle_show_label))
        self.props.signal_label_font_size.connect(self._all_or_current(self.on_label_size_changed))
        self.props.signal_label_shift.connect(self._all_or_current(self.on_label_shift_changed))
        self.props.signal_show_only.connect(self._all_or_current(self.open_show_only))
        self.props.signal_change_style.connect(self._all_or_current(self.on_model_style_change))
        self.show_only_ranges.signal_item_changed.connect(self._all_or_current(self.on_show_only_ranges_changed))
        self.menubar.action_open.triggered.connect(self.open_file_dialog)
        self.menubar.action_add_canvas_hor.triggered.connect(self.add_canvas_hor)
        self.menubar.action_add_canvas_ver.triggered.connect(self.add_canvas_ver)
        self.menubar.action_change_link_status.triggered.connect(self.change_canvas_link)
        self.menubar.action_remove_canvas.triggered.connect(self.remove_canvas)

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

    def change_canvas_link(self):
        self.link_canvas = not self.link_canvas
        if self.link_canvas:
            self.menubar.action_change_link_status.setText("&Unlink canvases")
        else:
            self.menubar.action_change_link_status.setText("&Link canvases")

    def add_canvas_hor(self):
        self.add_canvas('h')

    def add_canvas_ver(self):
        self.add_canvas('v')

    def on_model_style_change(self):
        style = self.props.model_style_select.currentText()
        self.canvas.remove_model()
        self.canvas.draw_model(style=style)
        if style == 'line':
            self.props.width_control.setMaximum(20.0)
            self.props.width_control.setMinimum(1.0)
            self.props.width_control.setSingleStep(1.0)
            self.props.width_control.setValue(1.0)
        elif style == 'points':
            self.props.width_control.setMaximum(2.0)
            self.props.width_control.setMinimum(0)
            self.props.width_control.setSingleStep(0.1)
            self.props.width_control.setValue(0.5)
        elif style == 'tube':
            self.props.width_control.setMaximum(2.0)
            self.props.width_control.setMinimum(0)
            self.props.width_control.setSingleStep(0.05)
            self.props.width_control.setValue(0.1)

    def on_show_only_ranges_changed(self):
        ranges = self.show_only_ranges.ranges
        self.canvas.info['show_only_ranges'] = copy(ranges)
        df = self.canvas.info['df']
        if len(ranges) == 0:
            df_ = df
        elif self.show_only_ranges.reverse_ck.isChecked():
            ix = np.full(df.shape[0], True)
            for gr in ranges:
                sdf = df[(df['chrom'] == gr.chr) & (df['start'] >= gr.start) & (df['end'] <= gr.end)]
                ix[sdf.index] = False
            df_ = df[ix]
        else:
            sub_dfs = []
            for gr in ranges:
                sdf = df[(df['chrom'] == gr.chr) & (df['start'] >= gr.start) & (df['end'] <= gr.end)]
                sub_dfs.append(sdf)
            df_ = pd.concat(sub_dfs).sort_values(by="start")
        self.on_data_changed(df_)

    def open_show_only(self):
        self.show_only_ranges.show()

    def open_file_dialog(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        path, _ = QFileDialog.getOpenFileName(self, "Open", "", "All Files (*);;CSV Files(*.csv)", options=options)
        if path:
            print(path)
            df = read_particles(path)
            self.load_model(df)
            self.init_draw()
            self.update_view()

    def init_draw(self):
        self.canvas.remove_model()
        self.canvas.draw_model(df=self.canvas.info['df'], chr_colormap=self.chr_colormap, style='line', width=1)
        self.canvas.draw_label(self.canvas.info['df'], color=self.chr_colormap)

    def on_data_changed(self, df=None):
        if df is None:
            df = self.canvas.info['df']
        self.canvas.remove_model()
        self.canvas.remove_label()
        self.canvas.draw_model(df=df)
        self.on_toggle_show_model()
        self.canvas.draw_label(df, color=self.chr_colormap)
        self.on_toggle_show_label()

    def update_view(self):
        self.on_model_style_change()
        self.on_toggle_show_model()
        self.on_toggle_show_axis()
        self.on_width_changed()
        self.on_opacity_changed()
        self.on_toggle_show_label()
        self.on_label_size_changed()
        self.on_label_shift_changed()

    def on_label_shift_changed(self):
        val = self.props.label_shift_control.value()
        for i, l in enumerate(self.canvas.labels):
            ori = self.canvas.label_ori_pos[i]
            l.pos = ori * (1+val)

    def on_label_size_changed(self):
        val = self.props.label_size_control.value()
        self.canvas.set_label_props('font_size', val)

    def on_toggle_show_label(self):
        val = self.props.show_label_ckbox.isChecked()
        self.canvas.set_label_props('visible', val)

    def on_opacity_changed(self):
        val = self.props.opacity_control.value()
        self.canvas.set_model_props('opacity', val)
        self.canvas.cache_props['opacity'] = val

    def on_width_changed(self):
        style = self.props.model_style_select.currentText()
        width = self.props.width_control.value()
        self.canvas.cache_props['width'] = width
        for l in self.canvas.lines:
            if style == "line":
                l.set_data(width=width)
            else:
                self.canvas.remove_model()
                self.canvas.draw_model(width=width)
                self.on_opacity_changed()

    def on_toggle_show_model(self):
        val = self.props.show_model_ckbox.isChecked()
        self.canvas.set_model_props('visible', val)

    def on_toggle_show_axis(self):
        val = self.props.show_axis_ckbox.isChecked()
        self.canvas.axis.visible = val

    def load_model(self, df):
        self.canvas.info['df'] = df
        self.chroms.clear()
        for chr in list(df['chrom'].unique()):
            self.chroms.append(chr)
        for c in self.chroms:
            if c not in self.chr_colormap:
                self.chr_colormap[c] = random_color()

    def adjust_camera(self, factor=2.0):
        pos = self.canvas.info['df'][['x', 'y', 'z']].values
        norm = np.sqrt(sum([(pos[:, i])**2 for i in range(3)]))
        max_norm = np.max(norm)
        self.canvas.view.camera.distance = max_norm * factor

