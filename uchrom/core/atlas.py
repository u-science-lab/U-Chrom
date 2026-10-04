"""An atlas: a bucket (or any HTTP location) of ``.chromdata.zarr`` stores plus a ``catalog.json`` listing them.

Layout of an atlas root (an ``s3://`` / ``https://`` URL or a directory)::

    catalog.json                       what ``fetch_catalog`` reads (written by ``build_catalog``)
    <key>.chromdata.zarr/              one store per dataset (``uchrom.core.embedded``: self-contained)

``catalog.json``::

    {"version": 1, "title": "...", "updated": "<utc>", "datasets": [
       {"id", "path" (relative to the root), "title", "description", "paper", "doi", "source_url", "license",
        "organism", "assembly", "tissue", "n_cells", "n_bins", "sections": [...],
        "modalities": ["Hi-C per spot", "Hi-C bulk", "RNA", "A/B per spot", "images", ...],
        "contact_maps": n, "images": n, "size_mb", "files", "format_version"}]}

The display text (title, paper, licence ...) comes from a hand-written JSON file (``atlas/datasets.json``);
everything countable is read from the stores, so the catalog cannot drift from the data.

    python -m uchrom.core.atlas build atlas/datasets.json --root example-data --out catalog.json
    python -m uchrom.core.atlas show https://uchrom-atlas.u-science.org
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .remote import is_url

PathLike = Union[str, Path]
CATALOG = "catalog.json"
#: the public atlas the web browser lists unless ``--atlas`` / ``UCHROM_ATLAS`` says otherwise (empty: none)
DEFAULT_ATLAS = "https://uchrom-atlas.u-science.org"
CATALOG_VERSION = 1


def _du(path: Path) -> tuple:
    files = [p for p in path.rglob("*") if p.is_file()]
    return round(sum(p.stat().st_size for p in files) / 1e6, 1), len(files)


def describe_store(path: PathLike) -> Dict[str, Any]:
    """What the catalog says about a store, read from the store itself."""
    from .cdata import ChromData

    p = Path(path)
    cd = ChromData.read(str(p), backed=True)
    emb = cd.embedded_links()
    contacts = list(emb["contacts"])
    kinds = set()
    if contacts:
        from .embedded import EmbeddedContacts

        for key, name in emb["contacts"].items():
            kinds.add("Hi-C per spot" if EmbeddedContacts(str(p), name).kind == "per_cell" else "Hi-C bulk")
    mods: List[str] = sorted(kinds, key=["Hi-C per spot", "Hi-C bulk"].index)
    uns = cd.uns if isinstance(cd.uns, dict) else {}
    if uns.get("linked_anndata"):
        mods.append("RNA")
    for key in (uns.get("linked_bin_matrices") or {}):
        mods.append({"ssAB": "A/B per spot", "ATAC": "ATAC per spot"}.get(str(key), f"{key} per spot"))
    if emb["images"]:
        mods.append("images")
    if cd.n_spots:
        mods.append("3-D coordinates")
    if len(getattr(cd, "cellm", {}) or {}):
        mods.append("embeddings")
    sections = []
    if "section" in cd.cells.columns:
        sections = [str(s) for s in cd.cells["section"].astype(str).unique()]
    size, files = _du(p)
    return {"n_cells": int(cd.n_cells), "n_spots": int(cd.n_spots), "n_bins": int(len(cd.bins)),
            "sections": sections, "modalities": mods, "contact_maps": len(contacts), "images": len(emb["images"]),
            "size_mb": size, "files": files,
            "format_version": str(cd._c.meta.get("format_version", ""))}


def build_catalog(config: PathLike, root: PathLike, out: Optional[PathLike] = None) -> Dict[str, Any]:
    """Catalog from the display config and the stores under ``root`` (config entries: ``id``, ``store`` — the
    path of the store under ``root`` — and ``path`` — its name in the atlas; the rest is copied)."""
    cfg = json.loads(Path(config).read_text())
    root = Path(root)
    datasets = []
    for d in cfg["datasets"]:
        d = dict(d)
        store = root / d.pop("store")
        info = describe_store(store)
        datasets.append({**d, **info})
    cat = {"version": CATALOG_VERSION, "title": cfg.get("title", "U-Chrom Atlas"),
           "description": cfg.get("description", ""), "updated": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "datasets": datasets}
    if out is not None:
        Path(out).write_text(json.dumps(cat, indent=1, ensure_ascii=False) + "\n")
    return cat


def catalog_url(root: str) -> str:
    return root if root.rstrip("/").endswith(".json") else root.rstrip("/") + "/" + CATALOG


def fetch_catalog(root: str, timeout: float = 20.0) -> Dict[str, Any]:
    """Read the catalog of an atlas root (URL or directory); every dataset gets ``url``, the address that
    ``ChromData.read(..., backed=True)`` and the web browser open."""
    if is_url(root):
        import urllib.request

        base = catalog_url(root)
        req = urllib.request.Request(base, headers={"User-Agent": "uchrom-atlas"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            cat = json.loads(r.read().decode("utf-8"))
        base = base.rsplit("/", 1)[0]
    else:
        p = Path(root)
        p = p if p.suffix == ".json" else p / CATALOG
        cat = json.loads(p.read_text())
        base = str(p.parent)
    for d in cat.get("datasets", []):
        d["url"] = base.rstrip("/") + "/" + str(d["path"]).lstrip("/")
    return cat


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Build / show an atlas catalog")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("config")
    b.add_argument("--root", required=True, help="folder holding the stores named by the config")
    b.add_argument("--out", default=CATALOG)
    s = sub.add_parser("show")
    s.add_argument("root")
    a = ap.parse_args()
    if a.cmd == "build":
        cat = build_catalog(a.config, a.root, a.out)
        print(f"wrote {a.out}: {len(cat['datasets'])} datasets")
    else:
        for d in fetch_catalog(a.root)["datasets"]:
            print(f"{d['id']:34s} {d.get('n_cells', 0):>7,} cells  {d.get('size_mb', 0):>8,.1f} MB  {d['url']}")
