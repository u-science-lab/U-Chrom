"""The on-disk structure of a ChromData store, for the browser's "Store" tab.

Walks a ``.chromdata.zarr`` directory or a ``.cdz`` zip (the same tree) and returns a nested
listing: Zarr groups and arrays (shape, dtype, chunks; the chunk files of an array are folded
into it), Parquet tables (rows, columns, row groups), other files, with the size of every
node.  Attributes are summarised (keys and a short preview), never returned whole.

A store read over a URL (:func:`remote_store_tree`) is walked the same way where the object store
lists its files (``s3://``, ``gs://``).  HTTP cannot list a directory, so there the tree is rebuilt
from the store's own metadata: the consolidated Zarr metadata in the root ``zarr.json`` (every group
and array) and the Parquet files the groups' attributes name (the ``tables`` manifest).  Each table
costs a size request and a footer read; the chunk files of an array are not known, so an array
gives its uncompressed size (``nbytes``) and ``bytes`` is ``None``, as is every group holding one.
"""

from __future__ import annotations

import json
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

#: children listed per directory (the rest summarised)
MAX_CHILDREN = 400
#: characters of an attribute preview
PREVIEW = 160
#: Parquet footers read at once from a remote store
REMOTE_WORKERS = 16
#: Parquet tables read from a remote store (the rest listed by name only)
MAX_REMOTE_TABLES = 2000


class _Dir:
    __slots__ = ("files", "dirs")

    def __init__(self) -> None:
        self.files: Dict[str, int] = {}
        self.dirs: Dict[str, "_Dir"] = {}

    def put(self, rel: str, size: int) -> None:
        parts = rel.split("/")
        d = self
        for p in parts[:-1]:
            d = d.dirs.setdefault(p, _Dir())
        d.files[parts[-1]] = size


def _listing(path: Path):
    """(root _Dir, reader of a relative file as bytes / file object) for a directory or zip."""
    root = _Dir()
    put = root.put
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


def _header(tree: Dict[str, Any], head: dict) -> None:
    """The store's own header (format version, counts) in full: small, and what the tab shows first."""
    meta = (head.get("attributes") or {}).get("uchrom")
    if isinstance(meta, dict):
        tree["meta"] = {k: v for k, v in meta.items() if isinstance(v, (str, int, float, bool)) or v is None}


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
    try:
        with (open(path / "zarr.json", "rb") if zf is None else zipfile.ZipFile(path).open("zarr.json")) as fh:
            _header(tree, json.load(fh))
    except Exception:
        pass
    return tree


# --------------------------------------------------------------------------- stores at a URL


def remote_store_tree(url: str) -> Dict[str, Any]:
    """Nested listing of the ``.chromdata.zarr`` store at ``url`` (same nodes as :func:`store_tree`).

    Raises ``LookupError`` when ``url`` holds no Zarr store, or (over HTTP) one without
    consolidated metadata.
    """
    from chromdata.remote import filesystem

    fs, root = filesystem(url)
    root = root.rstrip("/")
    name = url.rstrip("/").rsplit("/", 1)[-1]
    try:
        raw = fs.cat_file(f"{root}/zarr.json")
        head = json.loads(raw)
    except Exception as exc:
        raise LookupError(f"no Zarr store at {url} ({type(exc).__name__})") from exc

    def open_rel(rel: str):
        return fs.open(f"{root}/{rel}", "rb", block_size=1 << 16)

    protocols = fs.protocol if isinstance(fs.protocol, (tuple, list)) else (fs.protocol,)
    if not {"http", "https"} & set(protocols):      # an object store that lists its keys
        listing = _Dir()
        for p, info in fs.find(root, detail=True).items():
            rel = p[len(root):].lstrip("/")
            if rel:
                listing.put(rel, int(info.get("size") or 0))
        tree = _node(name, "", listing, open_rel)
    else:
        tree = _from_metadata(name, head, len(raw), fs, root)
        tree["note"] = ("Read over HTTP, which lists no files: the tree is rebuilt from the store's metadata; "
                        "an array shows its uncompressed size, and a group holding one no size.")
    tree["container"] = "remote"
    _header(tree, head)
    return tree


def _parquet_refs(attrs: Any, out: Optional[List[str]] = None) -> List[str]:
    """Relative Parquet paths named anywhere in a group's attributes (the ``tables`` manifest)."""
    out = [] if out is None else out
    if isinstance(attrs, str):
        if attrs.endswith(".parquet") and "://" not in attrs and not attrs.startswith("/") and ".." not in attrs.split("/"):
            out.append(attrs)
    elif isinstance(attrs, dict):
        for v in attrs.values():
            _parquet_refs(v, out)
    elif isinstance(attrs, list):
        for v in attrs:
            _parquet_refs(v, out)
    return out


def _nbytes(meta: dict) -> Optional[int]:
    import numpy as np

    dt = meta.get("data_type")
    try:
        size = int(dt["configuration"]["length_bytes"]) if isinstance(dt, dict) else np.dtype(str(dt)).itemsize
    except (KeyError, TypeError, ValueError):          # variable length / unknown
        return None
    return int(np.prod(meta.get("shape") or [], dtype=np.int64)) * size


def _doc_bytes(meta: dict) -> int:
    """Size of a node's ``zarr.json`` as zarr writes it (its consolidated copy, re-serialised)."""
    own = {k: v for k, v in meta.items() if k != "consolidated_metadata"}
    return len(json.dumps(own, indent=2, ensure_ascii=False).encode())


def _from_metadata(name: str, head: dict, head_bytes: int, fs, root: str) -> Dict[str, Any]:
    nodes = ((head.get("consolidated_metadata") or {}).get("metadata")) or {}
    if not nodes:
        raise LookupError("the store has no consolidated metadata: its structure cannot be read over HTTP")
    nodes = {"": head, **nodes}
    tables = sorted({f"{key}/{ref}" if key else ref
                     for key, meta in nodes.items() if meta.get("node_type") == "group"
                     for ref in _parquet_refs(meta.get("attributes") or {})})

    def read(rel: str) -> Optional[Dict[str, Any]]:
        try:
            size = int(fs.info(f"{root}/{rel}")["size"])
        except FileNotFoundError:                      # named but absent: not listed
            return None
        except Exception as exc:
            return {"bytes": None, "error": f"{type(exc).__name__}: {exc}"}
        return {"bytes": size, **_parquet(lambda r: fs.open(f"{root}/{r}", "rb", block_size=1 << 16, size=size), rel)}

    with ThreadPoolExecutor(REMOTE_WORKERS) as pool:
        found = dict(zip(tables, pool.map(read, tables[:MAX_REMOTE_TABLES])))
    for rel in tables[MAX_REMOTE_TABLES:]:
        found[rel] = {"bytes": None}

    # one tree of groups / arrays / folders, the tables as its files
    listing = _Dir()
    for key in nodes:
        if key:
            d = listing
            for part in key.split("/"):
                d = d.dirs.setdefault(part, _Dir())
    for rel, info in found.items():
        if info is not None:
            listing.put(rel, 0)

    def node(nm: str, rel: str, d: _Dir) -> Dict[str, Any]:
        meta = nodes.get(rel)
        out: Dict[str, Any] = {"name": nm, "path": rel}
        attrs = (meta or {}).get("attributes") or {}
        if attrs:
            out["attrs"] = {k: _preview(v) for k, v in attrs.items()}
        if meta and meta.get("node_type") == "array":
            chunks = (meta.get("chunk_grid") or {}).get("configuration", {}).get("chunk_shape")
            out.update(kind="array", bytes=None, nbytes=_nbytes(meta), shape=meta.get("shape"),
                       dtype=str(meta.get("data_type")), chunk_shape=chunks)
            return out
        out["kind"] = "group" if meta else "dir"
        children = [node(c, f"{rel}/{c}" if rel else c, d.dirs[c]) for c in sorted(d.dirs, key=str.lower)]
        for fname in sorted(d.files, key=str.lower):
            frel = f"{rel}/{fname}" if rel else fname
            children.append({"name": fname, "path": frel, "kind": "table", **found[frel]})
        sizes = [c["bytes"] for c in children]
        doc = head_bytes if rel == "" else _doc_bytes(meta) if meta else 0
        out["bytes"] = None if any(b is None for b in sizes) else doc + sum(sizes)
        if len(children) > MAX_CHILDREN:
            out["more"] = len(children) - MAX_CHILDREN
            children = children[:MAX_CHILDREN]
        out["children"] = children
        return out

    return node(name, "", listing)
