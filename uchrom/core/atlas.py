"""An atlas: a bucket (or any HTTP location) of ``.chromdata.zarr`` stores plus a ``catalog.json`` listing them.

Layout of an atlas root (an ``s3://`` / ``https://`` URL or a directory)::

    catalog.json                       what ``fetch_catalog`` reads (written by ``build_catalog``)
    <key>.chromdata.zarr/              one store per dataset (``uchrom.core.embedded``: self-contained)

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

The display text (title, paper, licence ...) comes from a hand-written JSON file (``atlas/datasets.json``);
everything countable is read from the stores, so the catalog cannot drift from the data.  The thumbnails of the
atlas page are drawn from the stores too (``render_figures``; committed under ``atlas/site/figures``).

    python -m uchrom.core.atlas build atlas/datasets.json --root example-data --out catalog.json
    python -m uchrom.core.atlas figures atlas/datasets.json --root example-data      # -> atlas/site/figures
    python -m uchrom.core.atlas pack example-data/x.chromdata.zarr          # -> x.cdz, the download
    python -m uchrom.core.atlas show https://uchrom-atlas-r2.u-science.org
    python -m uchrom.core.atlas site dist/site --catalog catalog.json    # the static page (atlas/site) to deploy
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


# -- figures for the atlas page --------------------------------------------------------------------------------------

#: cell columns tried, in order, to colour the spatial thumbnail (the first one that covers the section): spatial
#: domains first (they draw the tissue), then cell types and clusters
COLOR_COLUMNS = ("cluster_cellcharter", "banksy_cluster", "anno", "cell_type", "atac_cluster", "seurat_clusters",
                 "leiden", "louvain", "cluster")
#: categorical colours of the figures (muted, readable on a light and a dark page)
PALETTE = ("#3651A2", "#DC740D", "#5B8F34", "#BE2D2A", "#7E5AA6", "#2A9D8F", "#E0A526", "#C1567E", "#4F86C6",
           "#8C6D46", "#91B23A", "#E4704F", "#5C6F7E", "#B07AC9", "#3E8E5E", "#D9A07E", "#2F6B8F", "#A3A33C",
           "#E07AA0", "#6C4F3D", "#77AADD", "#C2452D", "#4C9A8A", "#9E8FCF")
NA_COLOR = "#B8B4AC"
#: contact-map colour ramp (white → rose → red → dark red, as in Juicebox)
MAP_RAMP = ((255, 255, 255), (247, 196, 178), (226, 104, 80), (178, 30, 38), (100, 10, 22))
FIGURE_WINDOW = 40_000_000      # bp of the contact-map thumbnail (a window of the chromosome, not all of it)


def _section_choice(cd, emb: Dict[str, Any], section: Optional[str], color_by: Optional[str]):
    """(section, colour column, bulk map) of a thumbnail: a section with a bulk map and a covering label column."""
    cells = cd.cells
    sections = [str(s) for s in cells["section"].astype(str).unique()] if "section" in cells else [None]
    bulk = {k: v for k, v in emb.items() if v.kind == "bulk"}

    def bulk_of(s):       # the bulk map of a section is keyed bulk.<section>[.<variant>]
        hits = [k for k in bulk if s is not None and (k == f"bulk.{s}" or k.startswith(f"bulk.{s}."))]
        return min(hits, key=len) if hits else None

    def column_of(s):
        sub = cells if s is None else cells[cells["section"].astype(str) == s]
        for c in ([color_by] if color_by else COLOR_COLUMNS):
            if c in sub and len(sub) and sub[c].notna().mean() >= 0.9 and 1 < sub[c].nunique() <= 60:
                return c
        return None

    order = [section] if section else sorted(sections, key=lambda s: (bulk_of(s) is None, column_of(s) is None))
    s = order[0]
    return s, column_of(s), bulk_of(s) or (next(iter(bulk)) if bulk and not section else None)


def _hex(c: str):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) + (255,)


def _spatial_png(pos, labels, out: Path, size: int, supersample: int = 3) -> Dict[str, Any]:
    """Spots as squares (a regular grid) or dots, in tissue coordinates (y down), on a transparent square."""
    import numpy as np
    from PIL import Image, ImageDraw
    from scipy.spatial import cKDTree

    xy = pos[["x", "y"]].to_numpy(float)
    ok = np.isfinite(xy).all(1)
    xy = xy[ok]
    lab = labels[ok] if labels is not None else None
    lo, hi = xy.min(0), xy.max(0)
    span = float(max(hi - lo)) or 1.0
    big = size * supersample
    scale = big * 0.94 / span
    origin = (big - (hi - lo) * scale) / 2 - lo * scale
    p = xy * scale + origin
    nn = cKDTree(xy).query(xy, k=2)[0][:, 1] if len(xy) > 2 else np.full(len(xy), span / 50)
    step = float(np.median(nn))
    grid = bool(np.mean(np.abs(nn - step) < 0.05 * step) > 0.8)
    half = step * scale * (0.52 if grid else 0.45)
    if not grid:                                   # an embedding: dots stay visible however close the cells are
        half = max(half, 1.7 * supersample * size / 480)
    if lab is not None:
        cats = lab.dropna().astype(str).value_counts().index.tolist()
        lut = {c: _hex(PALETTE[i % len(PALETTE)]) for i, c in enumerate(cats)}
        cols = [lut.get(str(v), _hex(NA_COLOR)) if v == v else _hex(NA_COLOR) for v in lab]
    else:
        cats, cols = [], [_hex(PALETTE[0])] * len(p)
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    shape = draw.rectangle if grid else draw.ellipse
    for (x, y), c in zip(p, cols):
        shape((x - half, y - half, x + half, y + half), fill=c)
    img.resize((size, size), Image.LANCZOS).save(out, quality=90, method=6)
    return {"n": int(len(p)), "categories": len(cats), "grid": grid}


def _map_matrix(e, chrom: str, start: int, end: int, res: int):
    import numpy as np

    lo, hi = start // res, -(-end // res)
    if e.kind == "per_cell":
        d = e.sum_pixels(f"cis/{chrom}", res)
        d = d[(d[:, 0] >= lo) & (d[:, 0] < hi)]
    else:
        d = e.region_pixels(chrom, lo, hi, res)
    d = d[(d[:, 1] >= lo) & (d[:, 1] < hi)]
    n = hi - lo
    m = np.zeros((n, n), np.float64)
    m[d[:, 0] - lo, d[:, 1] - lo] = d[:, 2]
    return np.maximum(m, m.T), lo, hi


def _map_png(e, chrom: str, out: Path, region: Optional[str] = None, max_bins: int = 400,
             min_fill: float = 0.25) -> Dict[str, Any]:
    """A window of a contact map (log counts; a per-cell map: the all-cells sum) at the finest resolution that keeps
    it under ``max_bins``.  A sparse map (under ``min_fill`` of the off-diagonal pixels seen: a few cells) is drawn
    for the whole chromosome at the finest resolution that fills it instead."""
    import numpy as np
    from PIL import Image

    sizes = e.chromsizes()
    if region:
        chrom, _, span = region.partition(":")
        start, end = (int(float(v)) for v in span.replace(",", "").split("-"))
    else:
        if chrom not in sizes:
            chrom = next(c for c in e.chroms if c in sizes)
        width = min(FIGURE_WINDOW, sizes[chrom])
        start = int(min(sizes[chrom] * 0.15, sizes[chrom] - width))
        end = start + width
    if e.kind == "per_cell" and not region:      # per-cell maps are coarse: the whole chromosome
        start, end = 0, sizes[chrom]
    res = next((r for r in sorted(e.resolutions) if (end - start) / r <= max_bins), max(e.resolutions))
    tries = [(start, end, res)]
    if not region:
        tries += [(0, sizes[chrom], r) for r in sorted(e.resolutions) if r > res and sizes[chrom] / r <= max_bins]
    for start, end, res in tries:
        m, lo, hi = _map_matrix(e, chrom, start, end, res)
        n = hi - lo
        fill = float((m[np.triu_indices(n, 1)] > 0).mean()) if n > 1 else 1.0
        if fill >= min_fill:
            break
    v = np.log1p(m)
    off = v[np.triu_indices(n, 1)]
    vmax = np.percentile(off[off > 0], 99.5) if (off > 0).any() else 1.0
    t = np.clip(v / vmax, 0, 1) ** 1.3
    ramp = np.asarray(MAP_RAMP, float)
    k = t * (len(ramp) - 1)
    i0 = np.minimum(k.astype(int), len(ramp) - 2)
    f = (k - i0)[..., None]
    rgb = ramp[i0] * (1 - f) + ramp[i0 + 1] * f
    Image.fromarray(rgb.astype(np.uint8), "RGB").save(out, quality=90, method=6)
    return {"map_key": e.key, "map_label": e.label, "chrom": chrom, "start": int(lo * res), "end": int(hi * res),
            "resolution": int(res), "fill": round(fill, 3)}


def _cell_layout(cd, key: Optional[str], embedding: Optional[str] = None):
    """Where to draw the cells: (x / y frame, "space" | "embedding", key).  Tissue positions (y down) when the
    store has them, else a 2-D embedding of ``cellm`` (y up; ``embedding``, else a key with "umap" first), else
    ``None``."""
    import pandas as pd

    try:
        return cd.cell_positions(key or "default"), "space", key or "default"
    except KeyError:
        pass
    cellm = dict(getattr(cd, "cellm", {}) or {})
    keys = [k for k in cellm if getattr(cellm[k], "ndim", 0) == 2 and cellm[k].shape[1] >= 2]
    keys.sort(key=lambda k: (k != embedding, "umap" not in k.lower(), "tsne" not in k.lower(), k))
    if not keys:
        return None, None, None
    xy = cellm[keys[0]][:, :2]
    return pd.DataFrame({"x": xy[:, 0], "y": -xy[:, 1]}, index=cd.cells.index), "embedding", keys[0]


def _chrom_rank(name: str) -> tuple:
    c = str(name).removeprefix("chr")
    return (0, int(c), "") if c.isdigit() else (1, 0, c)


def _structure_png(cell_cd, out: Path, size: int, supersample: int = 3) -> Dict[str, Any]:
    """One cell's 3-D structure: each trace (chromosome copy) a polyline coloured by chromosome, the cell turned
    to its principal axes and projected on the first two; far segments are drawn first and paler."""
    import numpy as np
    from PIL import Image, ImageDraw

    s = cell_cd.spots_with_loci()
    xyz = np.asarray(cell_cd.coords, dtype=np.float64)
    ok = np.isfinite(xyz).all(1)
    s, xyz = s[ok].reset_index(drop=True), xyz[ok]
    c = xyz - xyz.mean(0)
    _, _, vt = np.linalg.svd(c, full_matrices=False)
    p = c @ vt.T                                    # x: most spread, y: next, z: depth
    span = float(np.ptp(p[:, :2], 0).max()) or 1.0
    big = size * supersample
    scale = big * 0.92 / span
    xy = (p[:, :2] - (p[:, :2].min(0) + p[:, :2].max(0)) / 2) * scale + big / 2
    depth = (p[:, 2] - p[:, 2].min()) / (np.ptp(p[:, 2]) or 1.0)          # 0 far ... 1 near
    chroms = sorted(s["chrom"].astype(str).unique(), key=_chrom_rank)
    lut = {ch: np.array(_hex(PALETTE[i % len(PALETTE)])[:3], float) for i, ch in enumerate(chroms)}
    order = np.lexsort((s["start"].to_numpy(), s["trace_id"].astype(str).to_numpy()))
    tr = s["trace_id"].astype(str).to_numpy()[order]
    same = tr[1:] == tr[:-1]
    i0, i1 = order[:-1][same], order[1:][same]
    seg = np.linalg.norm(xyz[i1] - xyz[i0], axis=1)
    keep = seg <= 4 * np.median(seg) if len(seg) else seg > 0   # sparse tracing: no lines across big jumps
    i0, i1 = i0[keep], i1[keep]
    d = (depth[i0] + depth[i1]) / 2
    segs = np.argsort(d)                             # far first
    width = max(1, int(round(supersample * size / 480 * 1.6)))
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    names = s["chrom"].astype(str).to_numpy()
    for k in segs:                                   # depth cue by transparency: works on a light or dark page
        a, b = i0[k], i1[k]
        rgb = tuple(int(v) for v in lut[names[a]])
        draw.line((xy[a, 0], xy[a, 1], xy[b, 0], xy[b, 1]), fill=rgb + (int(70 + 185 * d[k] ** 1.5),), width=width)
    img.resize((size, size), Image.LANCZOS).save(out, quality=90, method=6)
    return {"n": int(len(xyz)), "categories": len(chroms), "grid": False}


def render_figures(config: PathLike, root: PathLike, out: PathLike, *, size: int = 480, hero_size: int = 640,
                   only: Optional[List[str]] = None) -> Dict[str, Any]:
    """Thumbnails of every dataset of the display config, drawn from the stores under ``root``:
    ``<id>.space.webp`` (one section, spots coloured by a label column, in tissue coordinates; a dataset with 3-D
    structures: one cell's structure, chromosomes coloured; a dataset without either: its cells in a 2-D embedding
    such as a UMAP) and ``<id>.map.webp`` (a 40-Mb window of that
    section's bulk contact map, chr2 by default; without a bulk map: the all-cells sum of a per-cell map).  The
    config entry ``"figure"`` may pin ``section`` / ``color_by`` / ``positions`` / ``chrom`` / ``region``
    (``chr2:40e6-80e6``), ``layout`` (``structure``), ``cell`` or ``embedding`` (a ``cellm`` key) and give the ``caption`` of
    what the hero figure shows.  The datasets of the config's
    ``"hero"`` list are drawn again at ``hero_size`` (``<id>.hero.space.webp`` ...).  Writes ``figures.json``
    (what each figure shows: the page writes the captions from it) next to the images."""
    from .cdata import ChromData
    from .embedded import open_all

    cfg = json.loads(Path(config).read_text())
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    index_path = out / "figures.json"
    index = json.loads(index_path.read_text()) if index_path.is_file() else {}
    hero = cfg.get("hero") or []
    hero = [hero] if isinstance(hero, str) else list(hero)
    hero_map = None           # the hero figure shows one contact map: of the first hero dataset (config order) with one
    for d in cfg["datasets"]:
        if only and d["id"] not in only:
            continue
        spec = d.get("figure", {})
        store = str(Path(root) / d["store"])
        cd = ChromData.read(store, backed=True)
        emb = open_all(store)
        section, column, bulk = _section_choice(cd, emb, spec.get("section"), spec.get("color_by"))
        if bulk is None:          # no bulk map: the all-cells sum of a per-cell map
            bulk = next((k for k, e in emb.items() if e.kind == "per_cell" and e.has_sum()), None)
        structure = None
        try:
            has_positions = bool(len(cd.cell_positions(spec.get("positions") or "default")))
        except KeyError:
            has_positions = False
        per_cell_xyz = bool(cd.n_spots) and "cell_id" in cd.spots.columns
        if spec.get("layout", "structure" if (per_cell_xyz and not has_positions) else "") == "structure":
            cell = spec.get("cell")
            if cell is None and "rmsd_20k" in cd.cells:                        # the best-determined structure
                cell = cd.cells["rmsd_20k"].astype(float).idxmin()
            cell = str(cell if cell is not None else cd.cells.index[0])
            structure = cd.get_cell(cell)
            pos, layout, layout_key = None, "structure", cell
        else:
            pos, layout, layout_key = _cell_layout(cd, spec.get("positions"), spec.get("embedding"))
        info: Dict[str, Any] = {"section": section, "color_by": column, "layout": layout, "layout_key": layout_key}
        if spec.get("caption"):
            info["caption"] = spec["caption"]
        if pos is not None and section is not None and "section" in cd.cells:
            pos = pos[(cd.cells.loc[pos.index, "section"].astype(str) == section).to_numpy()]
        labels = cd.cells.loc[pos.index, column] if (pos is not None and column) else None
        for tag, px in [("", size)] + ([("hero.", hero_size)] if d["id"] in hero else []):
            if structure is not None:
                name = f"{d['id']}.{tag}space.webp"
                info.update(_structure_png(structure, out / name, px))
                info[f"{tag}space"] = name
                info["color_by"] = "chromosome"
            elif pos is not None and len(pos):
                name = f"{d['id']}.{tag}space.webp"
                info.update(_spatial_png(pos, labels, out / name, px))
                info[f"{tag}space"] = name
            if bulk and (not tag or hero_map in (None, d["id"])):
                hero_map = d["id"] if tag else hero_map
                mname = f"{d['id']}.{tag}map.webp"
                info.update(_map_png(emb[bulk], spec.get("chrom", "chr2"), out / mname, spec.get("region")))
                info[f"{tag}map"] = mname
        index[d["id"]] = info
    index_path.write_text(json.dumps(index, indent=1, ensure_ascii=False) + "\n")
    return index


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


def build_site(out: PathLike, catalog: PathLike, *, data_root: str = DEFAULT_ATLAS,
               template: Optional[PathLike] = None, repo: str = "https://github.com/Nanguage/U-Chrom",
               install: str = 'pip install "u-chrom[web]"', hosted: str = "") -> Path:
    """Write the static atlas page to ``out`` (deploy the folder on any static host, e.g. Cloudflare Pages):
    the template (``atlas/site``), ``catalog.json``, ``config.js`` (data root, install line, repo) and ``_headers``."""
    import shutil

    out = Path(out)
    tpl = Path(template) if template else Path(__file__).resolve().parents[2] / "atlas" / "site"
    if not (tpl / "index.html").is_file():
        raise FileNotFoundError(f"no site template at {tpl}")
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(tpl, out)
    cat = json.loads(Path(catalog).read_text())
    cat.pop("url", None)
    figs = out / "figures" / "figures.json"            # render_figures: what each thumbnail shows
    if figs.is_file():
        index = json.loads(figs.read_text())
        for d in cat.get("datasets", []):
            if d["id"] in index:
                d["figures"] = index[d["id"]]
        cat["hero"] = [h for h in (cat.get("hero") or [k for k, v in index.items() if "hero.space" in v]) if h in index]
    (out / CATALOG).write_text(json.dumps(cat, ensure_ascii=False, indent=1) + "\n")
    (out / "config.js").write_text("window.ATLAS_CONFIG = " + json.dumps(
        {"dataRoot": data_root.rstrip("/"), "install": install, "repo": repo, "hosted": hosted.rstrip("/")}, indent=1) + ";\n")
    (out / "_headers").write_text("/catalog.json\n  Cache-Control: public, max-age=300\n/*\n  X-Content-Type-Options: nosniff\n")
    return out


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
    f = sub.add_parser("figures", help="draw the dataset thumbnails of the atlas page from the stores")
    f.add_argument("config")
    f.add_argument("--root", required=True)
    f.add_argument("--out", default="atlas/site/figures")
    f.add_argument("--only", nargs="*")
    w = sub.add_parser("site", help="write the static atlas page")
    w.add_argument("out")
    w.add_argument("--catalog", required=True)
    w.add_argument("--data-root", default=DEFAULT_ATLAS)
    w.add_argument("--template")
    w.add_argument("--hosted", default="", help="URL of the hosted browser: adds an Open online button")
    a = ap.parse_args()
    if a.cmd == "site":
        print("wrote", build_site(a.out, a.catalog, data_root=a.data_root, template=a.template, hosted=a.hosted))
    elif a.cmd == "pack":
        out = pack(a.store, a.out)
        print(f"wrote {out} ({out.stat().st_size / 1e6:,.1f} MB)")
    elif a.cmd == "figures":
        for k, v in render_figures(a.config, a.root, a.out, only=a.only).items():
            print(f"{k:34s} {v}")
    elif a.cmd == "build":
        cat = build_catalog(a.config, a.root, a.out)
        print(f"wrote {a.out}: {len(cat['datasets'])} datasets")
    else:
        for d in fetch_catalog(a.root)["datasets"]:
            print(f"{d['id']:34s} {d.get('n_cells', 0):>7,} cells  {d.get('size_mb', 0):>8,.1f} MB  {d['url']}")
