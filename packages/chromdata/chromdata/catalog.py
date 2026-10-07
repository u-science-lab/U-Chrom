"""An atlas: a bucket (or any HTTP location) of ``.chromdata.zarr`` stores plus a ``catalog.json`` listing them.

Layout of an atlas root (an ``s3://`` / ``https://`` URL or a directory)::

    catalog.json                       what ``fetch_catalog`` reads (written by ``build_catalog``)
    <key>.chromdata.zarr/              one store per dataset (``chromdata.embedded``: self-contained)

``catalog.json``::

    {"version": 1, "title": "...", "updated": "<utc>", "hero": [<id>, ...],
     "studies": [{"id", "citation", "journal", "title", "kind", "category", "summary", "doi", "source",
                  "source_url", "license"}],
     "datasets": [
       {"id", "path" (relative to the root), "study", "name", "title", "description", "paper", "doi", "source_url",
        "license", "organism", "assembly", "tissue", "n_cells", "n_bins", "sections": [...],
        "modalities": ["Hi-C per spot", "Hi-C bulk", "RNA", "A/B per spot", "images", ...],
        "contact_maps": n, "images": n, "size_mb", "files", "format_version", "download" (the .cdz next to the
        store, unless the config says ``"download": false``), "download_mb"}]}

The display text (title, paper, licence ...) comes from a hand-written JSON file (``apps/atlas/datasets.json``);
everything countable is read from the stores, so the catalog cannot drift from the data.  The thumbnails of the
atlas page are drawn from the stores too, by the atlas app (``apps/atlas/build.py``, with the static page).

    python -m chromdata.catalog build apps/atlas/datasets.json --root $UCHROM_DATA --out catalog.json
    python -m chromdata.catalog pack $UCHROM_DATA/x.chromdata.zarr          # -> x.cdz, the download
    python -m chromdata.catalog show https://uchrom-atlas-r2.u-science.org
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
DEFAULT_ATLAS = "https://uchrom-atlas-r2.u-science.org"
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
    uns = cd.uns if isinstance(cd.uns, dict) else {}
    spatial = bool(uns.get("cell_spatial"))          # spots of a tissue section, or dissociated cells
    per_cell = "Hi-C per spot" if spatial else "Hi-C per cell"
    kinds = set()
    if contacts:
        from .embedded import EmbeddedContacts

        for key, name in emb["contacts"].items():
            kinds.add(per_cell if EmbeddedContacts(str(p), name).kind == "per_cell" else "Hi-C bulk")
    mods: List[str] = sorted(kinds, key=[per_cell, "Hi-C bulk"].index)
    if uns.get("linked_anndata"):
        mods.append("RNA")
    for key in (uns.get("linked_bin_matrices") or {}):
        mods.append({"ssAB": "A/B per spot", "ATAC": "ATAC per spot"}.get(str(key), f"{key} per spot"))
    # dissociated cells with accessibility of their own (gene activity ``atac.<gene>`` / an ATAC embedding)
    if not spatial and "ATAC per spot" not in mods and (
            any(str(c).startswith("atac.") for c in cd.cells.columns)
            or any(str(k).startswith("atac_") for k in (getattr(cd, "cellm", {}) or {}))):
        mods.append("ATAC per cell")
    if emb["images"]:
        mods.append("images")
    if len(getattr(cd.spot_tracks, "columns", [])):
        mods.append("signals per spot")
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
        if d.pop("download", True):          # the one-file copy next to the store (``pack``): same files, zipped
            info["download"] = download_name(d["path"])
            info["download_mb"] = info["size_mb"]
        datasets.append({**d, **info})
    cat = {"version": CATALOG_VERSION, "title": cfg.get("title", "U-Chrom Atlas"),
           "description": cfg.get("description", ""), "updated": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "studies": cfg.get("studies", []), "hero": cfg.get("hero") or [], "datasets": datasets}
    if out is not None:
        Path(out).write_text(json.dumps(cat, indent=1, ensure_ascii=False) + "\n")
    return cat


def download_name(path: str) -> str:
    """The ``.cdz`` (one-file) name of an atlas store: ``x.chromdata.zarr`` -> ``x.cdz``."""
    p = str(path).rstrip("/")
    for suffix in (".chromdata.zarr", ".zarr"):
        if p.endswith(suffix):
            return p[: -len(suffix)] + ".cdz"
    return p + ".cdz"


def pack(store: PathLike, out: Optional[PathLike] = None) -> Path:
    """The store as one ``.cdz`` file (the same tree in an uncompressed zip, embedded copies included): what the
    atlas page offers for download.  ``ChromData.read`` and the web browser open it like the directory."""
    from .zarrcd import _zip_tree

    store = Path(store)
    out = Path(out) if out else store.with_name(download_name(store.name))
    tmp = out.with_name(out.name + ".part")
    _zip_tree(store, tmp)
    tmp.replace(out)
    return out


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
    k = sub.add_parser("pack", help="zip a store into the one-file .cdz offered for download")
    k.add_argument("store")
    k.add_argument("--out")
    a = ap.parse_args()
    if a.cmd == "pack":
        out = pack(a.store, a.out)
        print(f"wrote {out} ({out.stat().st_size / 1e6:,.1f} MB)")
    elif a.cmd == "build":
        cat = build_catalog(a.config, a.root, a.out)
        print(f"wrote {a.out}: {len(cat['datasets'])} datasets")
    else:
        for d in fetch_catalog(a.root)["datasets"]:
            print(f"{d['id']:34s} {d.get('n_cells', 0):>7,} cells  {d.get('size_mb', 0):>8,.1f} MB  {d['url']}")
