from PyQt5.QtWidgets import (QAction, QMenu, QMenuBar)
from ..widgets.about import About


class MenuBar(QMenuBar):

    def __init__(self, *args, **kwargs):
        QMenuBar.__init__(self, *args, **kwargs)

        self.link_canvas = False
        self.show_axis = False

        self.action_open = QAction("&Open...", self)
        self.action_add_canvas_hor = QAction("&Add canvas(right)", self)
        self.action_add_canvas_ver = QAction("&Add canvas(below)", self)
        self.action_remove_canvas = QAction("&Remove canvas", self)
        self.action_change_link_status = QAction("&Link canvases", self)
        self.action_show_axis = QAction("&Show axis", self)
        self.action_show_about = QAction("&About", self)

        file_menu = QMenu("&File", self)
        file_menu.addAction(self.action_open)
        self.addMenu(file_menu)
        canvas_menu = QMenu("&Canvas", self)
        canvas_menu.addAction(self.action_add_canvas_hor)
        canvas_menu.addAction(self.action_add_canvas_ver)
        canvas_menu.addAction(self.action_remove_canvas)
        canvas_menu.addAction(self.action_change_link_status)
        canvas_menu.addAction(self.action_show_axis)
        self.addMenu(canvas_menu)
        help_menu = QMenu("&Help", self)
        help_menu.addAction(self.action_show_about)
        self.addMenu(help_menu)

        self.about_page = About()
        self._connect_events()

    def _connect_events(self):
        self.action_show_about.triggered.connect(self.open_about)
        self.action_change_link_status.triggered.connect(self.toggle_canvas_link)
        self.action_show_axis.triggered.connect(self.toggle_show_axis)

    def open_about(self):
        self.about_page.show()

    def toggle_canvas_link(self):
        self.link_canvas = not self.link_canvas
        if self.link_canvas:
            self.action_change_link_status.setText("&Unlink canvases")
        else:
            self.action_change_link_status.setText("&Link canvases")

    def set_show_axis(self, val):
        self.show_axis = val
        if self.show_axis:
            self.action_show_axis.setText("&Hidden axis")
        else:
            self.action_show_axis.setText("&Show axis")

    def toggle_show_axis(self):
        self.set_show_axis(not self.show_axis)
