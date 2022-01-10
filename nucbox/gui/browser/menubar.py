from PyQt5.QtWidgets import (QAction, QMenu, QMenuBar)


class MenuBar(QMenuBar):
    def __init__(self, *args, **kwargs):
        QMenuBar.__init__(self, *args, **kwargs)

        self.action_open = QAction("&Open...", self)
        self.action_add_canvas_hor = QAction("&Add canvas(right)", self)
        self.action_add_canvas_ver = QAction("&Add canvas(below)", self)
        self.action_remove_canvas = QAction("&Remove canvas", self)
        self.action_change_link_status = QAction("&Link canvases", self)

        file_menu = QMenu("&File", self)
        file_menu.addAction(self.action_open)
        self.addMenu(file_menu)
        canvas_menu = QMenu("&Canvas", self)
        canvas_menu.addAction(self.action_add_canvas_hor)
        canvas_menu.addAction(self.action_add_canvas_ver)
        canvas_menu.addAction(self.action_remove_canvas)
        canvas_menu.addAction(self.action_change_link_status)
        self.addMenu(canvas_menu)
        help_menu = QMenu("&Help", self)
        self.addMenu(help_menu)
