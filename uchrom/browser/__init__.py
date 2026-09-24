"""U-Chrom structure browser.

Two front ends share this package:

* desktop — PyVista + PyQt5 (``MainWindow``; ``browser`` extra)
* web     — FastAPI + Three.js (:mod:`uchrom.browser.web`; ``web`` extra)

Qt is imported lazily so the web browser works without PyQt5 installed.
"""

__all__ = ["MainWindow", "get_qapp"]


def __getattr__(name):
    if name == "MainWindow":
        from .main_window import MainWindow
        return MainWindow
    if name == "get_qapp":
        from .utils import get_qapp
        return get_qapp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
