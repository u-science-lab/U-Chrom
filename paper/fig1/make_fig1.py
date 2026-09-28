"""Figure 1 — U-Chrom overview (vector PDF).

  a  workflow: sequencing + imaging inputs → recon / im → ChromData → analysis
  b  anatomy of ChromData (AnnData-style block diagram)
  c  flat storage, hierarchical access — real data (Takei 2025 cerebellum,
     DNA seqFISH+): field of view → one nucleus → one trace → spots
  d  one container, many modalities — real data panels

Data come from example-data/ (see example-data/README.md); ``--refresh``
re-extracts the small caches in ``_cache/`` from the .h5cd / .mcool files.

    python paper/fig1/make_fig1.py            # → paper/fig1/fig1_overview.pdf (+ .png preview)
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CACHE = HERE / "_cache"

MM = 1 / 25.4
W, H = 180.0, 208.0  # figure size, mm

mpl.rcParams.update({
    "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 6, "axes.linewidth": 0.4, "xtick.major.width": 0.4, "ytick.major.width": 0.4,
    "xtick.major.size": 1.5, "ytick.major.size": 1.5, "xtick.labelsize": 5, "ytick.labelsize": 5,
    "axes.labelsize": 5.5, "axes.titlesize": 6,
})

# palette
SEQ = "#2a9d8f"      # sequencing
IMG = "#e07a3f"      # imaging
CORE = "#34568b"     # ChromData
ANA = "#6c6f7f"      # downstream analysis
INK = "#222222"
MUTED = "#8a8f98"
LIGHT = {SEQ: "#e3f3f1", IMG: "#fbeadf", CORE: "#e4eaf4", ANA: "#eeeff2"}
# a clean single allele: 197 loci, Spearman(genomic, spatial distance) = 0.59.
# (chr6_a1 has 510 loci and rho = 0.08 — likely both homologs merged.)
TRACE, TRACE_CHROM = "1_0_34_chr15_a1", "chr15"
CELL_TYPE = {"Granule": "#4c78a8", "Bergmann": "#e45756", "Other": "#9c9c9c", "MLI1": "#eeca3b",
             "MLI2+PLI": "#b279a2", "Purkinje": "#d67195"}


# --------------------------------------------------------------------------- data

def refresh_cache() -> None:
    import warnings

    import cooler

    from uchrom import ChromData

    warnings.filterwarnings("ignore")
    CACHE.mkdir(exist_ok=True)
    cd = ChromData.read(ROOT / "example-data/takei2025_fov0/takei2025_fov0.h5cd")
    sp = cd.spots
    df = pd.DataFrame({"cell_id": sp.cell_id.astype(str), "chrom": sp.chrom.astype(str), "start": sp.start,
                       "trace_id": sp.trace_id.astype(str), "x": cd.coords[:, 0], "y": cd.coords[:, 1],
                       "z": cd.coords[:, 2], "H3K27ac": cd.tracks["H3K27ac"].values,
                       "LaminB1": cd.tracks["LaminB1"].values, "H3K9me3": cd.tracks["H3K9me3"].values})
    df.sample(60000, random_state=0).to_csv(CACHE / "fov_spots_sample.csv", index=False)
    df[df.cell_id == "1_0_34"].to_csv(CACHE / "cell_1_0_34.csv", index=False)
    c = cd.cells
    pd.DataFrame({"cell_id": c.index, "cell_type": c.cell_type, "vol": c.nuc_volume_um3}).to_csv(
        CACHE / "fov_cells.csv", index=False)

    s = ChromData.read(ROOT / "example-data/schicar_mop/schicar_mop.h5cd")
    u = s.cellm["paper_umap"]
    pd.DataFrame({"u1": u[:, 0], "u2": u[:, 1], "cell_type": s.cells["cell_type"].astype(str).values}).to_csv(
        CACHE / "schicar_umap.csv", index=False)
    clr = cooler.Cooler(str(ROOT / "example-data/schicar_mop/contacts_all.mcool") + "::resolutions/250000")
    np.save(CACHE / "schicar_chr2.npy", clr.matrix(balance=False).fetch("chr2:20,000,000-80,000,000"))

    m = ChromData.read(ROOT / "example-data/sim_cell1/sim_cell1.cdz")
    pd.DataFrame({"chrom": m.spots.chrom.astype(str), "start": m.spots.start, "x": m.coords[:, 0],
                  "y": m.coords[:, 1], "z": m.coords[:, 2]}).to_csv(CACHE / "sim_cell1.csv", index=False)


def chrom_order(names):
    def key(c):
        c = c.replace("chr", "")
        return (0, int(c)) if c.isdigit() else (1, c)
    return sorted(set(names), key=key)


def chrom_colors(names):
    order = chrom_order(names)
    cmap = plt.get_cmap("turbo")
    return {c: cmap(0.05 + 0.9 * i / max(1, len(order) - 1)) for i, c in enumerate(order)}


def rotate(xyz, elev=20, azim=35):
    """Orthographic projection of centred xyz → 2-D (a fixed 'camera')."""
    p = xyz - xyz.mean(0)
    a, e = np.radians(azim), np.radians(elev)
    rz = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    rx = np.array([[1, 0, 0], [0, np.cos(e), -np.sin(e)], [0, np.sin(e), np.cos(e)]])
    q = p @ rz.T @ rx.T
    return q[:, [0, 2]], q[:, 1]  # screen xy, depth


# --------------------------------------------------------------------------- drawing helpers

class Canvas:
    """Figure-wide axes in millimetres, y pointing down."""

    def __init__(self, fig):
        self.fig = fig
        self.ax = fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, W)
        self.ax.set_ylim(H, 0)
        self.ax.axis("off")

    def box(self, x, y, w, h, fc="white", ec=INK, lw=0.5, r=1.2, ls="-", z=1, alpha=1):
        p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}", fc=fc, ec=ec, lw=lw,
                           ls=ls, zorder=z, alpha=alpha)
        self.ax.add_patch(p)
        return p

    def rect(self, x, y, w, h, fc, ec="none", lw=0.4, z=2, hatch=None, alpha=1):
        self.ax.add_patch(Rectangle((x, y), w, h, fc=fc, ec=ec, lw=lw, zorder=z, hatch=hatch, alpha=alpha))

    def text(self, x, y, s, size=6, color=INK, ha="left", va="center", weight="normal", z=5, **kw):
        fd = dict(kw.pop("fontdict", None) or {})
        size = fd.pop("size", size)
        kw.update(fd)
        return self.ax.text(x, y, s, fontsize=size, color=color, ha=ha, va=va, fontweight=weight, zorder=z, **kw)

    def arrow(self, x0, y0, x1, y1, color=INK, lw=0.7, ls="-", z=3, head=4, rad=0.0):
        a = FancyArrowPatch((x0, y0), (x1, y1), arrowstyle=f"-|>,head_length={head * 0.12},head_width={head * 0.07}",
                            color=color, lw=lw, ls=ls, zorder=z, shrinkA=0, shrinkB=0,
                            connectionstyle=f"arc3,rad={rad}", mutation_scale=10)
        self.ax.add_patch(a)

    def line(self, xs, ys, color=INK, lw=0.5, ls="-", z=3):
        self.ax.plot(xs, ys, color=color, lw=lw, ls=ls, zorder=z, solid_capstyle="butt")

    def label(self, x, y, s):
        self.text(x, y, s, size=9, weight="bold", va="top")

    def inset(self, x, y, w, h):
        """Data axes at (x, y, w, h) mm (y from the top)."""
        return self.fig.add_axes([x / W, 1 - (y + h) / H, w / W, h / H])


ART = HERE / "art"


def place_image(cv: "Canvas", name, x, y, w, h, badge=None, pad=0.8):
    """Generated artwork (paper/fig1/art/<name>.png), cropped to content, fit in (x, y, w, h) mm.

    ``badge`` = ring colour: draws a white rounded badge behind it (the art has a white background).
    """
    from PIL import Image

    im = Image.open(ART / f"{name}.png").convert("RGB")
    a = np.asarray(im).astype(int)
    ys, xs = np.where(a.min(-1) < 235)
    im = im.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    if badge:
        cv.box(x, y, w, h, fc="white", ec=badge, lw=0.5, r=min(w, h) * 0.22, z=4)
        x, y, w, h = x + pad, y + pad, w - 2 * pad, h - 2 * pad
    iw, ih = im.size
    s_ = min(w / iw, h / ih)
    dw, dh = iw * s_, ih * s_
    ax = cv.inset(x + (w - dw) / 2, y + (h - dh) / 2, dw, dh)
    ax.imshow(np.asarray(im), interpolation="lanczos")
    ax.axis("off")
    ax.set_zorder(5)


def uchrom_mark(cv: "Canvas", x, y, h):
    """U-Chrom mark: a bead chain bent into a U — teal (sequencing) and orange (imaging)
    arms meeting in indigo (the shared container).  (x, y) = top-left, h = height, mm."""
    w = h * 0.72
    n_arm, n_bot = 7, 5
    pts, cols, rad = [], [], []
    for i in range(n_arm):  # left arm, top → bottom, gentle zig-zag
        t = i / (n_arm - 1)
        pts.append((x + w * (0.08 + 0.07 * (i % 2)), y + h * (0.04 + 0.62 * t)))
        cols.append(SEQ); rad.append(h * (0.035 + 0.025 * t))
    for i in range(n_bot):  # bottom arc
        a = np.pi * (1 - (i + 1) / (n_bot + 1))
        pts.append((x + w / 2 + w * 0.40 * np.cos(a), y + h * 0.70 + h * 0.24 * np.sin(a)))
        cols.append(CORE); rad.append(h * (0.062 if i % 2 == 0 else 0.042))
    for i in range(n_arm):  # right arm, bottom → top
        t = 1 - i / (n_arm - 1)
        pts.append((x + w * (0.92 - 0.07 * ((i + 1) % 2)), y + h * (0.04 + 0.62 * t)))
        cols.append(IMG); rad.append(h * (0.035 + 0.025 * t))
    P = np.array(pts)
    for i in range(len(P) - 1):
        c = cols[i] if cols[i] == cols[i + 1] else CORE
        cv.ax.plot(P[i:i + 2, 0], P[i:i + 2, 1], color=c, lw=h * 0.09, zorder=6, solid_capstyle="round")
    for (px_, py_), c, r in zip(P, cols, rad):
        cv.ax.add_patch(plt.Circle((px_, py_), r, color=c, zorder=7, lw=0))
    return w


def uchrom_logo(cv: "Canvas", x, y, h, subtitle=None):
    w = uchrom_mark(cv, x, y, h)
    tx = x + w + h * 0.25
    fs = h * 2.0  # pt per mm of mark height
    t = cv.text(tx, y + h * 0.40, "U", size=fs, weight="bold", color=CORE, va="center")
    cv.fig.canvas.draw()
    bb = t.get_window_extent().transformed(cv.ax.transData.inverted())
    cv.text(bb.x1, y + h * 0.40, "-Chrom", size=fs, weight="bold", color="#3a3f47", va="center")
    if subtitle:
        cv.text(tx, y + h * 0.88, subtitle, size=5.6, color=MUTED, va="center")


def chromdata_mark(cv: "Canvas", x, y, s):
    """ChromData mark: three isometric data sheets with a bead chain leaving the top one."""
    def sheet(cx_, cy_, fc, grid):
        dx, dy = s * 0.45, s * 0.2
        poly = np.array([[cx_ - dx, cy_], [cx_, cy_ - dy], [cx_ + dx, cy_], [cx_, cy_ + dy]])
        cv.ax.add_patch(plt.Polygon(poly, closed=True, fc=fc, ec="white", lw=0.6, zorder=6))
        if grid:
            for f in (1 / 3, 2 / 3):
                a0 = poly[0] + (poly[1] - poly[0]) * f; a1 = poly[3] + (poly[2] - poly[3]) * f
                b0 = poly[0] + (poly[3] - poly[0]) * f; b1 = poly[1] + (poly[2] - poly[1]) * f
                for p0, p1 in ((a0, a1), (b0, b1)):
                    cv.ax.plot([p0[0], p1[0]], [p0[1], p1[1]], color="white", lw=0.35, zorder=6.5)
    cx_ = x + s / 2
    for k, fc in enumerate([IMG, SEQ, CORE]):
        sheet(cx_, y + s * (0.78 - 0.17 * k), fc, grid=(k == 2))
    chain = np.array([[0.05, 0.44], [0.12, 0.30], [0.05, 0.17], [0.15, 0.07], [0.27, 0.02]])
    P = np.c_[cx_ + chain[:, 0] * s, y + chain[:, 1] * s]
    cv.ax.plot(P[:, 0], P[:, 1], color=CORE, lw=s * 0.08, zorder=7)
    for i, (px_, py_) in enumerate(P):
        cv.ax.add_patch(plt.Circle((px_, py_), s * (0.055 if i else 0.045), color=CORE, ec="white",
                                   lw=0.3, zorder=8))


def mono(s):
    return {"family": "monospace", "size": 5.2}


# --------------------------------------------------------------------------- panel a

def panel_a(cv: Canvas, y0=4.0):
    cv.label(2, y0, "a")
    uchrom_logo(cv, 7, y0 - 1.0, 8, subtitle="one data model for sequencing- and imaging-based 3-D genomics")
    y0 += 8
    top = y0 + 5
    # inputs --------------------------------------------------------------
    cv.text(4, top, "Input data", size=6.5, weight="bold")
    seq = ["Hi-C / Dip-C  .pairs", "Contact maps  .cool .mcool .hic", "Single-cell Hi-C  .scool",
           "scHiCAR  RNA + ATAC + contacts"]
    img = ["Chromatin tracing  (4DN FOF-CT)", "DNA seqFISH+ multi-omics", "IF / RNA-FISH channels, RNA spots"]
    yy = top + 9
    cv.box(3, yy, 47, 5 + 4.2 * len(seq), fc=LIGHT[SEQ], ec=SEQ, lw=0.6)
    place_image(cv, "el_sequencing", 36.8, yy + 3.5, 12.4, 10.5, badge=SEQ, pad=0.6)
    cv.text(5, yy + 3, "Sequencing", color=SEQ, weight="bold")
    for i, s in enumerate(seq):
        cv.text(6, yy + 7.5 + 4.2 * i, "•  " + s, size=5.1)
    yi = yy + 5 + 4.2 * len(seq) + 3
    cv.box(3, yi, 47, 5 + 4.2 * len(img), fc=LIGHT[IMG], ec=IMG, lw=0.6)
    place_image(cv, "el_microscope", 37.6, yi + 1.4, 11.4, 11.0, badge=IMG, pad=0.6)
    cv.text(5, yi + 3, "Imaging", color=IMG, weight="bold")
    for i, s in enumerate(img):
        cv.text(6, yi + 7.5 + 4.2 * i, "•  " + s, size=5.1)
    seq_mid, img_mid = yy + (5 + 4.2 * len(seq)) / 2, yi + (5 + 4.2 * len(img)) / 2

    # processing ------------------------------------------------------------
    px, pw = 57, 36
    cv.text(px, top, "Structure generation", size=6.5, weight="bold")
    cv.box(px, yy, pw, 21.8, fc="white", ec=SEQ, lw=0.6)
    cv.text(px + 2, yy + 3, "uchrom.recon", color=SEQ, weight="bold", fontdict=mono(0))
    place_image(cv, "el_fiber", px + pw - 10.5, yy + 0.9, 9.5, 5.2)
    for i, s in enumerate(["NucDynamics · GEM  (single cell)", "MDS / SMACOF  (bulk, GPU)",
                           "GEM-FISH  (Hi-C + FISH)"]):
        cv.text(px + 2.5, yy + 8 + 4.4 * i, s, size=5.3)
    cv.box(px, yi, pw, 17.6, fc="white", ec=IMG, lw=0.6)
    cv.text(px + 2, yi + 3, "uchrom.im", color=IMG, weight="bold", fontdict=mono(0))
    for i, s in enumerate(["spot → trace alignment", "coordinate imputation"]):
        cv.text(px + 2.5, yi + 8 + 4.4 * i, s, size=5.3)
    cv.arrow(50.5, seq_mid, px - 0.8, seq_mid, color=SEQ)
    cv.arrow(50.5, img_mid, px - 0.8, img_mid, color=IMG)

    # core ------------------------------------------------------------------
    cx, cw = 100, 34
    cy, ch = yy + 1, (yi + 17.6) - yy - 2
    cv.text(cx + cw / 2, top, "One container", size=6.5, weight="bold", ha="center")
    cv.box(cx, cy, cw, ch, fc=LIGHT[CORE], ec=CORE, lw=1.0, r=2)
    chromdata_mark(cv, cx + 3.5, cy + 1.3, 6.8)
    cv.text(cx + 11.5, cy + 4.6, "ChromData", size=8, weight="bold", color=CORE)
    cv.text(cx + cw / 2, cy + 10.0, "cell → trace → spot / bin", size=5.3, color=CORE, ha="center")
    slots = ["coords", "spots", "cells", "cellm", "tracks", "traces", "layers", "points", "results", "uns"]
    for i, s in enumerate(slots):
        r, c = divmod(i, 2)
        bx, by = cx + 3 + c * 14.5, cy + 12.8 + r * 4.2
        cv.box(bx, by, 13.5, 3.4, fc="white", ec=CORE, lw=0.4, r=0.8, z=2)
        cv.text(bx + 6.75, by + 1.75, s, ha="center", color=CORE, fontdict=mono(0), z=6)
    cv.text(cx + cw / 2, cy + ch - 2.6, ".h5cd  (HDF5, versioned)", size=5.2, color=CORE, ha="center")
    cv.arrow(px + pw + 0.5, yy + 10.9, cx - 0.8, cy + ch * 0.35, color=SEQ)
    cv.arrow(px + pw + 0.5, yi + 8.8, cx - 0.8, cy + ch * 0.7, color=IMG)
    # direct routes: imaging tables already have coordinates; contacts are linked
    # imaging tables already carry coordinates: straight into ChromData, under uchrom.im
    yb_ = yi + 17.6 + 3.2
    cv.line([25.5, 25.5, cx + cw / 2], [yi + 5 + 4.2 * len(img) + 0.3, yb_, yb_], color=IMG, lw=0.5)
    cv.arrow(cx + cw / 2, yb_, cx + cw / 2, cy + ch + 0.6, color=IMG, lw=0.5)
    cv.text(74, yb_ + 1.8, "coordinates read directly (FOF-CT, seqFISH+)", size=4.8, color=IMG, ha="center")
    # contacts are referenced, not copied
    dash = (0, (2, 1.2))
    cv.line([25.5, 25.5, cx + cw / 2], [yy - 0.3, yy - 4, yy - 4], color=SEQ, lw=0.5, ls=dash)
    cv.arrow(cx + cw / 2, yy - 4, cx + cw / 2, cy - 0.6, color=SEQ, lw=0.5, ls=dash)
    cv.text(74, yy - 5.6, "contacts linked, not copied  (link_cool · link_scool · link_mudata)",
            size=4.8, color=SEQ, ha="center")

    # downstream --------------------------------------------------------------
    dx, dw = 142, 36
    cv.text(dx, top, "Analysis & visualization", size=6.5, weight="bold")
    mods = [("uchrom.strc", "TADs · loops · compartments"), ("uchrom.fea", "per-bin geometric features"),
            ("uchrom.emb", "cell embeddings (RNA, IF, Hi-C)"), ("uchrom.pl", "plots, trace statistics"),
            ("uchrom.browser", "desktop + web browser")]
    step = (ch + 4) / len(mods)
    for i, (m, d) in enumerate(mods):
        by = yy + i * step
        cv.box(dx, by, dw, step - 1.6, fc=LIGHT[ANA], ec=ANA, lw=0.5)
        cv.text(dx + 2, by + 2.4, m, color=INK, weight="bold", fontdict=mono(0))
        cv.text(dx + 2, by + (step - 1.6) - 2.2, d, size=5.0, color="#444")
        cv.arrow(cx + cw + 0.5, cy + ch / 2, dx - 0.8, by + (step - 1.6) / 2, color=CORE, lw=0.5)
    return yi + 17.6 + 6


# --------------------------------------------------------------------------- panel b

def panel_b(cv: Canvas, y0: float):
    cv.label(2, y0, "b")
    chromdata_mark(cv, 7, y0 - 0.6, 5.5)
    cv.text(13.5, y0 + 1.4, "Anatomy of ChromData", size=6.5, weight="bold", va="top")
    top = y0 + 12
    rows = 44  # height of the spots axis block
    # spots axis bracket
    cv.text(3.2, top + rows / 2, "n_spots", size=5.2, color=MUTED, rotation=90, ha="center")
    # hierarchy bars along the spots axis: cells → traces
    cell_breaks = [0, 0.42, 0.78, 1.0]
    for i in range(3):
        a, b = cell_breaks[i], cell_breaks[i + 1]
        cv.rect(5.2, top + a * rows + 0.2, 1.1, (b - a) * rows - 0.4, fc=["#4c78a8", "#e45756", "#eeca3b"][i])
        n = 3 if i < 2 else 2
        for k in range(n):
            ta, tb = a + (b - a) * k / n, a + (b - a) * (k + 1) / n
            cv.rect(6.8, top + ta * rows + 0.2, 1.0, (tb - ta) * rows - 0.4, fc="#bbbbbb")
    cv.text(5.75, top - 1.4, "cell", size=4.3, color=MUTED, ha="center", rotation=90, va="bottom")
    cv.text(7.3, top - 1.4, "trace", size=4.3, color=MUTED, ha="center", rotation=90, va="bottom")

    def table(x, w, cols, fc, ec, title, sub, y=top, h=rows, hatch_rows=True):
        cv.rect(x, y, w, h, fc=fc, ec=ec, lw=0.6, z=2)
        cw = w / len(cols)
        for i, c in enumerate(cols):
            if i:
                cv.line([x + i * cw] * 2, [y, y + h], color=ec, lw=0.25, z=3)
            cv.text(x + (i + 0.5) * cw, y - 1.2, c, size=4.4, ha="center", va="bottom", rotation=90, color=ec)
        if hatch_rows:
            for k in range(1, 11):
                cv.line([x, x + w], [y + h * k / 11] * 2, color="white", lw=0.35, z=3)
        cv.text(x + w / 2, y + h + 2.5, title, ha="center", color=ec, fontdict=mono(0))
        if sub:
            cv.text(x + w / 2, y + h + 5.5, sub, ha="center", size=4.6, color=MUTED)

    table(9, 17, ["chrom", "start", "end", "trace_id", "cell_id"], "#dde3ea", "#5a6b80", "spots", "DataFrame")
    # layers stacked behind coords
    for k in (2, 1):
        cv.rect(29 + k * 1.3, top - k * 1.3, 9, rows, fc="#c9d6ec", ec=CORE, lw=0.4, z=1.5)
    table(29, 9, ["x", "y", "z"], "#9fb6dd", CORE, "coords", "(n_spots, 3)")
    cv.text(41.8, top + rows + 2.5, "layers", size=4.8, color=CORE, fontdict=mono(0))
    table(47, 13, ["ATAC", "H3K27ac", "LaminB1", "…"], "#f6dccb", IMG, "tracks", "per-spot signals")

    # cell-level ---------------------------------------------------------------
    rx = 66
    cv.text(rx, top - 5.5, "per cell", size=5.2, color=MUTED)
    cv.rect(rx, top, 14, 13, fc="#e8e0ef", ec="#7a5c99", lw=0.6)
    for k in range(1, 5):
        cv.line([rx, rx + 14], [top + 13 * k / 5] * 2, color="white", lw=0.35, z=3)
    cv.text(rx + 7, top + 15.3, "cells", ha="center", color="#7a5c99", fontdict=mono(0))
    cv.text(rx + 11, top + 18.3, "cell type, RNA, embeddings", ha="center", size=4.4, color=MUTED)
    cv.rect(rx + 16, top, 6, 13, fc="#d3c3e3", ec="#7a5c99", lw=0.6)
    cv.text(rx + 19, top + 15.3, "cellm", ha="center", color="#7a5c99", fontdict=mono(0))
    # trace-level + other
    yb = top + 23
    cv.rect(rx, yb, 14, 7, fc="#e6e6e6", ec="#777", lw=0.6)
    cv.text(rx + 7, yb + 9.2, "traces", ha="center", color="#555", fontdict=mono(0))
    small = [("points", "RNA spots, puncta"), ("results", "TADs, loops, comp."), ("uns", "metadata, links")]
    for i, (s, d) in enumerate(small):
        by = yb + 13 + i * 5.2
        cv.box(rx - 0.5, by, 24.5, 4.2, fc="white", ec="#999", lw=0.4, r=0.8)
        cv.text(rx + 1, by + 2.1, s, color=INK, fontdict=mono(0))
        cv.text(rx + 9.3, by + 2.1, d, size=4.2, color=MUTED)
    # external linked files
    ey = top + rows + 12
    cv.text(3, ey + 2.6, "linked, not copied:", size=5.0, color=SEQ)
    for i, f in enumerate([".mcool", ".scool", ".h5mu"]):
        bx = 25 + i * 14
        cv.box(bx, ey, 12, 5.2, fc="white", ec=SEQ, lw=0.6, ls=(0, (2, 1)), r=0.8)
        cv.text(bx + 6, ey + 2.6, f, ha="center", color=SEQ, fontdict=mono(0))
    cv.arrow(66.5, ey + 2.6, rx + 1, yb + 13 + 2 * 5.2 + 4.6, color=SEQ, lw=0.5, ls=(0, (2, 1)), rad=0.25)
    cv.line([62, 66.5], [ey + 2.6, ey + 2.6], color=SEQ, lw=0.5, ls=(0, (2, 1)))
    return ey + 6


# --------------------------------------------------------------------------- panel c

def panel_c(cv: Canvas, y0: float, x0: float = 95):
    cv.label(x0 - 3, y0, "c")
    cv.text(x0 + 2, y0 + 1.4, "Flat storage, hierarchical access  (Takei et al. 2025, DNA seqFISH+)",
            size=6.5, weight="bold", va="top")
    top = y0 + 9
    s = pd.read_csv(CACHE / "fov_spots_sample.csv")
    cells = pd.read_csv(CACHE / "fov_cells.csv").set_index("cell_id")
    one = pd.read_csv(CACHE / "cell_1_0_34.csv")

    # 1. field of view
    ax = cv.inset(x0, top + 4, 24, 24)
    s = s[s.cell_id.isin(cells.index)]
    col = s.cell_id.map(cells.cell_type).map(CELL_TYPE).fillna("#999")
    ax.scatter(s.x, s.y, s=0.05, c=col.values, lw=0, rasterized=False)
    c34 = one[["x", "y"]].mean()
    ax.add_patch(plt.Circle((c34.x, c34.y), 6.5, fill=False, ec=INK, lw=0.6))
    ax.set_aspect("equal"); ax.axis("off")
    ax.plot([s.x.min(), s.x.min() + 20], [s.y.min() - 4] * 2, color=INK, lw=0.8)
    ax.text(s.x.min() + 10, s.y.min() - 6, "20 µm", fontsize=4.5, ha="center", va="top")
    cv.text(x0 + 12, top + 1.2, "47 cells · 1,500 traces", size=5.0, ha="center")
    cv.text(x0 + 12, top + 30.8, "ChromData", ha="center", color=CORE, fontdict=mono(0))
    # legend of cell types
    for i, (k, v) in enumerate(CELL_TYPE.items()):
        r, c = divmod(i, 2)
        cv.ax.scatter([x0 + 1.5 + c * 12.5], [top + 34.5 + r * 2.6], s=4, color=v, lw=0, zorder=6)
        cv.text(x0 + 2.6 + c * 12.5, top + 34.5 + r * 2.6, k, size=4.4)

    # 2. one nucleus
    nx = x0 + 29
    ax = cv.inset(nx, top + 4, 24, 24)
    cc = chrom_colors(one.chrom)
    xy, depth = rotate(one[["x", "y", "z"]].to_numpy(), elev=80, azim=0)
    one = one.assign(px=xy[:, 0], py=xy[:, 1], d=depth)
    for tid, t in one.sort_values("start").groupby("trace_id", sort=False):
        ax.plot(t.px, t.py, color=cc[t.chrom.iloc[0]], lw=0.25, alpha=0.9)
    ax.set_aspect("equal"); ax.axis("off")
    cv.text(nx + 12, top + 1.2, "cell 1_0_34 (Bergmann) · 19 traces", size=5.0, ha="center")
    cv.text(nx + 12, top + 30.8, 'cd.get_cell("1_0_34")', ha="center", color=CORE, fontdict=mono(0))

    # 3. one trace segment
    tx = x0 + 58
    seg = one[one.trace_id == TRACE].sort_values("start")
    ax = cv.inset(tx, top + 4, 24, 24)
    pts = seg[["px", "py"]].to_numpy()
    mb = seg.start.to_numpy() / 1e6
    ax.plot(pts[:, 0], pts[:, 1], color="#b0b0b0", lw=0.15, alpha=0.6, zorder=1)
    sc = ax.scatter(pts[:, 0], pts[:, 1], c=mb, cmap="viridis", s=2.2, lw=0, zorder=2)
    ax.set_aspect("equal"); ax.axis("off")
    cv.text(tx + 12, top + 1.2, f"{TRACE_CHROM}, allele 1 · {len(seg)} loci", size=5.0, ha="center")
    cv.text(tx + 12, top + 30.8, f'cd.get_trace("…{TRACE_CHROM}_a1")', ha="center", color=CORE, fontdict=mono(0))
    cax = cv.inset(tx + 5, top + 33.5, 14, 1.2)
    cb = plt.colorbar(sc, cax=cax, orientation="horizontal")
    cb.outline.set_linewidth(0.3); cb.ax.tick_params(labelsize=4.2, length=1, pad=0.5)
    cv.text(tx + 12, top + 38.8, "genomic position (Mb)", size=4.4, ha="center", color=MUTED)

    for xa in (x0 + 25, x0 + 54):
        cv.arrow(xa, top + 16, xa + 3.2, top + 16, color=INK, lw=0.6)

    # spot row
    r = seg.iloc[0]
    cv.box(x0 + 24, top + 42.5, 59, 5.2, fc="#f4f6f9", ec="#b8c2d0", lw=0.4, r=0.8)
    cv.text(x0 + 53.5, top + 45.1,
            f"one spot = one row:  {TRACE_CHROM}:{int(r.start):,}-{int(r.start) + 25000:,}  →  "
            f"({r.x:.1f}, {r.y:.1f}, {r.z:.1f}) µm",
            size=4.6, color="#445", ha="center")
    return top + 48


# --------------------------------------------------------------------------- panel d

def panel_d(cv: Canvas, y0: float):
    cv.label(2, y0, "d")
    cv.text(7, y0 + 1.4, "The same container across modalities", size=6.5, weight="bold", va="top")
    top, h, w, gap, x = y0 + 12, 28, 29, 6.2, 7
    one = pd.read_csv(CACHE / "cell_1_0_34.csv")
    tr = one[one.trace_id == TRACE].sort_values("start").reset_index(drop=True)

    def caption(i, title, code, color):
        cx = x + i * (w + gap) + w / 2
        cv.text(cx, top - 4.4, title, size=5.4, ha="center", weight="bold", color=color)
        cv.text(cx, top + h + 9.2, code, ha="center", color=CORE, fontdict=mono(0))

    # d1 distance matrix of one trace (imaging)
    xyz = tr[["x", "y", "z"]].to_numpy()
    d = np.sqrt(((xyz[:, None] - xyz[None]) ** 2).sum(-1))
    ax = cv.inset(x, top, w, h)
    im = ax.imshow(d, cmap="viridis_r", vmax=np.percentile(d, 98), interpolation="none", rasterized=True)
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_linewidth(0.3)
    caption(0, "3-D distances (imaging)", "cd.compute_distances()", IMG)
    cax = cv.inset(x + w + 0.8, top + 4, 1.0, 12)
    cb = plt.colorbar(im, cax=cax); cb.outline.set_linewidth(0.3)
    cb.ax.tick_params(labelsize=4.2, length=1, pad=0.5)
    cv.text(x + w / 2, top + h + 6.0, f"{TRACE_CHROM}, one allele, {len(tr)} loci · µm", size=4.4, ha="center", color=MUTED)

    # d2 tracks along the trace
    x2 = x + (w + gap)
    for k, (mark, colr) in enumerate([("H3K27ac", "#d95f02"), ("LaminB1", "#1b9e77"), ("H3K9me3", "#7570b3")]):
        ax = cv.inset(x2, top + k * (h / 3), w, h / 3 - 1.4)
        v = tr[mark].to_numpy()
        pos = tr.start.to_numpy() / 1e6
        ax.fill_between(pos, 0, v, color=colr, lw=0, step="mid")
        ax.set_xlim(pos.min(), pos.max()); ax.set_yticks([])
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.text(0.01, 0.98, mark, transform=ax.transAxes, fontsize=4.6, va="top", color=colr, zorder=5,
                path_effects=[mpl.patheffects.withStroke(linewidth=1.5, foreground="white")])
        if k < 2:
            ax.set_xticks([])
            ax.spines["bottom"].set_visible(False)
        else:
            ax.set_xlabel(f"{TRACE_CHROM} (Mb)", labelpad=0.5)
    caption(1, "Per-spot signals (IF)", "cd.tracks", IMG)
    cv.text(x2 + w / 2, top + h + 6.0, "same allele, z-scored intensity", size=4.4, ha="center", color=MUTED)

    # d3 contact map (sequencing, linked mcool)
    x3 = x + 2 * (w + gap)
    m = np.load(CACHE / "schicar_chr2.npy").astype(float)
    ax = cv.inset(x3, top, w, h)
    ax.imshow(np.log1p(m), cmap="YlOrRd", vmax=np.percentile(np.log1p(m), 99.5), interpolation="none",
              rasterized=True, extent=[20, 80, 80, 20])
    ax.tick_params(labelsize=4.2, pad=0.8); ax.set_xticks([20, 50, 80]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_linewidth(0.3)
    ax.set_xlabel("chr2 (Mb)", labelpad=0.5)
    caption(2, "Contacts (scHiCAR)", 'cd.link_cool("….mcool")', SEQ)
    cv.text(x3 + w / 2, top + h + 6.0, "5,313 cells merged · 250 kb", size=4.4, ha="center", color=MUTED)

    # d4 UMAP of cells (cellm)
    x4 = x + 3 * (w + gap)
    u = pd.read_csv(CACHE / "schicar_umap.csv")
    types = sorted(u.cell_type.unique())
    pal = plt.get_cmap("tab20")
    cmap = {t: pal(i % 20) for i, t in enumerate(types)}
    ax = cv.inset(x4, top, w, h)
    ax.scatter(u.u1, u.u2, s=0.25, c=u.cell_type.map(cmap).tolist(), lw=0)
    ax.set_xticks([]); ax.set_yticks([]); ax.set_aspect("equal", adjustable="datalim")
    for sp in ax.spines.values():
        sp.set_visible(False)
    for t in ["Oligo", "Astro", "L23IT.1", "MGL", "Vip"]:
        if t in set(u.cell_type):
            c = u[u.cell_type == t][["u1", "u2"]].median()
            ax.text(c.u1, c.u2, t, fontsize=4.3, ha="center", va="center",
                    path_effects=[mpl.patheffects.withStroke(linewidth=1.2, foreground="white")])
    caption(3, "Cells (scHiCAR RNA)", 'cd.cellm["paper_umap"]', SEQ)
    cv.text(x4 + w / 2, top + h + 6.0, f"{len(u):,} cells · {len(types)} types", size=4.4, ha="center",
            color=MUTED)

    # d5 reconstructed single-cell structure (NucDynamics)
    x5 = x + 4 * (w + gap)
    sim = pd.read_csv(CACHE / "sim_cell1.csv")
    cc = chrom_colors(sim.chrom)
    xy, _ = rotate(sim[["x", "y", "z"]].to_numpy(), elev=20, azim=40)
    sim = sim.assign(px=xy[:, 0], py=xy[:, 1])
    ax = cv.inset(x5, top, w, h)
    for ch, t in sim.sort_values(["chrom", "start"]).groupby("chrom"):
        ax.plot(t.px, t.py, color=cc[ch], lw=0.2)
    ax.set_aspect("equal"); ax.axis("off")
    caption(4, "Reconstruction (Hi-C)", "uchrom.recon.sc.nucdyn", SEQ)
    cv.text(x5 + w / 2, top + h + 6.0, "one mESC, 20 chromosomes, 100 kb", size=4.4, ha="center", color=MUTED)
    return top + h + 11


# --------------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-extract the data caches from example-data/")
    ap.add_argument("--out", default=str(HERE / "fig1_overview.pdf"))
    args = ap.parse_args()
    if args.refresh or not (CACHE / "cell_1_0_34.csv").exists():
        refresh_cache()
    import matplotlib.patheffects  # noqa: F401  (used via mpl.patheffects)

    fig = plt.figure(figsize=(W * MM, H * MM))
    cv = Canvas(fig)
    ya = panel_a(cv)
    yb = ya + 6
    panel_b(cv, yb)
    yc = panel_c(cv, yb)
    panel_d(cv, max(yc, yb + 76) + 1)
    fig.savefig(args.out)
    fig.savefig(Path(args.out).with_suffix(".png"), dpi=300)
    print(args.out)


if __name__ == "__main__":
    main()
