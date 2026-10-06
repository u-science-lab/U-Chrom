"""Directory listing for the browser's "Open dataset" dialog (server-side paths).

Lists one directory at a time: sub-directories and the files the browser can open.  A
``*.chromdata.zarr`` directory is a dataset (it is opened, not entered).  Hidden entries are left
out unless asked for.  Nothing is read beyond names and ``stat``; the server listens on localhost
only (see ``serve``), so the listing is the local user's own view of the filesystem.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

#: suffix -> format label of what the browser opens (ChromData stores and reconstruction tables)
DATASET_SUFFIXES = {
    ".chromdata.zarr": "chromdata.zarr",
    ".cdz": "cdz",
    ".csv": "csv",
    ".csv.gz": "csv",
}
MAX_ENTRIES = 5000


def dataset_format(name: str, is_dir: bool) -> Optional[str]:
    """Format label when ``name`` is something the browser opens (a zarr store is a directory)."""
    low = name.lower()
    for suffix, fmt in DATASET_SUFFIXES.items():
        if low.endswith(suffix) and (is_dir == (suffix == ".chromdata.zarr")):
            return fmt
    return None


def _dir_size(path: Path, limit: int = 20000) -> Optional[int]:
    """Total size of a store directory (stops at ``limit`` files: None beyond)."""
    total, n = 0, 0
    for root, _, files in os.walk(path):
        for f in files:
            n += 1
            if n > limit:
                return None
            try:
                total += (Path(root) / f).stat().st_size
            except OSError:
                pass
    return total


def list_dir(path: Optional[str] = None, *, show_hidden: bool = False, sizes: bool = True) -> Dict[str, Any]:
    """One directory: its entries (directories first, then datasets, then other files; by name)."""
    p = Path(path).expanduser() if path else Path.cwd()
    p = p.resolve()
    if not p.exists():
        raise FileNotFoundError(f"no such directory: {p}")
    if not p.is_dir():
        raise NotADirectoryError(f"not a directory: {p}")
    entries: List[Dict[str, Any]] = []
    truncated = False
    try:
        listing = os.scandir(p)
    except PermissionError:
        raise PermissionError(f"permission denied: {p}") from None
    with listing as it:
        for e in it:
            if not show_hidden and e.name.startswith("."):
                continue
            if len(entries) >= MAX_ENTRIES:
                truncated = True
                break
            try:
                is_dir = e.is_dir()
                st = e.stat()
            except OSError:
                continue
            fmt = dataset_format(e.name, is_dir)
            kind = "dataset" if fmt else ("dir" if is_dir else "file")
            size = None
            if kind == "dataset":
                size = _dir_size(Path(e.path)) if is_dir and sizes else (st.st_size if not is_dir else None)
            elif kind == "file":
                size = st.st_size
            entries.append({"name": e.name, "path": e.path, "kind": kind, "format": fmt,
                            "size": size, "mtime": st.st_mtime})
    order = {"dir": 0, "dataset": 1, "file": 2}
    entries.sort(key=lambda d: (order[d["kind"]], d["name"].lower()))
    parent = str(p.parent) if p.parent != p else None
    return {"path": str(p), "parent": parent, "sep": os.sep, "entries": entries, "truncated": truncated}


def places(dataset_paths: Iterable[str] = ()) -> List[Dict[str, str]]:
    """Starting points: the server's working directory, the home directory, the folders of the
    loaded datasets (each once, in that order)."""
    out, seen = [], set()

    def add(label: str, p: Optional[Path]) -> None:
        if p is None:
            return
        p = p.expanduser().resolve()
        if str(p) in seen or not p.is_dir():
            return
        seen.add(str(p))
        out.append({"label": label, "path": str(p)})

    add("Server folder", Path.cwd())
    add("Home", Path.home())
    for d in dataset_paths:
        if d:
            add(Path(d).parent.name or str(Path(d).parent), Path(d).parent)
    return out
