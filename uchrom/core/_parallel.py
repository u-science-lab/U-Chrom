"""A shared thread pool and multi-threaded gathers for large spot columns.

numpy releases the GIL in ``np.take`` / ``np.repeat`` for non-object
dtypes, so a gather of millions of rows split into blocks runs in parallel
(the readers use it to materialise loci and derived spot columns)."""

from __future__ import annotations

import os
from typing import Optional

import numpy as np

_POOL = None
#: gathers of at least this many rows are split into blocks run in threads
PARALLEL_MIN_ROWS = 1 << 20
_BLOCK = 1 << 19


def pool():
    """Shared thread pool (the zarr readers' row-group tasks use it too)."""
    global _POOL
    if _POOL is None:
        from concurrent.futures import ThreadPoolExecutor
        _POOL = ThreadPoolExecutor(max_workers=min(16, (os.cpu_count() or 4)), thread_name_prefix="uchrom-io")
    return _POOL


def take(values: np.ndarray, idx: np.ndarray, out: Optional[np.ndarray] = None) -> np.ndarray:
    """``values[idx]`` (1-D ``values``), in threads for large numeric gathers."""
    values = np.asarray(values)
    idx = np.asarray(idx)
    n = len(idx)
    if n < PARALLEL_MIN_ROWS or values.dtype == object or os.environ.get("UCHROM_ZARR_SERIAL_READ") == "1":
        # fancy indexing: faster than np.take(out=) (an object ``out`` would
        # first be filled with None references)
        if out is None:
            return values[idx]
        out[...] = values[idx]
        return out
    if out is None:
        out = np.empty(n, dtype=values.dtype)

    def one(a):
        b = min(n, a + _BLOCK)
        np.take(values, idx[a:b], out=out[a:b])

    list(pool().map(one, range(0, n, _BLOCK)))
    return out


def repeat(values: np.ndarray, counts: np.ndarray) -> np.ndarray:
    """``np.repeat(values, counts)`` (run-constant columns)."""
    return np.repeat(np.asarray(values), np.asarray(counts))
