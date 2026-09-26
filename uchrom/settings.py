"""Package-wide settings: the memory budget of out-of-core work.

::

    import uchrom
    uchrom.settings.memory_budget = "8GB"      # or bytes; None → default
    uchrom.settings.default_batch = "auto"     # or an int (traces per batch)

``memory_budget`` bounds the working memory of the streaming paths:

* ``iter_traces(batch="auto")`` / ``iter_cells(batch="auto")`` size their
  batches so one batch of the selected columns stays within a fraction of
  the budget;
* the streaming writer (:class:`uchrom.core.stream.ChromDataWriter`, used by
  ``from_fofct(..., out=)`` and the seqFISH+ loader with ``out=``) spills
  appended chunks to disk and sorts each chromosome partition in pieces
  that fit the budget;
* the streaming population callers (:mod:`uchrom.fea.distance`,
  :mod:`uchrom.strc.stream`) size their row bands from it.

The default is 50 % of the RAM that is available when the budget is first
read (``psutil``; without it, 50 % of the physical RAM).  The budget is a
target for the large arrays of those paths, not a hard cap on the process:
Python, the small tables, and per-chromosome ``n_bins²`` outputs come on
top.
"""

from __future__ import annotations

import os
import re
from typing import Optional, Union

_UNITS = {"": 1, "B": 1, "K": 1 << 10, "KB": 1 << 10, "KIB": 1 << 10, "M": 1 << 20,
          "MB": 1 << 20, "MIB": 1 << 20, "G": 1 << 30, "GB": 1 << 30, "GIB": 1 << 30,
          "T": 1 << 40, "TB": 1 << 40, "TIB": 1 << 40}


def parse_bytes(value: Union[int, float, str]) -> int:
    """``"8GB"`` / ``"512 MiB"`` / ``2e9`` → bytes (binary units: 1 GB = 2**30)."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value <= 0:
            raise ValueError("memory size must be positive")
        return int(value)
    m = re.fullmatch(r"\s*([0-9]*\.?[0-9]+(?:[eE][+-]?\d+)?)\s*([A-Za-z]*)\s*", str(value))
    if not m or m.group(2).upper() not in _UNITS:
        raise ValueError(f"cannot parse memory size {value!r} (e.g. '8GB', '512MB', 2e9)")
    out = int(float(m.group(1)) * _UNITS[m.group(2).upper()])
    if out <= 0:
        raise ValueError("memory size must be positive")
    return out


def format_bytes(n: int) -> str:
    for unit, div in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= div:
            return f"{n / div:.1f} {unit}"
    return f"{n} B"


def _available_ram() -> int:
    try:
        import psutil
        return int(psutil.virtual_memory().available)
    except ImportError:  # pragma: no cover - psutil is optional
        try:
            return int(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
        except (ValueError, OSError, AttributeError):
            return 8 << 30


class Settings:
    """Mutable settings object; see the module docstring."""

    def __init__(self):
        self._memory_budget: Optional[int] = None
        self._default: Optional[int] = None
        self.default_batch: Union[str, int] = "auto"

    @property
    def memory_budget(self) -> int:
        """Working-memory budget of the streaming paths, in bytes."""
        if self._memory_budget is not None:
            return self._memory_budget
        if self._default is None:
            self._default = max(256 << 20, _available_ram() // 2)
        return self._default

    @memory_budget.setter
    def memory_budget(self, value) -> None:
        self._memory_budget = None if value is None else parse_bytes(value)

    def resolve_budget(self, value=None) -> int:
        """``value`` (bytes or a string such as ``"2GB"``) or the global budget."""
        return self.memory_budget if value is None else parse_bytes(value)

    def __repr__(self) -> str:
        return (f"uchrom.settings(memory_budget={format_bytes(self.memory_budget)}"
                f"{'' if self._memory_budget is not None else ' (default)'}, "
                f"default_batch={self.default_batch!r})")


settings = Settings()

__all__ = ["Settings", "format_bytes", "parse_bytes", "settings"]
