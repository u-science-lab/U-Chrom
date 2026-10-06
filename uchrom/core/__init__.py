"""Deprecated: the data model is the ``chromdata`` package.

``uchrom.core`` and its modules (``uchrom.core.cdata``, ``uchrom.core.zarrcd``, ...) are the ``chromdata`` modules
under their former names -- the same module objects, private names included -- so existing code keeps working;
import from ``chromdata`` instead.  ``uchrom.core.atlas`` is :mod:`chromdata.catalog` (the atlas page's thumbnails
and site moved to ``apps/atlas/build.py``) and ``uchrom.core.convention`` is :mod:`uchrom.convention`.
"""

import importlib
import sys
import warnings

warnings.warn("uchrom.core is deprecated: the data model is the chromdata package (from chromdata import ChromData)",
              DeprecationWarning, stacklevel=2)

_ALIASES = {name: f"chromdata.{name}" for name in (
    "backed", "bins", "cdata", "cellspatial", "embedded", "floatcodec", "intervals", "project", "remote", "results",
    "settings", "stream", "zarrcd", "_parallel")}
_ALIASES.update({"atlas": "chromdata.catalog", "convention": "uchrom.convention"})

for _name, _target in _ALIASES.items():
    _module = importlib.import_module(_target)
    sys.modules[f"{__name__}.{_name}"] = _module
    globals()[_name] = _module

from chromdata import ChromData, ResultRecord, ResultsStore, UChromProject  # noqa: E402

__all__ = ["ChromData", "ResultRecord", "ResultsStore", "UChromProject"]
