"""Datasets as ``ChromData``: a loader turns a dataset's original files into a store, once.

A loader is registered under a dataset name with :func:`register`.  ``build(root, out)`` fetches what it
needs (:func:`uchrom.datasets.fetch`, into ``root``), writes any linked files (a ``.scool`` of per-cell
contact maps, a ``.cool``) next to ``out`` (``<root>/<store>``), links them under relative paths and returns
the ``ChromData``; :func:`uchrom.datasets.load` writes it to ``out`` and reads that store afterwards.

The loaders live in ``_load_<area>.py`` modules (single-cell Hi-C, tracing, bulk Hi-C), imported on first
use.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Tuple

#: modules that register loaders (imported lazily)
_MODULES = ("_load_schic", "_load_tracing", "_load_imaging", "_load_bulk", "_load_cells")


@dataclass(frozen=True)
class Loader:
    name: str
    build: Callable[[Path, Path], Any]       # (root, out) -> ChromData (linked files written next to out)
    store: str                               # store path, relative to the data directory
    sources: Tuple[str, ...] = ()            # the fetch() datasets it reads
    description: str = ""
    version: int = 1                         # bump when the built store changes (rebuilds old caches)
    extra: Dict[str, str] = field(default_factory=dict)


LOADERS: Dict[str, Loader] = {}


def register(loader: Loader) -> Loader:
    LOADERS[loader.name] = loader
    return loader


def loaders() -> Dict[str, Loader]:
    """Every registered loader (importing the modules that define them)."""
    for mod in _MODULES:
        try:
            importlib.import_module(f"{__package__}.{mod}")
        except ModuleNotFoundError as exc:      # an area without loaders yet
            if exc.name != f"{__package__}.{mod}":
                raise
    return LOADERS
