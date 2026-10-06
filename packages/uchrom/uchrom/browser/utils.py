import importlib
import os.path as osp

from PyQt5 import QtCore, QtGui
import PyQt5


# Provide automatic signal function selection for PyQtX/PySide2
pyqtsignal = QtCore.pyqtSignal if hasattr(QtCore, 'pyqtSignal') else QtCore.Signal


def get_qapp(style='qdarkgraystyle'):
    qapp = PyQt5.QtWidgets.QApplication(["1"])
    # macOS Dock icon (and taskbar icon on Linux/Windows): set on the
    # QApplication so it applies before any window is shown.
    try:
        svg_path = osp.join(osp.dirname(osp.abspath(__file__)), 'uc.svg')
        if osp.exists(svg_path):
            qapp.setWindowIcon(QtGui.QIcon(svg_path))
        qapp.setApplicationName("U-Chrom")
        qapp.setApplicationDisplayName("U-Chrom")
    except Exception:
        pass
    style_mod = importlib.import_module(style)
    qapp.setStyleSheet(style_mod.load_stylesheet())
    return qapp
