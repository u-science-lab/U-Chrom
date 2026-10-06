"""U-Chrom structure browser.

* desktop — PyVista + PyQt5 (``MainWindow``; ``browser`` extra), here;
* web     — the ``uchrom-browser`` package (``import uchrom_browser``; ``web`` extra).  ``python -m uchrom.browser
  --web`` starts it, and ``connect()`` / ``Workspace`` / ``BrowserError`` are its client's, so existing code keeps
  working.

Qt is imported lazily so the web browser works without PyQt5 installed.
"""

__all__ = ["MainWindow", "get_qapp", "connect", "Workspace", "BrowserError"]


def __getattr__(name):
    if name in ("connect", "Workspace", "BrowserError"):
        from . import client
        return getattr(client, name)
    if name == "MainWindow":
        from .main_window import MainWindow
        return MainWindow
    if name == "get_qapp":
        from .utils import get_qapp
        return get_qapp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
