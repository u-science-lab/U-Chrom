"""Deprecated alias for :mod:`uchrom_discovery`.

Auto-discovery now ships as the separate ``uchrom-discovery`` package
(``discovery/`` in the U-Chrom repository), so the core toolkit no longer
depends on LLM backends.  This shim keeps ``uchrom.auto_discovery`` and
its submodules importable for one release; import ``uchrom_discovery``
instead.
"""

import importlib
import pkgutil
import sys
import warnings

try:
    import uchrom_discovery as _impl
except ImportError as exc:  # pragma: no cover - depends on environment
    raise ImportError(
        "uchrom.auto_discovery moved to the separate 'uchrom-discovery' package. "
        "Install it with `pip install -e discovery/` from the U-Chrom repository "
        "and import `uchrom_discovery`."
    ) from exc

warnings.warn(
    "uchrom.auto_discovery is deprecated; import uchrom_discovery instead.",
    DeprecationWarning,
    stacklevel=2,
)

for _mod in pkgutil.iter_modules(_impl.__path__):
    if _mod.name != "__main__":
        sys.modules[f"{__name__}.{_mod.name}"] = importlib.import_module(
            f"uchrom_discovery.{_mod.name}"
        )

from uchrom_discovery import *  # noqa: E402,F401,F403
from uchrom_discovery import __all__  # noqa: E402,F401
