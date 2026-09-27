"""Figure 2a — ChromData: tables, keys and the on-disk layout (format 2.2).

Follows docs/source/guide/chromdata_2_0_design.md (Overview, section 2 `bins`,
section 4) and the on-disk layout actually written by ``uchrom.core.zarrcd``
(``x.chromdata.zarr``: Zarr + Parquet).  Eager / lazy markers follow
``uchrom.core.backed`` (``read(path, backed=True)``).  Schematic only — no data.

    python paper/fig2/panel_a.py      # -> fig2a_draft.pdf / .png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle

HERE = Path(__file__).resolve().parent
MM = 1 / 25.4
W, H = 170.0, 88.0

mpl.rcParams.update({"pdf.fonttype": 42, "font.family": "sans-serif", "font.sans-serif": ["Arial"]})

ORANGE, TEAL, PURPLE, INDIGO = "#e07a3f", "#2a9d8f", "#8e7cc3", "#34568b"
INK, GREY, LGREY, LINE = "#2b2f36", "#8a8f98", "#e6e7ea", "#3a3f47"
TINT = {ORANGE: "#fbe3d4", TEAL: "#d8efec", PURPLE: "#e9e4f4", INDIGO: "#dde4ef", GREY: "#eceef1"}


class C:
    def __init__(self, fig, rect=(0, 0, 1, 1)):
        self.ax = fig.add_axes(list(rect))
        self.ax.set_xlim(0, W); self.ax.set_ylim(H, 0); self.ax.axis("off")

    def t(self, x, y, s, size=6, color=INK, ha="left", va="center", weight="normal", **kw):
        return self.ax.text(x, y, s, fontsize=size, color=color, ha=ha, va=va, fontweight=weight, **kw)

    def rect(self, x, y, w, h, fc, ec=LINE, lw=0.4, ls="-", z=2, r=0.0):
        if r:
            p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}", fc=fc, ec=ec, lw=lw,
                               ls=ls, zorder=z)
        else:
            p = Rectangle((x, y), w, h, fc=fc, ec=ec, lw=lw, ls=ls, zorder=z)
        self.ax.add_patch(p)

    def line(self, xs, ys, color=LINE, lw=0.3, ls="-", z=3):
        self.ax.plot(xs, ys, color=color, lw=lw, ls=ls, zorder=z, solid_capstyle="butt")

    def arrow(self, a, b, color=INDIGO, lw=0.6, ls="-", rad=0.0, z=4):
        self.ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>,head_length=1.6,head_width=0.9",
                                          color=color, lw=lw, ls=ls, zorder=z, shrinkA=0, shrinkB=0,
                                          connectionstyle=f"arc3,rad={rad}", mutation_scale=1))

    def key(self, x, y, s, color=INDIGO):
        """A key label in a small rounded pill."""
        w = 1.35 * len(s) + 2.2
        self.rect(x - w / 2, y - 1.6, w, 3.2, fc="white", ec=color, lw=0.4, r=1.2, z=6)
        self.t(x, y, s, size=6, color=color, ha="center", zorder=7)


def table(c, x, y, w, h, color, cols=None, rows=8, title=None, sub=None, ls="-"):
    """A table block: tinted body, optional column dividers and faint row lines."""
    c.rect(x, y, w, h, fc=TINT[color], ec=color, lw=0.5, ls=ls)
    for k in range(1, rows):
        c.line([x, x + w], [y + h * k / rows] * 2, color="white", lw=0.35)
    if cols:
        cw = w / len(cols)
        for i, col in enumerate(cols):
            if i:
                c.line([x + i * cw] * 2, [y, y + h], color=color, lw=0.3)
            c.t(x + (i + 0.5) * cw, y - 1.0, col, size=6, color=color, ha="center", va="bottom", rotation=90)
    if title:
        c.t(x + w / 2, y + h + 2.2, title, size=7, weight="bold", color=INK, ha="center")
    if sub:
        c.t(x + w / 2, y + h + 5.0, sub, size=6, color=GREY, ha="center")


def draw(c: C) -> None:
    c.t(0.5, 1.5, "a", size=10, weight="bold", va="top")
    c.t(6, 1.8, "ChromData: tables joined by keys", size=8.5, weight="bold", va="top")
    c.t(64, 2.2, "format 2.2", size=6, color=GREY, va="top")

    # ---------------------------------------------------------------- bins axis (top)
    bx, by, bw, nb = 40, 13, 56, 14
    c.t(bx - 1.5, by + 1.6, "bins", size=7, weight="bold", ha="right")
    c.t(bx - 1.5, by + 4.6, "genomic loci", size=6, color=GREY, ha="right")
    c.rect(bx, by, bw, 3.2, fc=TINT[GREY], ec=LINE, lw=0.5)
    for k in range(1, nb):
        c.line([bx + bw * k / nb] * 2, [by, by + 3.2], color=GREY, lw=0.3)
    c.t(bx + bw + 1.5, by + 1.6, "chrom · start · end", size=6, color=GREY)
    rng = np.random.default_rng(3)
    for r, name in enumerate(["ATAC", "ChIP"]):
        yy = by + 4.2 + r * 3.0
        c.rect(bx, yy, bw, 2.6, fc=TINT[PURPLE], ec=PURPLE, lw=0.4)
        v = rng.gamma(1.5, 1, nb); v = v / v.max()
        for k, vv in enumerate(v):
            c.rect(bx + bw * k / nb + 0.6, yy + 2.6 - 2.2 * vv, bw / nb - 1.2, 2.2 * vv, fc=PURPLE, ec="none", z=3)
        c.t(bx + bw + 1.5, yy + 1.3, f"bin_tracks · {name}", size=6, color=PURPLE)
    for a0, a1 in [(0, 4), (4, 9), (9, 14)]:
        x0, x1 = bx + bw * a0 / nb + 0.4, bx + bw * a1 / nb - 0.4
        c.ax.add_patch(Polygon([[x0, by - 0.4], [(x0 + x1) / 2, by - 3.6], [x1, by - 0.4]], closed=True,
                               fc=TINT[TEAL], ec=TEAL, lw=0.4, zorder=2))
    c.t(bx + bw + 1.5, by - 1.8, "intervals · TADs, loops", size=6, color=TEAL)

    # ---------------------------------------------------------------- spots (left, tall)
    sx, sy, sh, sw = 13, 32, 36, 27
    table(c, sx, sy, sw, sh, INDIGO, rows=12)
    for i, col in enumerate(["bin_id", "trace_id", "cell_id"]):
        c.t(sx + (i + 0.5) * sw / 3, sy - 1.4, col, size=6, color=INDIGO, ha="center", weight="bold")
        if i:
            c.line([sx + i * sw / 3] * 2, [sy, sy + sh], color=INDIGO, lw=0.3)
    c.t(sx + sw / 2, sy + sh + 2.4, "spots", size=7, weight="bold", ha="center")
    c.t(sx + sw / 2, sy + sh + 5.2, "one row per observation", size=6, color=GREY, ha="center")
    cells_b = [0, 0.45, 0.8, 1.0]
    for i in range(3):
        a0, a1 = cells_b[i], cells_b[i + 1]
        c.rect(sx - 4.0, sy + sh * a0 + 0.2, 1.3, sh * (a1 - a0) - 0.4, fc=INDIGO, ec="none")
        nt = 3 if i < 2 else 2
        for k in range(nt):
            t0 = a0 + (a1 - a0) * k / nt; t1 = a0 + (a1 - a0) * (k + 1) / nt
            c.rect(sx - 2.3, sy + sh * t0 + 0.2, 1.3, sh * (t1 - t0) - 0.4, fc="#9fb2d3", ec="none")
    c.t(sx - 3.35, sy - 1.0, "cell", size=6, color=INDIGO, ha="center", va="bottom", rotation=90)
    c.t(sx - 1.65, sy - 1.0, "trace", size=6, color=INDIGO, ha="center", va="bottom", rotation=90)
    c.t(sx - 6.3, sy + sh / 2, "cell › trace › bin", size=6, color=GREY, ha="center", rotation=90)
    # coords (+ layers) and spot_tracks
    cx = sx + sw + 3
    for k in (2, 1):
        c.rect(cx + 1.0 * k, sy - 1.0 * k, 8, sh, fc="#fdf0e7", ec=ORANGE, lw=0.35, z=1)
    table(c, cx, sy, 8, sh, ORANGE, rows=12)
    for i, col in enumerate("xyz"):
        c.t(cx + (i + 0.5) * 8 / 3, sy - 1.4, col, size=6, color=ORANGE, ha="center", weight="bold")
        if i:
            c.line([cx + i * 8 / 3] * 2, [sy, sy + sh], color=ORANGE, lw=0.3)
    c.t(cx + 4, sy + sh + 2.4, "coords", size=7, weight="bold", ha="center", color=ORANGE)
    c.t(cx + 4, sy + sh + 5.2, "+ layers", size=6, color=GREY, ha="center")
    # on disk (format 2.2): keys + x, y, z once, one table per chromosome (tables/coords/);
    # every other spot-aligned column in cell-sorted primary tables (tables/primary/)
    bx0, bx1, byb = sx, cx + 8, sy + sh + 8.4
    c.line([bx0, bx0, bx1, bx1], [byb - 0.9, byb, byb, byb - 0.9], color=GREY, lw=0.4)
    c.t((bx0 + bx1) / 2, byb + 1.3, "on disk: keys + xyz stored once,\none table per chromosome", size=6,
        color=GREY, ha="center", va="top", linespacing=1.0)
    tx = cx + 13
    table(c, tx, sy, 8, sh, PURPLE, rows=12)
    c.t(tx + 4, sy - 1.4, "IF · …", size=6, color=PURPLE, ha="center", weight="bold")
    c.t(tx + 4, sy + sh + 2.4, "spot_tracks", size=7, weight="bold", ha="center", color=PURPLE)
    c.t(tx + 4, sy + sh + 5.2, "per spot", size=6, color=GREY, ha="center")
    c.line([tx, tx, tx + 8, tx + 8], [byb - 0.9, byb, byb, byb - 0.9], color=GREY, lw=0.4)
    c.t(tx + 4, byb + 1.3, "cell-sorted\nprimary", size=6, color=GREY, ha="center", va="top", linespacing=1.0)

    # bin_id → bins
    c.arrow((sx + sw / 6, sy - 3.2), (bx + 3, by + 10.4), rad=-0.3)
    c.key(sx + 10.5, 22.5, "bin_id")

    # ---------------------------------------------------------------- traces / cells (right)
    rx = tx + 22
    table(c, rx, 33, 16, 8, GREY, rows=4)
    c.t(rx + 8, 31.8, "traces", size=7, weight="bold", ha="center", va="bottom")
    table(c, rx, 49, 16, 13, GREY, rows=6)
    c.t(rx + 8, 47.8, "cells", size=7, weight="bold", ha="center", va="bottom")
    c.rect(rx + 17.5, 49, 5, 13, fc=TINT[PURPLE], ec=PURPLE, lw=0.5)
    for k in range(1, 6):
        c.line([rx + 17.5, rx + 22.5], [49 + 13 * k / 6] * 2, color="white", lw=0.35)
    c.t(rx + 20, 47.8, "cellm", size=7, weight="bold", ha="center", va="bottom", color=PURPLE)
    c.t(rx + 11.25, 64.6, "type · RNA · embeddings", size=6, color=GREY, ha="center")
    c.t(rx + 11.25, 67.4, "cell_type → groups", size=6, color=INDIGO, ha="center")
    # joins, drawn behind the spot tables
    c.arrow((sx + sw, sy + 5.5), (rx - 0.6, 37), rad=-0.12, z=0.5)
    c.key(tx + 15, 34.4, "trace_id")
    c.arrow((sx + sw, sy + sh * 0.62), (rx - 0.6, 55.5), rad=0.06, z=0.5)
    c.key(tx + 15, 52.2, "cell_id")

    # ---------------------------------------------------------------- contacts, results
    ex = rx + 26
    c.rect(ex, 33, 18, 10, fc="white", ec=TEAL, lw=0.6, ls=(0, (2.2, 1.2)), r=1.0)
    c.t(ex + 9, 36.2, "contacts", size=7, weight="bold", color=TEAL, ha="center")
    c.t(ex + 9, 39.8, ".cool · .scool", size=6, color=TEAL, ha="center")
    c.t(ex + 9, 45.2, "linked, not copied", size=6, color=GREY, ha="center")
    c.arrow((ex + 9, 33), (bx + bw - 4, by + 10.4), color=TEAL, ls=(0, (2, 1.2)), rad=0.25)
    c.t(ex + 10.5, 28.0, "by bins", size=6, color=TEAL)
    c.arrow((ex, 41.5), (rx + 22.8, 50.5), color=TEAL, ls=(0, (2, 1.2)), rad=-0.25)
    c.t(ex + 1.5, 49.8, "cell_map", size=6, color=TEAL)
    c.rect(ex, 55, 18, 4.4, fc=TINT[GREY], ec=LINE, lw=0.4, r=0.8)
    c.t(ex + 9, 57.2, "results", size=6, ha="center")
    c.rect(ex, 61, 18, 4.4, fc=TINT[GREY], ec=LINE, lw=0.4, r=0.8)
    c.t(ex + 9, 63.2, "uns", size=6, ha="center")

    # ---------------------------------------------------------------- on-disk layout (right column)
    # the actual store written by uchrom.core.zarrcd (format 2.2; spec.md); a glyph per node gives
    # its storage type: Parquet table, Zarr array or JSON attributes
    dx, dy = 127, 7
    c.rect(dx - 2, dy - 2.5, 44.5, H - dy + 1.5, fc="#f7f8fa", ec=LGREY, lw=0.5, r=1.5, z=0)
    c.t(dx, dy + 0.4, "x.chromdata.zarr", size=7, weight="bold")
    c.t(dx + 21.5, dy + 0.5, "format 2.2", size=6, color=GREY)
    c.t(dx, dy + 4.1, "Zarr + Parquet", size=6, color=GREY)
    logo(c, "zarr", dx + 16.2, dy + 2.55, h=3.1)
    logo(c, "parquet", dx + 26.6, dy + 2.7, h=2.8)
    rows = [  # name, storage, colour, note (same line), note (next line), depth
        ("zarr.json", "json", GREY, "version · orders", None, 0),
        ("tables/", "dir", GREY, None, None, 0),
        ("coords/chrom=…/", "parquet", ORANGE, None, "x · y · z + keys, one table per\nchromosome (cell › trace › bin)", 1),
        ("primary/", "parquet", PURPLE, None, "spot tracks · layers · other spot\ncolumns, cell-sorted, no keys", 1),
        ("derived/", "parquet", INDIGO, None, "spot columns stored once per\nbin / cell / trace", 1),
        ("bins · cells · traces", "parquet", GREY, None, None, 1),
        ("intervals/ · points/", "parquet", TEAL, None, None, 1),
        ("index/", "zarr", INDIGO, None, "run offsets: primary ↔ coords", 0),
        ("cellm/ · binm/", "zarr", PURPLE, None, None, 0),
        ("results/ · uns/", "json", GREY, "+ provenance", None, 0),
        ("contacts/ · links/", "json", TEAL, None, "→ .cool · .scool · .h5mu · .h5ad", 0),
    ]
    y = dy + 8.6
    last = {0: dy + 5.4, 1: None}  # y of the previous sibling (or the parent) per depth
    for name, kind, col, inline, below, depth in rows:
        x = dx + 0.8 + depth * 3.4
        top = last[depth] if last[depth] is not None else last[depth - 1] + 1.4
        c.line([x, x], [top, y], color=LGREY, lw=0.5)
        c.line([x, x + 2.0], [y, y], color=LGREY, lw=0.5)
        glyph(c, kind, x + 3.4, y, col)
        tx_ = x + 5.6
        c.t(tx_, y, name, size=6.5, color=INK)
        if inline:
            c.t(tx_ + 0.98 * len(name) + 1.8, y, inline, size=6, color=GREY)
        step = 3.9
        if below:
            nl = below.count("\n") + 1
            c.t(tx_, y + 1.4, below, size=6, color=GREY, va="top", linespacing=1.0)
            step += 2.35 * nl
        last[depth] = y
        if depth == 0:
            last[1] = None
        y += step
    ly = y + 0.6
    for i, (kind, lab) in enumerate([("parquet", "Parquet"), ("zarr", "Zarr array"), ("json", "JSON")]):
        xx = dx + 0.8 + [0, 12.0, 26.5][i]
        glyph(c, kind, xx + 1.2, ly, INK)
        c.t(xx + 3.4, ly, lab, size=6, color=GREY)
    c.t(dx, ly + 3.6, "spot tables read on access (backed);", size=6, color=GREY)
    c.t(dx, ly + 6.4, ".cdz = the same store in one zip file", size=6, color=GREY)
    # logos are images: keep the mm coordinate frame
    c.ax.set_xlim(0, W); c.ax.set_ylim(H, 0); c.ax.set_aspect("auto")


def glyph(c: "C", kind: str, x: float, y: float, col: str) -> None:
    """Storage-type glyph centred at (x, y): a small table (Parquet), a
    stacked-cube chunk (Zarr array), braces (JSON attributes), a dash
    (directory)."""
    if kind == "parquet":
        w, h = 2.6, 2.2
        c.rect(x - w / 2, y - h / 2, w, h, fc="white", ec=col, lw=0.5, z=5)
        c.rect(x - w / 2, y - h / 2, w, h / 3, fc=col, ec="none", z=5)
        c.line([x - w / 2, x + w / 2], [y + h / 6, y + h / 6], color=col, lw=0.3, z=6)
        c.line([x, x], [y - h / 6, y + h / 2], color=col, lw=0.3, z=6)
    elif kind == "zarr":
        s = 1.8
        c.rect(x - s / 2 + 0.55, y - s / 2 - 0.55, s, s, fc="white", ec=col, lw=0.4, z=5)
        c.rect(x - s / 2, y - s / 2, s, s, fc=col, ec=col, lw=0.4, z=6)
    elif kind == "json":
        c.t(x, y - 0.1, "{ }", size=5.5, color=col, ha="center", weight="bold", zorder=6)
    else:
        c.line([x - 1.0, x + 1.0], [y, y], color=LGREY, lw=1.2, z=5)


_LOGO_CACHE: dict = {}


def logo(c: "C", key: str, x: float, y: float, h: float) -> None:
    """An official logo from ``paper/fig1/logos_ext/`` (``<key>.svg``,
    rasterised with rsvg-convert, or ``<key>.png``; unaltered, the empty
    canvas around it trimmed), placed at (x, y) (top left, mm) with height
    ``h`` mm (aspect kept)."""
    import subprocess

    from PIL import Image

    if key not in _LOGO_CACHE:
        base = HERE.parent / "fig1" / "logos_ext"
        svg, src = base / f"{key}.svg", base / f"{key}.png"
        if svg.exists():
            src = HERE / "_cache" / f"logo_{key}.png"
            src.parent.mkdir(exist_ok=True)
            if not src.exists() or src.stat().st_mtime < svg.stat().st_mtime:
                subprocess.run(["rsvg-convert", "-h", "600", str(svg), "-o", str(src)], check=True)
        im = Image.open(src).convert("RGBA")
        _LOGO_CACHE[key] = np.asarray(im.crop(im.getchannel("A").getbbox()))   # empty canvas trimmed
    im = _LOGO_CACHE[key]
    w = h * im.shape[1] / im.shape[0]
    # resample once to 1200 dpi at the printed size (no aliasing at 300 dpi output)
    px = max(8, int(round(h / 25.4 * 1200)))
    small = np.asarray(Image.fromarray(im).resize((max(8, int(round(px * w / h))), px), Image.LANCZOS))
    c.ax.imshow(small, extent=(x, x + w, y + h, y), zorder=8, interpolation="antialiased")


def main() -> None:
    fig = plt.figure(figsize=(W * MM, H * MM))
    draw(C(fig))
    out = HERE / "_cache" / "panel_a_preview.png"
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out, dpi=300)
    print(out)


if __name__ == "__main__":
    main()
