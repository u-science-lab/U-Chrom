"""Deprecated: the web browser is the ``uchrom-browser`` package (``import uchrom_browser``).

``uchrom.browser.web`` and its modules (``uchrom.browser.web.server``, ``.data``, ...) are the ``uchrom_browser``
modules under their former names, so existing code keeps working.
"""

import importlib
import sys
import warnings

try:
    import uchrom_browser as _browser
except ModuleNotFoundError as exc:          # pragma: no cover - depends on the installation
    raise ImportError('the web browser is the uchrom-browser package: pip install "u-chrom[web]"') from exc

warnings.warn("uchrom.browser.web is deprecated: the web browser is the uchrom_browser package",
              DeprecationWarning, stacklevel=2)

for _name in ("client", "control", "data", "files", "hosted", "server", "store_tree"):
    _module = importlib.import_module(f"uchrom_browser.{_name}")
    sys.modules[f"{__name__}.{_name}"] = _module
    globals()[_name] = _module

from uchrom_browser import (DatasetStore, create_app, decode_geometry, encode_geometry,  # noqa: E402,F401
                            serve)

__all__ = ["DatasetStore", "create_app", "decode_geometry", "encode_geometry", "serve"]
