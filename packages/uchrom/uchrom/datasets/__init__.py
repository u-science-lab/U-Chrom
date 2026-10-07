"""Datasets: every dataset U-Chrom knows, as a ``ChromData`` — or as its original files.

``load`` gives a ``ChromData``: a store of the public atlas (opened over HTTP, backed: only what a view or
an analysis reads is fetched), or a dataset built once from its original files by a registered loader and
cached in the data directory::

    import uchrom.datasets as ds
    cd = ds.load("takei2025_cerebellum")             # the atlas store, https://uchrom-atlas-r2.u-science.org/...
    cd = ds.load("kim2020_scihic")                   # 1,931 cells, cell types, per-cell contact maps (linked)

Original files (4DN, GEO, Zenodo, GitHub, UCSC) — what the readers of ``uchrom.io`` read, the inputs of
the benchmarks — are downloaded once into the data directory (``$UCHROM_DATA``, else ``~/.cache/uchrom``)
and checked::

    path = ds.fetch("takei")                          # .../4DNFIHF3JCBY.csv (Takei 2021 FOF-CT)
    ds.list_datasets()                                # what there is, sizes, descriptions

Command line: ``python -m uchrom.datasets list | atlas | load NAME | fetch NAME ... | path NAME``.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from ._paths import ENV, data_dir

__all__ = ["data_dir", "load", "fetch", "files", "path", "atlas", "list_datasets", "list_atlas", "ENV"]


def _entry(name: str) -> dict:
    from ._sources import DATASETS

    if name not in DATASETS:
        raise KeyError(f"unknown dataset {name!r}; known: {', '.join(sorted(DATASETS))}")
    return DATASETS[name]


def _files(entry: dict) -> list:
    items = entry.get("files") or [(entry["filename"], entry["url"])]
    return list(items() if callable(items) else items)


def files(name: str, *, root: Optional[Path] = None) -> List[Path]:
    """The local paths of a dataset's files (downloaded or not)."""
    root = Path(root) if root is not None else data_dir()
    entry = _entry(name)
    out = [root / rel for rel, _ in _files(entry)]
    out += [root / rel for rel, *_ in entry.get("extract", [])]
    out += [root / rel for rel, *_ in entry.get("extract_many", [])]
    return out


def path(name: str, *, root: Optional[Path] = None) -> Path:
    """Where a dataset is: its file if it has one, else the folder its files share."""
    paths = files(name, root=root)
    if len(paths) == 1:
        return paths[0]
    import os

    return Path(os.path.commonpath([str(p) for p in paths]))


def fetch(name: str, *, root: Optional[Path] = None, extract: bool = True, verbose: bool = True) -> Path:
    """Download a dataset from its original source into the data directory (files already there are
    kept) and check its md5 sums; returns :func:`path`."""
    from ._fetch import download, extract_many, extract_member, md5

    root = Path(root) if root is not None else data_dir()
    entry = _entry(name)
    items = _files(entry)
    if "build" in entry:                 # built from its source (e.g. a .hic read over HTTP), not downloaded
        from . import _builders

        if not all((root / rel).exists() for rel, _ in items):
            func, kw = entry["build"]
            getattr(_builders, func)(out=root / items[0][0], **kw)
        for rel, want in entry.get("md5", {}).items():
            if md5(root / rel) != want:
                raise IOError(f"md5 mismatch for {root / rel} (expected {want}); delete it and fetch again")
        return path(name, root=root)

    def one(item):
        rel, url = item
        dest = download(url, root / rel, entry.get("description", name), entry.get("size_mb", 0), verbose=verbose)
        want = entry.get("md5", {}).get(rel)
        if want and md5(dest) != want:
            raise IOError(f"md5 mismatch for {dest} (expected {want}); delete it and fetch again")

    if entry.get("parallel", 1) > 1:     # polite: NCBI throttles many parallel requests
        from concurrent.futures import ThreadPoolExecutor

        def safe(item):
            try:
                one(item)
            except Exception as exc:
                return f"{item[0]}: {exc}"

        with ThreadPoolExecutor(entry["parallel"]) as pool:
            failed = [f for f in pool.map(safe, items) if f]
        if failed:
            raise IOError(f"{len(failed)} files of {name} failed (fetch again to retry): {failed[:3]}")
    else:
        for item in items:
            one(item)
    if extract:
        for rel, url, member in entry.get("extract", []):
            extract_member(url, member, root / rel, verbose=verbose)
        for rel, url, pattern in entry.get("extract_many", []):
            extract_many(url, pattern, root / rel, verbose=verbose)
    return path(name, root=root)


def list_datasets():
    """The datasets :func:`fetch` knows: name, size (MB), whether :func:`load` gives it as a ``ChromData``,
    whether ``fetch --default`` (the tutorials' inputs) includes it, description."""
    import pandas as pd

    from ._loaders import loaders
    from ._sources import DATASETS

    known = loaders()
    rows = [{"name": k, "size_mb": v.get("size_mb"), "load": k in known, "default": v.get("default", False),
             "description": v.get("description", "")} for k, v in DATASETS.items()]
    rows += [{"name": k, "size_mb": None, "load": True, "default": False, "description": v.description}
             for k, v in known.items() if k not in DATASETS]
    return pd.DataFrame(rows).set_index("name")


def load(name: str, *, root: Optional[Path] = None, backed: Optional[bool] = None, rebuild: bool = False,
         **read_kw):
    """A dataset as a ``ChromData``.

    - A dataset with a loader (``list_datasets()``, column ``load``): built once from its original files
      (fetched with :func:`fetch`) into ``<data directory>/<dataset>/<dataset>.chromdata.zarr`` with its
      linked files next to it, then read from there (in memory unless ``backed=True``).  ``rebuild=True``
      builds it again.
    - Otherwise a store of the atlas (``list_atlas()``): opened over HTTP, backed unless ``backed=False``.

    ``read_kw`` go to :meth:`chromdata.ChromData.read` (``columns=``, ``tracks=``, ...).
    """
    from chromdata import ChromData

    from ._loaders import loaders

    known = loaders()
    if name in known:
        loader = known[name]
        root = Path(root) if root is not None else data_dir()
        out = root / loader.store
        if out.exists() and not rebuild:
            meta = ChromData.read(out, backed=True).uns.get("dataset") or {}
            rebuild = meta.get("loader_version") != loader.version
        if rebuild or not out.exists():
            cd = loader.build(root, out)
            cd.uns["dataset"] = {"name": name, "loader_version": loader.version, "sources": list(loader.sources)}
            cd.write(out)                          # atomic: replaces an older build
        return ChromData.read(out, backed=bool(backed), **read_kw)
    try:
        return atlas(name, backed=True if backed is None else backed, **read_kw)
    except KeyError:
        raise KeyError(f"no dataset {name!r}: neither a loader ({', '.join(sorted(known))}) nor an atlas "
                       f"store (list_atlas())") from None


def list_atlas(root: Optional[str] = None):
    """The datasets of the atlas (``chromdata.catalog.DEFAULT_ATLAS`` unless ``root``) as a table."""
    import pandas as pd
    from chromdata import catalog

    cat = catalog.fetch_catalog(root or catalog.DEFAULT_ATLAS)
    cols = ("id", "title", "n_cells", "modalities", "size_mb", "url")
    return pd.DataFrame([{c: d.get(c) for c in cols} for d in cat["datasets"]]).set_index("id")


def atlas(name: str, *, root: Optional[str] = None, backed: bool = True, **read_kw):
    """Open a dataset of the atlas by its id (``list_atlas()``), backed over HTTP by default."""
    from chromdata import ChromData, catalog

    root = root or catalog.DEFAULT_ATLAS
    cat = catalog.fetch_catalog(root)
    urls = {d["id"]: d["url"] for d in cat["datasets"]}
    if name not in urls:
        raise KeyError(f"{name!r} is not in the atlas at {root}; it has: {', '.join(sorted(urls))}")
    return ChromData.read(urls[name], backed=backed, **read_kw)
