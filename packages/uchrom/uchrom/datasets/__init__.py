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

A store of the atlas can be downloaded too, as its one-file copy (``.cdz``), for offline work; ``load`` then
reads the local copy::

    ds.list_atlas()                                   # id, title, study, organism, cells, modalities, sizes
    ds.fetch("stevens2017_mesc")                      # .../atlas/stevens2017_mesc.cdz (26 MB)

Command line: ``python -m uchrom.datasets list | atlas | load NAME | fetch NAME ... | path NAME``.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from ._paths import ENV, data_dir

__all__ = ["data_dir", "load", "fetch", "files", "path", "atlas", "atlas_path", "list_datasets", "list_atlas",
           "ENV"]

#: where downloaded atlas stores go: ``<data directory>/atlas/<id>.cdz``
ATLAS_DIR = "atlas"


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
    """Where a dataset is: its file if it has one, else the folder its files share; for a store of the atlas,
    where :func:`fetch` puts its one-file copy."""
    from ._sources import DATASETS

    if name not in DATASETS:
        _atlas_entry(name)                                  # a KeyError naming what there is
        return atlas_path(name, root=root)
    paths = files(name, root=root)
    if len(paths) == 1:
        return paths[0]
    import os

    return Path(os.path.commonpath([str(p) for p in paths]))


def fetch(name: str, *, root: Optional[Path] = None, extract: bool = True, verbose: bool = True) -> Path:
    """Download a dataset into the data directory (files already there are kept) and return :func:`path`.

    A dataset of the registry (``list_datasets()``) comes from its original source and its md5 sums are
    checked; an id of the atlas (``list_atlas()``) gives the store's one-file copy, ``<data
    directory>/atlas/<id>.cdz``, which :func:`load` then reads instead of the remote store.
    """
    from ._fetch import download, extract_many, extract_member, md5
    from ._sources import DATASETS

    root = Path(root) if root is not None else data_dir()
    if name not in DATASETS:
        return _fetch_atlas(name, root=root, verbose=verbose)
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
    - Otherwise a store of the atlas (``list_atlas()``): its local copy when :func:`fetch` downloaded it, else
      opened over HTTP; backed unless ``backed=False``.

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
    return atlas(name, backed=True if backed is None else backed, **read_kw)


def _catalog(root: Optional[str]) -> dict:
    from chromdata import catalog

    return catalog.fetch_catalog(root or catalog.DEFAULT_ATLAS)


def _atlas_entry(name: str, root: Optional[str] = None) -> dict:
    from chromdata import catalog

    entries = {d["id"]: d for d in _catalog(root)["datasets"]}
    if name not in entries:
        from ._loaders import loaders
        from ._sources import DATASETS

        raise KeyError(f"no dataset {name!r}: not in the registry (list_datasets(): {', '.join(sorted(DATASETS))}; "
                       f"loaders: {', '.join(sorted(loaders()))}) nor in the atlas at "
                       f"{root or catalog.DEFAULT_ATLAS} ({', '.join(sorted(entries))})")
    return entries[name]


def atlas_path(name: str, *, root: Optional[Path] = None) -> Path:
    """Where :func:`fetch` puts the one-file copy of the atlas store ``name``: ``<data directory>/atlas/<name>.cdz``
    (whether it is there or not)."""
    return (Path(root) if root is not None else data_dir()) / ATLAS_DIR / f"{name}.cdz"


def _fetch_atlas(name: str, *, root: Path, atlas_root: Optional[str] = None, verbose: bool = True) -> Path:
    """Download the ``.cdz`` of an atlas store into ``root``/atlas/ (kept when already there)."""
    from ._fetch import download

    entry = _atlas_entry(name, atlas_root)
    url = entry.get("download_url")
    if not url:
        raise KeyError(f"the atlas offers no download of {name!r}: open it over HTTP (load / atlas)")
    dest = atlas_path(name, root=root)
    if dest.exists():
        return dest
    want = float(entry.get("download_mb") or 0)
    download(url, dest, f"atlas store {name} ({entry.get('title', '')})", want, verbose=verbose)
    got = dest.stat().st_size / 1e6
    if want and abs(got - want) > 0.02 * want + 0.2:       # catalog sizes are the store's, to 0.1 MB
        dest.unlink()
        raise IOError(f"{name}: downloaded {got:.1f} MB, the catalog says {want:.1f} MB; fetch again")
    return dest


def list_atlas(root: Optional[str] = None, *, data: Optional[Path] = None):
    """The datasets of the atlas (``chromdata.catalog.DEFAULT_ATLAS`` unless ``root``) as a table, one row per
    store: ``title, study, organism, tissue, assembly, n_cells, modalities, size_mb, download_mb``,
    ``downloaded`` (its ``.cdz`` is in the data directory — ``data`` or :func:`data_dir` — :func:`fetch`) and
    ``url`` (what :func:`load` opens over HTTP)."""
    import pandas as pd

    cols = ("id", "title", "study", "organism", "tissue", "assembly", "n_cells", "modalities", "size_mb",
            "download_mb", "url")
    rows = [{c: d.get(c) for c in cols} for d in _catalog(root)["datasets"]]
    table = pd.DataFrame(rows, columns=list(cols)).set_index("id")
    table.insert(len(cols) - 2, "downloaded", [atlas_path(i, root=data).exists() for i in table.index])
    return table


def atlas(name: str, *, root: Optional[str] = None, backed: bool = True, local: Optional[bool] = None,
          **read_kw):
    """Open a dataset of the atlas by its id (``list_atlas()``), backed by default: the one-file copy
    :func:`fetch` downloaded when it is there (``local=None``; ``True`` requires it, ``False`` ignores it),
    else the store over HTTP."""
    from chromdata import ChromData

    copy = atlas_path(name)
    if local or (local is None and root is None and copy.exists()):    # a copy of the default atlas
        if not copy.exists():
            raise FileNotFoundError(f"{copy} is not there: ds.fetch({name!r}) downloads it")
        return ChromData.read(copy, backed=backed, **read_kw)
    return ChromData.read(_atlas_entry(name, root)["url"], backed=backed, **read_kw)
