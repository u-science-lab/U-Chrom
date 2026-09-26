"""Give freed memory back to the operating system.

The streaming callers free a band's arrays before building the next one.
The C allocators keep freed blocks for reuse (macOS ``malloc`` zones,
glibc arenas, Arrow's mimalloc pool), so the resident set size would still
include them and grow towards the largest *sum* of past allocations rather
than the largest live set.  :func:`release_memory` asks each allocator to
return what it can: ``malloc_zone_pressure_relief`` on macOS,
``malloc_trim`` on glibc, ``release_unused`` on Arrow's pool.  Best effort:
missing symbols are ignored.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import sys

_LIBC = None


def _libc():
    global _LIBC
    if _LIBC is None:
        try:
            if sys.platform == "darwin":
                _LIBC = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
            else:
                _LIBC = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6")
        except OSError:  # pragma: no cover
            _LIBC = False
    return _LIBC


def release_memory() -> None:
    """Return freed heap memory to the OS (best effort, cheap)."""
    lib = _libc()
    if lib:
        try:
            if sys.platform == "darwin":
                lib.malloc_zone_pressure_relief.restype = ctypes.c_size_t
                lib.malloc_zone_pressure_relief(None, ctypes.c_size_t(0))
            elif hasattr(lib, "malloc_trim"):
                lib.malloc_trim(ctypes.c_size_t(0))
        except (AttributeError, OSError):  # pragma: no cover
            pass
    try:
        import pyarrow as pa
        pa.default_memory_pool().release_unused()
    except Exception:  # pragma: no cover
        pass


__all__ = ["release_memory"]
