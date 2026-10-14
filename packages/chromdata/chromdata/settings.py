"""Package-wide settings: the memory budget of out-of-core work.

::

    import chromdata
    chromdata.settings.memory_budget = "8GB"      # or bytes; None → default
    chromdata.settings.default_batch = "auto"     # or an int (traces per batch)

(``uchrom.settings`` is the same object.)

``memory_budget`` bounds the working memory of the streaming paths:

* ``iter_traces(batch="auto")`` / ``iter_cells(batch="auto")`` size their
  batches so one batch of the selected columns stays within a fraction of
  the budget;
* the streaming writer (:class:`chromdata.stream.ChromDataWriter`, used by
  ``from_fofct(..., out=)`` and the seqFISH+ loader with ``out=``) spills
  appended chunks to disk and sorts each chromosome partition in pieces
  that fit the budget;
* the streaming population callers (:mod:`uchrom.fea.distance`,
  :mod:`uchrom.strc.stream`) size their row bands from it.

The default is the environment variable ``UCHROM_MEMORY_BUDGET`` when set (e.g. ``"12GB"``: for a container
that hides the job's limit, as ``apptainer exec --cleanenv`` hides Slurm's variables), else 50 % of the RAM that is
available (bounded by the job's memory limit under Slurm or in a cgroup) when the budget is first
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


def _job_memory_limit() -> Optional[int]:
    """The memory limit of this process's job, if any: Slurm's ``SLURM_MEM_PER_NODE`` (MB) or
    ``SLURM_MEM_PER_CPU`` x ``SLURM_CPUS_ON_NODE``, and the cgroup limit (v2 ``memory.max``, v1
    ``memory.limit_in_bytes``) minus what the cgroup already uses — the smallest of those found."""
    found = []
    env = os.environ
    try:
        if env.get("SLURM_MEM_PER_NODE"):
            found.append(int(env["SLURM_MEM_PER_NODE"]) << 20)
        elif env.get("SLURM_MEM_PER_CPU") and env.get("SLURM_CPUS_ON_NODE"):
            found.append(int(env["SLURM_MEM_PER_CPU"]) * int(env["SLURM_CPUS_ON_NODE"]) << 20)
    except ValueError:
        pass
    try:
        with open("/proc/self/cgroup") as fh:
            lines = fh.read().splitlines()
    except OSError:
        lines = []
    for line in lines:
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue
        ctrl, path = parts[1], parts[2]
        if ctrl == "":                                              # cgroup v2
            base = f"/sys/fs/cgroup{path}"
            limit, usage = f"{base}/memory.max", f"{base}/memory.current"
        elif "memory" in ctrl.split(","):                           # cgroup v1
            base = f"/sys/fs/cgroup/memory{path}"
            limit, usage = f"{base}/memory.limit_in_bytes", f"{base}/memory.usage_in_bytes"
        else:
            continue
        try:
            with open(limit) as fh:
                raw = fh.read().strip()
            if raw and raw != "max" and int(raw) < (1 << 60):
                used = 0
                try:
                    with open(usage) as fh:
                        used = int(fh.read().strip())
                except (OSError, ValueError):
                    pass
                found.append(max(int(raw) - used, 0))
        except (OSError, ValueError):
            pass
    return min(found) if found else None


def _available_ram() -> int:
    """Free memory: the system's (psutil), bounded by the job's limit when running under Slurm / in a cgroup."""
    try:
        import psutil
        free = int(psutil.virtual_memory().available)
    except ImportError:  # pragma: no cover - psutil is optional
        try:
            free = int(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
        except (ValueError, OSError, AttributeError):
            free = 8 << 30
    job = _job_memory_limit()
    return min(free, job) if job is not None else free


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
            env = os.environ.get("UCHROM_MEMORY_BUDGET")
            self._default = parse_bytes(env) if env else max(256 << 20, _available_ram() // 2)
        return self._default

    @memory_budget.setter
    def memory_budget(self, value) -> None:
        self._memory_budget = None if value is None else parse_bytes(value)

    def resolve_budget(self, value=None) -> int:
        """``value`` (bytes or a string such as ``"2GB"``) or the global budget."""
        return self.memory_budget if value is None else parse_bytes(value)

    def __repr__(self) -> str:
        return (f"chromdata.settings(memory_budget={format_bytes(self.memory_budget)}"
                f"{'' if self._memory_budget is not None else ' (default)'}, "
                f"default_batch={self.default_batch!r})")


settings = Settings()

__all__ = ["Settings", "format_bytes", "parse_bytes", "settings"]
