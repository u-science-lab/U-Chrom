import importlib

from PyQt5 import QtCore
import PyQt5


# Provide automatic signal function selection for PyQtX/PySide2
pyqtsignal = QtCore.pyqtSignal if hasattr(QtCore, 'pyqtSignal') else QtCore.Signal


def get_qapp(style='qdarkgraystyle'):
    qapp = PyQt5.QtWidgets.QApplication(["1"])
    style_mod = importlib.import_module(style)
    qapp.setStyleSheet(style_mod.load_stylesheet())
    return qapp
