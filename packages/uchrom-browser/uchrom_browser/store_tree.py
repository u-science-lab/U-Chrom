"""The on-disk structure of a ChromData store, for the browser's "Store" tab.

Walks a ``.chromdata.zarr`` directory or a ``.cdz`` zip (the same tree) and returns a nested
listing: Zarr groups and arrays (shape, dtype, chunks; the chunk files of an array are folded
into it), Parquet tables (rows, columns, row groups), other files, with the size of every
node.  Attributes are summarised (keys and a short preview), never returned whole.
"""

from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

#: children listed per directory (the rest summarised)
MAX_CHILDREN = 400
#: characters of an attribute preview
PREVIEW = 160


class _Dir:
    __slots__ = ("files", "dirs")

    def __init__(self) -> None:
        self.files: Dict[str, int] = {}
        self.dirs: Dict[str, "_Dir"] = {}


def _listing(path: Path):
    """(root _Dir, reader of a relative file as bytes / file object) for a directory or zip."""
    root = _Dir()

    def put(rel: str, size: int) -> None:
        parts = rel.split("/")
        d = root
        for p in parts[:-1]:
            d = d.dirs.setdefault(p, _Dir())
        d.files[parts[-1]] = size

    if path.is_dir():
        for base, _, files in os.walk(path):
            rb = os.path.relpath(base, path)
            for f in files:
                rel = f if rb == "." else f"{rb.replace(os.sep, '/')}/{f}"
                try:
                    put(rel, (Path(base) / f).stat().st_size)
                except OSError:
                    pass
        return root, lambda rel: open(path / rel, "rb"), None
    zf = zipfile.ZipFile(path)
    for info in zf.infolist():
        if not info.is_dir():
            put(info.filename.rstrip("/"), info.file_size)
    return root, lambda rel: zf.open(rel), zf


def _preview(v: Any) -> str:
    s = json.dumps(v, default=str, separators=(",", ":"))
    return s if len(s) <= PREVIEW else s[: PREVIEW - 1] + "…"


def _size(d: _Dir) -> int:
    return sum(d.files.values()) + sum(_size(c) for c in d.dirs.values())


def _count_files(d: _Dir) -> int:
    return len(d.files) + sum(_count_files(c) for c in d.dirs.values())


def _parquet(open_rel, rel: str) -> Dict[str, Any]:
    import pyarrow.parquet as pq

    try:
        with open_rel(rel) as fh:
            md = pq.ParquetFile(fh).metadata
            names = [md.schema.column(i).name for i in range(md.num_columns)]
        return {"rows": int(md.num_rows), "columns": names, "row_groups": int(md.num_row_groups)}
    except Exception as exc:  # unreadable: say so, keep the listing
        return {"error": f"{type(exc).__name__}: {exc}"}


def _node(name: str, rel: str, d: _Dir, open_rel) -> Dict[str, Any]:
    meta: Optional[dict] = None
    if "zarr.json" in d.files:
        try:
            with open_rel(f"{rel}/zarr.json" if rel else "zarr.json") as fh:
                meta = json.load(fh)
        except Exception:
            meta = None
    node: Dict[str, Any] = {"name": name, "path": rel, "bytes": _size(d)}
    attrs = (meta or {}).get("attributes") or {}
    if attrs:
        node["attrs"] = {k: _preview(v) for k, v in attrs.items()}
    if meta and meta.get("node_type") == "array":
        chunks = (meta.get("chunk_grid") or {}).get("configuration", {}).get("chunk_shape")
        node.update(kind="array", shape=meta.get("shape"), dtype=str(meta.get("data_type")),
                    chunk_shape=chunks, n_chunks=_count_files(d) - 1)
        return node                                         # its chunk files are folded in
    node["kind"] = "group" if meta else "dir"
    children: List[Dict[str, Any]] = []
    for cname in sorted(d.dirs, key=str.lower):
        children.append(_node(cname, f"{rel}/{cname}" if rel else cname, d.dirs[cname], open_rel))
    for fname in sorted(d.files, key=str.lower):
        if fname == "zarr.json" and meta is not None:
            continue
        frel = f"{rel}/{fname}" if rel else fname
        f: Dict[str, Any] = {"name": fname, "path": frel, "bytes": d.files[fname], "kind": "file"}
        if fname.endswith(".parquet"):
            f.update(kind="table", **_parquet(open_rel, frel))
        children.append(f)
    if len(children) > MAX_CHILDREN:
        node["more"] = len(children) - MAX_CHILDREN
        children = children[:MAX_CHILDREN]
    node["children"] = children
    return node


def store_tree(path: Path) -> Dict[str, Any]:
    """Nested listing of the store at ``path`` (``.chromdata.zarr`` directory or ``.cdz``)."""
    path = Path(path)
    root, open_rel, zf = _listing(path)
    try:
        tree = _node(path.name, "", root, open_rel)
    finally:
        if zf is not None:
            zf.close()
    tree["container"] = "cdz" if zf is not None else "zarr"
    # the store's own header (format version, counts) in full: small, and what the tab shows first
    try:
        with (open(path / "zarr.json", "rb") if zf is None else zipfile.ZipFile(path).open("zarr.json")) as fh:
            meta = (json.load(fh).get("attributes") or {}).get("uchrom")
        if isinstance(meta, dict):
            tree["meta"] = {k: v for k, v in meta.items() if isinstance(v, (str, int, float, bool)) or v is None}
    except Exception:
        pass
    return tree
