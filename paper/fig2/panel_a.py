"""Figure 2a (DRAFT) — ChromData 2.0: tables, keys and on-disk layout.

Follows docs/source/guide/chromdata_2_0_design.md (Overview, section 2 `bins`,
section 4 "Format 2.0 HDF5 layout").  Schematic only — no data.

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
W, H = 170.0, 80.0

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
                c.line([x + i * cw] * 2, [y, y + h], color=color, lw=0.25)
            c.t(x + (i + 0.5) * cw, y - 1.0, col, size=6, color=color, ha="center", va="bottom", rotation=90)
    if title:
        c.t(x + w / 2, y + h + 2.2, title, size=7, weight="bold", color=INK, ha="center")
    if sub:
        c.t(x + w / 2, y + h + 5.0, sub, size=6, color=GREY, ha="center")


def draw(c: C) -> None:
    c.t(0.5, 1.5, "a", size=10, weight="bold", va="top")
    c.t(6, 1.8, "ChromData: tables joined by keys", size=8.5, weight="bold", va="top")
    c.t(64, 2.2, "format 2.0", size=6, color=GREY, va="top")

    # ---------------------------------------------------------------- bins axis (top)
    bx, by, bw, nb = 40, 13, 56, 14
    c.t(bx - 1.5, by + 1.6, "bins", size=7, weight="bold", ha="right")
    c.t(bx - 1.5, by + 4.6, "genomic loci", size=6, color=GREY, ha="right")
    c.rect(bx, by, bw, 3.2, fc=TINT[GREY], ec=LINE, lw=0.5)
    for k in range(1, nb):
        c.line([bx + bw * k / nb] * 2, [by, by + 3.2], color=GREY, lw=0.25)
    c.t(bx + bw + 1.5, by + 1.6, "chrom · start · end", size=6, color=GREY)
    rng = np.random.default_rng(3)
    for r, name in enumerate(["ATAC", "ChIP"]):
        yy = by + 4.2 + r * 3.0
        c.rect(bx, yy, bw, 2.6, fc=TINT[PURPLE], ec=PURPLE, lw=0.4)
        v = rng.gamma(1.5, 1, nb); v = v / v.max()
        for k, vv in enumerate(v):
            c.rect(bx + bw * k / nb + 0.6, yy + 2.6 - 2.2 * vv, bw / nb - 1.2, 2.2 * vv, fc=PURPLE, ec="none", z=3)
        c.t(bx + bw + 1.5, yy + 1.3, f"tracks · {name}", size=6, color=PURPLE)
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
            c.line([sx + i * sw / 3] * 2, [sy, sy + sh], color=INDIGO, lw=0.25)
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
    c.t(sx - 6.3, sy + sh / 2, "sorted cell › trace › bin", size=6, color=GREY, ha="center", rotation=90)
    # coords (+ layers) and spot_tracks
    cx = sx + sw + 3
    for k in (2, 1):
        c.rect(cx + 1.0 * k, sy - 1.0 * k, 8, sh, fc="#fdf0e7", ec=ORANGE, lw=0.35, z=1)
    table(c, cx, sy, 8, sh, ORANGE, rows=12)
    for i, col in enumerate("xyz"):
        c.t(cx + (i + 0.5) * 8 / 3, sy - 1.4, col, size=6, color=ORANGE, ha="center", weight="bold")
        if i:
            c.line([cx + i * 8 / 3] * 2, [sy, sy + sh], color=ORANGE, lw=0.25)
    c.t(cx + 4, sy + sh + 2.4, "coords", size=7, weight="bold", ha="center", color=ORANGE)
    c.t(cx + 4, sy + sh + 5.2, "+ layers", size=6, color=GREY, ha="center")
    tx = cx + 13
    table(c, tx, sy, 8, sh, PURPLE, rows=12)
    c.t(tx + 4, sy - 1.4, "IF · …", size=6, color=PURPLE, ha="center", weight="bold")
    c.t(tx + 4, sy + sh + 2.4, "spot_tracks", size=7, weight="bold", ha="center", color=PURPLE)
    c.t(tx + 4, sy + sh + 5.2, "per spot", size=6, color=GREY, ha="center")

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
    dx, dy = 127, 8
    c.rect(dx - 2, dy - 2.5, 44, 70, fc="#f7f8fa", ec=LGREY, lw=0.5, r=1.5, z=0)
    c.t(dx, dy + 0.5, "data.h5cd", size=7, weight="bold")
    c.t(dx + 15.5, dy + 0.5, "HDF5, versioned", size=6, color=GREY)
    rows = [
        ("bins/ · intervals/", "eager", GREY, ""),
        ("tracks/ · binm/", "eager", PURPLE, "per bin"),
        ("spots/", "lazy", INDIGO, "bin_id · trace_id · cell_id"),
        ("coords · layers/", "lazy", ORANGE, "n_spots × 3, chunked"),
        ("spot_tracks/", "lazy", PURPLE, "per spot"),
        ("traces/ · cells/ · cellm/", "eager", GREY, ""),
        ("index/", "eager", INDIGO, "cell & trace offsets"),
        ("contacts/ · links/", "external", TEAL, "→ .cool · .scool · .h5mu"),
        ("results/ · uns/", "eager", GREY, ""),
    ]
    for i, (name, mode, col, note) in enumerate(rows):
        y = dy + 6.2 + i * 6.0
        c.line([dx + 0.8, dx + 0.8], [y - 6.0 + 1.8 if i else y - 3.2, y], color=LGREY, lw=0.5)
        c.line([dx + 0.8, dx + 3.0], [y, y], color=LGREY, lw=0.5)
        if mode == "eager":
            c.ax.plot(dx + 4.4, y, "o", ms=3.2, color=col, mec=col, zorder=5)
        else:
            c.ax.plot(dx + 4.4, y, "o", ms=3.2, mfc="white", mec=col, mew=0.8, zorder=5)
        if mode == "external":
            c.ax.plot(dx + 4.4, y, "o", ms=5.2, mfc="none", mec=col, mew=0.4, ls=":", zorder=5)
        c.t(dx + 6.4, y, name, size=6.5, color=INK)
        if note:
            c.t(dx + 6.4, y + 2.5, note, size=6, color=GREY)
    ly = dy + 6.2 + len(rows) * 6.0 + 0.4
    for i, (lab, mfc) in enumerate([("loaded on open", INK), ("read on access", "white")]):
        xx = dx + 1 + i * 20
        c.ax.plot(xx, ly, "o", ms=3.0, mfc=mfc, mec=INK, mew=0.7, zorder=5)
        c.t(xx + 1.8, ly, lab, size=6, color=GREY)


def main() -> None:
    fig = plt.figure(figsize=(W * MM, H * MM))
    draw(C(fig))
    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"fig2a_draft.{ext}", dpi=300)
    print(HERE / "fig2a_draft.pdf")


if __name__ == "__main__":
    main()
