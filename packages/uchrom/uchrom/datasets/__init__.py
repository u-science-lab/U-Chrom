"""Datasets: the public U-Chrom atlas, and original data files fetched from their sources.

Stores of the atlas open over HTTP, backed (only what a view or an analysis reads is fetched)::

    import uchrom.datasets as ds
    cd = ds.atlas("takei2025_cerebellum")            # https://uchrom-atlas-r2.u-science.org/...

Original files (4DN, GEO, Zenodo, GitHub, UCSC) — the inputs of the import tutorials and of the
benchmarks — are downloaded once into the data directory (``$UCHROM_DATA``, else ``~/.cache/uchrom``)
and checked::

    path = ds.fetch("takei")                          # .../4DNFIHF3JCBY.csv (Takei 2021 FOF-CT)
    ds.list_datasets()                                # what there is, sizes, descriptions

Command line: ``python -m uchrom.datasets list | fetch NAME ... | path NAME``.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from ._paths import ENV, data_dir

__all__ = ["data_dir", "fetch", "files", "path", "atlas", "list_datasets", "list_atlas", "ENV"]


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

        out = root / items[0][0]
        if not out.exists():
            func, kw = entry["build"]
            getattr(_builders, func)(out=out, **kw)
        return out

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
    """The datasets :func:`fetch` knows: name, size (MB), whether ``fetch --default`` includes it, description."""
    import pandas as pd

    from ._sources import DATASETS

    return pd.DataFrame([{"name": k, "size_mb": v.get("size_mb"), "default": v.get("default", True),
                          "description": v.get("description", "")} for k, v in DATASETS.items()]).set_index("name")


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
