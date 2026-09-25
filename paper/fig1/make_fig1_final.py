"""Figure 1 — U-Chrom places sequencing- and imaging-based 3-D genome data on one shared index.

  a  assays capture different facets (contacts / geometry / molecular state):
     a flat AI-generated illustration (art3/a_flat_1.png) with vector labels;
     its Hi-C wall (scHiCAR MOp, chr7:53–68 Mb) and floor tracks (Takei 2025
     chr15 IF) are repainted with real data
  b  ChromData: modality layers on shared genomic bins, an observation-level
     strip, and the bridges between layers (vector, real-data-derived shapes)
  c  the ecosystem: interfaces, methods, the ChromData core, and formats with
     their communities' logos (logos_ext/, see SOURCES.md; unaltered)

Data caches live in ``_cache/`` (re-extract with make_fig1.py --refresh); every
dataset is catalogued in example-data/README.md.  Legend: legend.md.

    python paper/fig1/make_fig1_final.py   # → paper/fig1/fig1_final.pdf + .png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle
from matplotlib.transforms import Affine2D

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CACHE = HERE / "_cache"

MM = 1 / 25.4
W, H = 170.0, 186.6

mpl.rcParams.update({
    "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
    "font.family": "sans-serif", "font.sans-serif": ["Arial"],
})

# type scale (pt) — five sizes only
F_LETTER, F_TITLE, F_LABEL, F_SEC, F_TAG = 10, 8.5, 7, 6, 6   # Arial only; nothing < 6 pt
LW, LW_THIN = 0.5, 0.3                 # journal: all lines > 0.25 pt

# palette
SEQ = "#2a9d8f"      # sequencing / contacts
IMG = "#e07a3f"      # imaging / geometry
OMX = "#8e7cc3"      # single-cell omics / features
CORE = "#34568b"     # ChromData
INK = "#2b2f36"
GREY = "#7d838c"
LIGHTGREY = "#c9cdd3"
PALE = {SEQ: "#eef7f6", IMG: "#fdf3ec", OMX: "#f4f1fa", CORE: "#edf1f7"}


def ramp(c, lo="#ffffff", name=None):
    return LinearSegmentedColormap.from_list(name or c, [lo, c])


CM_SEQ = ramp(SEQ)
CM_OMX = ramp(OMX)
CM_IMG = LinearSegmentedColormap.from_list("img", ["#f6c9a8", IMG, "#8a3f14"])

TRACE = "1_0_34_chr15_a1"   # clean single allele: 197 loci, Spearman rho 0.59


# --------------------------------------------------------------------------- data

def cache_markers():
    """cells x marker genes (scHiCAR RNA) for the floor of panel a.

    5 glia / vascular types x 12 random cells x 4 markers each.  Counts are
    log1p, kNN-smoothed (k = 15 in the stored RNA PCA, as in MAGIC-style
    display smoothing) and z-scored per gene; a gene is a marker of the type
    with its highest mean.  (The 500 stored HVGs carry few neuron markers.)
    """
    out = CACHE / "schicar_rna_markers.csv"
    if out.exists():
        return pd.read_csv(out, index_col=0)
    import warnings

    from sklearn.neighbors import NearestNeighbors

    from uchrom import ChromData
    warnings.filterwarnings("ignore")
    cd = ChromData.read(ROOT / "example-data/schicar_mop/schicar_mop.h5cd")
    c = cd.cells
    ct = c.cell_type.astype(str).to_numpy()
    genes = [g for g in c.columns if g.startswith("rna.")]
    X = np.log1p(c[genes].astype(float).to_numpy())
    pcs = cd.cellm["rna_pca"]
    idx = NearestNeighbors(n_neighbors=15).fit(pcs).kneighbors(pcs, return_distance=False)
    Xs = X[idx].mean(1)
    G = pd.DataFrame((Xs - Xs.mean(0)) / (Xs.std(0) + 1e-9), columns=genes)
    types = ["Astro", "OPC", "Oligo", "MGL", "Endo"]
    T = pd.DataFrame({t: G[ct == t].mean() for t in types}).T
    sel = []
    for t in types:
        cand = T.columns[(T.idxmax() == t).values]
        sel += list(T.loc[t, cand].sort_values(ascending=False).index[:4])
    rng = np.random.default_rng(1)
    rows = []
    for t in types:
        rows += list(rng.choice(np.where(ct == t)[0], 12, replace=False))
    Z = G.iloc[rows][sel]
    Z.index = c.index[rows]
    Z = Z.assign(cell_type=ct[rows])
    Z.to_csv(out)
    return Z


def load():
    cell = pd.read_csv(CACHE / "cell_1_0_34.csv")
    hic = np.load(CACHE / "schicar_chr2.npy").astype(float)
    mk = cache_markers()
    return cell, hic, mk


# --------------------------------------------------------------------------- canvas

class Canvas:
    """Whole-figure axes in millimetres, y pointing down."""

    def __init__(self, fig):
        self.fig = fig
        self.ax = fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, W)
        self.ax.set_ylim(H, 0)
        self.ax.axis("off")

    def fix(self):
        self.ax.set_xlim(0, W)
        self.ax.set_ylim(H, 0)

    def text(self, x, y, s, size=F_LABEL, color=INK, ha="left", va="center", weight="normal", z=20, **kw):
        return self.ax.text(x, y, s, fontsize=size, color=color, ha=ha, va=va, fontweight=weight, zorder=z, **kw)

    def box(self, x, y, w, h, fc="white", ec=INK, lw=LW, r=1.0, ls="-", z=2, alpha=1.0):
        p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}", fc=fc, ec=ec, lw=lw,
                           ls=ls, zorder=z, alpha=alpha)
        self.ax.add_patch(p)
        return p

    def poly(self, pts, fc="none", ec=INK, lw=LW, z=2, alpha=1.0, ls="-", **kw):
        p = Polygon(np.asarray(pts), closed=True, fc=fc, ec=ec, lw=lw, zorder=z, alpha=alpha, ls=ls,
                    joinstyle="round", **kw)
        self.ax.add_patch(p)
        return p

    def line(self, xs, ys, color=INK, lw=LW, ls="-", z=3, alpha=1.0, **kw):
        return self.ax.plot(xs, ys, color=color, lw=lw, ls=ls, zorder=z, alpha=alpha,
                            solid_capstyle="round", **kw)

    def arrow(self, p0, p1, color=INK, lw=0.6, rad=0.0, z=15, ls="-", head=3.2):
        a = FancyArrowPatch(p0, p1, arrowstyle=f"-|>,head_length={head * 0.11},head_width={head * 0.065}",
                            color=color, lw=lw, ls=ls, zorder=z, shrinkA=0, shrinkB=0,
                            connectionstyle=f"arc3,rad={rad}", mutation_scale=10, joinstyle="miter")
        self.ax.add_patch(a)
        return a

    def paint(self, img, p0, u, v, cmap, vmin=None, vmax=None, z=4, alpha=1.0, clip=None):
        """Paint image rows x cols on the parallelogram p0 + s*u + t*v (cols → s, rows → t)."""
        im = self.ax.imshow(img, extent=(0, 1, 0, 1), origin="lower", cmap=cmap, vmin=vmin, vmax=vmax,
                            interpolation="nearest", aspect="auto", zorder=z, alpha=alpha)
        m = Affine2D(np.array([[u[0], v[0], p0[0]], [u[1], v[1], p0[1]], [0, 0, 1.0]]))
        im.set_transform(m + self.ax.transData)
        if clip is not None:
            im.set_clip_path(clip)
        return im

    def letter(self, x, y, s):
        self.text(x, y, s, size=F_LETTER, weight="bold", va="top")

    def title(self, x, y, s, **kw):
        return self.text(x, y, s, size=F_TITLE, weight="bold", va="top", **kw)


# --------------------------------------------------------------------------- glyphs

def chromdata_mark(cv: Canvas, x, y, s):
    """Three isometric data sheets with a bead chain leaving the top one."""
    def sheet(cx_, cy_, fc, grid):
        dx, dy = s * 0.45, s * 0.2
        poly = np.array([[cx_ - dx, cy_], [cx_, cy_ - dy], [cx_ + dx, cy_], [cx_, cy_ + dy]])
        cv.ax.add_patch(Polygon(poly, closed=True, fc=fc, ec="white", lw=0.5, zorder=30))
        if grid:
            for f in (1 / 3, 2 / 3):
                a0 = poly[0] + (poly[1] - poly[0]) * f; a1 = poly[3] + (poly[2] - poly[3]) * f
                b0 = poly[0] + (poly[3] - poly[0]) * f; b1 = poly[1] + (poly[2] - poly[1]) * f
                for p0, p1 in ((a0, a1), (b0, b1)):
                    cv.ax.plot([p0[0], p1[0]], [p0[1], p1[1]], color="white", lw=0.3, zorder=31)
    cx_ = x + s / 2
    for k, fc in enumerate([IMG, SEQ, CORE]):
        sheet(cx_, y + s * (0.78 - 0.17 * k), fc, grid=(k == 2))
    chain = np.array([[0.05, 0.44], [0.12, 0.30], [0.05, 0.17], [0.15, 0.07], [0.27, 0.02]])
    P = np.c_[cx_ + chain[:, 0] * s, y + chain[:, 1] * s]
    cv.ax.plot(P[:, 0], P[:, 1], color=CORE, lw=s * 0.08, zorder=32)
    for i, (px_, py_) in enumerate(P):
        cv.ax.add_patch(Circle((px_, py_), s * (0.055 if i else 0.045), color=CORE, ec="white", lw=0.3, zorder=33))


def icon_python(cv, x, y, s, color):
    cv.text(x + s / 2, y + s / 2, ">>>", size=F_TAG, color=color, ha="center", weight="bold")


def icon_terminal(cv, x, y, s, color):
    cv.box(x, y + s * 0.12, s, s * 0.76, fc="white", ec=color, lw=LW, r=0.5, z=21)
    cv.text(x + s * 0.14, y + s * 0.52, ">_", size=F_SEC, color=color, weight="bold", z=22)


def icon_browser(cv, x, y, s, color):
    cv.box(x, y + s * 0.12, s, s * 0.76, fc="white", ec=color, lw=LW, r=0.5, z=21)
    cv.line([x, x + s], [y + s * 0.32] * 2, color=color, lw=LW_THIN, z=22)
    for k in range(3):
        cv.ax.add_patch(Circle((x + s * (0.13 + 0.12 * k), y + s * 0.22), s * 0.035, color=color, zorder=22))
    # tiny triangle map inside
    cv.poly([[x + s * 0.2, y + s * 0.78], [x + s * 0.5, y + s * 0.45], [x + s * 0.8, y + s * 0.78]],
            fc=PALE[SEQ], ec=SEQ, lw=LW_THIN, z=22)


def icon_plug(cv, x, y, s, color):
    """MCP connector: a plug with two prongs and a cable."""
    cx = x + s * 0.5
    cv.box(cx - s * 0.22, y + s * 0.30, s * 0.44, s * 0.34, fc="white", ec=color, lw=LW, r=0.4, z=21)
    for dx in (-0.1, 0.1):
        cv.line([cx + s * dx] * 2, [y + s * 0.30, y + s * 0.10], color=color, lw=0.6, z=22)
    cv.line([cx, cx, cx + s * 0.25], [y + s * 0.64, y + s * 0.82, y + s * 0.92], color=color, lw=0.6, z=22)


def icon_puzzle(cv, x, y, s, color):
    b = s * 0.62
    x0, y0 = x + s * 0.12, y + s * 0.26
    cv.box(x0, y0, b, b, fc="white", ec=color, lw=LW, r=0.3, z=21)
    cv.ax.add_patch(Circle((x0 + b / 2, y0), s * 0.12, fc="white", ec=color, lw=LW, zorder=22))
    cv.ax.add_patch(Circle((x0 + b, y0 + b / 2), s * 0.12, fc="white", ec=color, lw=LW, zorder=22))
    cv.ax.add_patch(Rectangle((x0 + b / 2 - s * 0.13, y0 + 0.2), s * 0.26, s * 0.14, fc="white", ec="none", zorder=23))
    cv.ax.add_patch(Rectangle((x0 + b - 0.25, y0 + b / 2 - s * 0.13), s * 0.14, s * 0.26, fc="white", ec="none", zorder=23))


def loop_arrow(cv, c, r, color, lw=0.6, a0=40, a1=320, z=15):
    """Circular arrow around centre c (screen mm; y down)."""
    t = np.radians(np.linspace(a0, a1, 40))
    xs, ys = c[0] + r * np.cos(t), c[1] - r * np.sin(t)
    cv.line(xs[:-2], ys[:-2], color=color, lw=lw, z=z)
    cv.arrow((xs[-3], ys[-3]), (xs[-1], ys[-1]), color=color, lw=lw, head=2.4, z=z)


# --------------------------------------------------------------------------- images

LOGOS = CACHE / "logos"          # rasterised (rsvg-convert) / copied from logos_ext/, padding trimmed only


def _crop_art(name):
    """Crop an art2/ illustration to its non-white content (cached)."""
    from PIL import Image
    out = CACHE / f"{name}_crop.png"
    if not out.exists():
        im = Image.open(HERE / "art2" / f"{name}.png").convert("RGB")
        a = np.asarray(im).astype(int)
        ys, xs = np.where(a.min(-1) < 238)
        im.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)).save(out)
    return out


def place_png(cv: Canvas, path, x, y, w=None, h=None, z=5, plate=None):
    """Place a PNG with its aspect ratio kept; give w or h (mm). Returns (w, h)."""
    from PIL import Image
    im = Image.open(path)
    iw, ih = im.size
    if w is None:
        w = h * iw / ih
    if h is None:
        h = w * ih / iw
    if plate:
        cv.box(x - 0.5, y - 0.5, w + 1.0, h + 1.0, fc="white", ec=plate, lw=LW_THIN * 1.6, r=0.8, z=z - 1)
    ax = cv.fig.add_axes([x / W, 1 - (y + h) / H, w / W, h / H])
    ax.imshow(np.asarray(im.convert("RGBA")), interpolation="none")
    ax.axis("off")
    ax.set_zorder(z)
    return w, h


def logo(cv, key, x, y, h, **kw):
    return place_png(cv, LOGOS / f"{key}.png", x, y, h=h, **kw)


def leader(cv, p0, p1, color):
    cv.line([p0[0], p1[0]], [p0[1], p1[1]], color=color, lw=0.35, z=30, alpha=0.9)
    cv.ax.add_patch(Circle(p1, 0.55, fc=color, ec="white", lw=0.35, zorder=31))


def measure(cv, t):
    if not hasattr(cv, "_r"):
        cv._r = cv.fig.canvas.get_renderer()
    bb = t.get_window_extent(cv._r).transformed(cv.ax.transData.inverted())
    return bb.x1 - bb.x0



# --------------------------------------------------------------------------- shared

OUTLINE = "#3a3f47"
A_BOTTOM = 97.0      # a and b end on the same y
TITLE_Y = 2.0
KO = dict(boxstyle="square,pad=0.15", fc="white", ec="none")   # white knock-out behind labels


HIC_REGION = ("chr7", 53_000_000, 68_000_000)   # 60 bins at 250 kb, scHiCAR (all cells), ICE-balanced


def hic_window():
    """ICE-balanced (computed on the whole chr7 cis matrix) log contacts for HIC_REGION."""
    out = CACHE / "hic_chr7_53_68.npy"
    if out.exists():
        return np.load(out)
    import cooler
    c = cooler.Cooler(str(ROOT / "example-data/schicar_mop/contacts_all.mcool") + "::resolutions/250000")
    ch, a, b = HIC_REGION
    m = c.matrix(balance=False).fetch(ch).astype(float)
    cov = m.sum(0)
    bad = cov < np.percentile(cov[cov > 0], 5)
    m[bad] = 0; m[:, bad] = 0
    for _ in range(50):                                   # iterative correction (ICE)
        sm = m.sum(0); sm = sm / np.mean(sm[sm > 0]); sm[sm == 0] = 1
        m /= sm[:, None]; m /= sm[None]
    i0, i1 = a // 250_000, b // 250_000
    w = np.log1p(m[i0:i1, i0:i1] * 1e3)
    np.save(out, w)
    return w


def paint_real_hic(cv: Canvas, Q):
    """Cover the illustration's stylised triangle and paint the real map in the wall plane."""
    from matplotlib.colors import BoundaryNorm, ListedColormap
    A, C, B = Q(69, 625), Q(69, 220), Q(356, 488)        # triangle corners in the 1024-px art
    ctr = (A + B + C) / 3
    grow = lambda p, d: p + (p - ctr) / np.linalg.norm(p - ctr) * d  # noqa: E731
    hyp = B - C
    nrm = np.array([hyp[1], -hyp[0]]) / np.linalg.norm(hyp)          # outward (up-right) normal
    if nrm[1] > 0:
        nrm = -nrm
    wall = (206 / 255, 228 / 255, 226 / 255)                          # sampled flat wall colour
    cv.poly([grow(A, 0.5), grow(C, 0.5) + nrm * 0.9, B + nrm * 1.1 + (B - C) / np.linalg.norm(B - C) * 0.3,
             grow(B, 0.4)], fc=wall, ec="none", z=1)
    L = hic_window()
    n = len(L)
    iu = np.triu_indices(n, 1)
    lo, hi_ = np.percentile(L[iu], [2, 99.3])
    q = np.clip((L - lo) / (hi_ - lo), 0, 1) ** 0.95
    tones = ["#ffffff", "#e3f2ef", "#bfe3dd", "#86cbc1", "#3fa697", "#1f7a6f"]
    lvl = np.floor(q * len(tones) * 0.999)
    img = np.where(np.tril(np.ones((n, n))) > 0, lvl, np.nan)   # i >= j: the triangle A-C-B
    cmap = ListedColormap(tones); cmap.set_bad(alpha=0)
    norm = BoundaryNorm(np.arange(-0.5, len(tones)), len(tones))
    im = cv.ax.imshow(img, extent=(0, n, n, 0), origin="upper", cmap=cmap, norm=norm,
                      interpolation="none", aspect="auto", zorder=2)
    M = Affine2D(np.array([[(B - A)[0] / n, (A - C)[0] / n, C[0]],
                           [(B - A)[1] / n, (A - C)[1] / n, C[1]], [0, 0, 1.0]]))
    tr = M + cv.ax.transData
    im.set_transform(tr)
    cv.poly([A, C, B], fc="none", ec="#9fb8b4", lw=LW_THIN, z=2.2)


def _tracks(cell, marks=("H3K27ac", "LaminB1", "H3K9me3"), nbins=48):
    """Real IF profiles along the Takei 2025 chr15 trace, binned and scaled to 0..1."""
    tr = cell[cell.trace_id == TRACE].sort_values("start")
    edges = np.linspace(tr.start.min(), tr.start.max() + 1, nbins + 1)
    bi = np.clip(np.digitize(tr.start.to_numpy(), edges) - 1, 0, nbins - 1)
    out = {}
    for m in marks:
        v = pd.Series(tr[m].to_numpy()).groupby(bi).mean().reindex(range(nbins)).interpolate().bfill().ffill().to_numpy()
        out[m] = (v - v.min()) / (np.ptp(v) + 1e-9)
    return out


def paint_floor_tracks(cv: Canvas, Q, cell, img_path, ext):
    """Replace the illustration's floor (UMAP clusters) with three real signal tracks."""
    from PIL import Image
    Bk, Lf, Rt = np.array([509, 543.]), np.array([27, 778.]), np.array([997, 781.5])   # floor corners (art px)
    F = lambda u, v: Q(*(Bk + u * (Lf - Bk) + v * (Rt - Bk)))  # noqa: E731
    floor = (222 / 255, 216 / 255, 233 / 255)                   # sampled flat floor colour
    clip = Rectangle((ext[0], ext[3]), ext[1] - ext[0], ext[2] - ext[3], transform=cv.ax.transData)
    cover = cv.poly([F(0.02, 0.02), F(0.975, 0.02), F(0.975, 0.975), F(0.02, 0.975)], fc=floor, ec="none", z=1)
    cover.set_clip_path(clip)
    # put the nucleus back on top of the cover (same pixels, clipped to its circle)
    im = cv.ax.imshow(np.asarray(Image.open(img_path)), extent=ext, zorder=1.5, interpolation="lanczos")
    circ = Circle(tuple(Q(506, 479)), 147 * (ext[1] - ext[0]) / 973, transform=cv.ax.transData)
    im.set_clip_path(circ)
    # nucleus → floor projection (dashed, as in the other two walls)
    p0, p1 = Q(506, 628), F(0.40, 0.22)
    cv.line([p0[0], p1[0]], [p0[1], p1[1]], color=OUTLINE, lw=LW_THIN * 1.6, ls=(0, (2.0, 1.4)), z=2.5)
    rows = _tracks(cell)
    v0, v1 = 0.16, 0.90
    for k, (mark, u) in enumerate(zip(rows, (0.42, 0.62, 0.82))):
        vals = rows[mark]
        n = len(vals)
        a_, b_ = F(u, v0), F(u, v1)
        cv.line([a_[0], b_[0]], [a_[1], b_[1]], color="#6d5aa8", lw=LW_THIN, z=2.6)
        for i, val in enumerate(vals):
            vc = v0 + (v1 - v0) * (i + 0.5) / n
            w2 = (v1 - v0) / n * 0.32
            q0, q1 = F(u, vc - w2), F(u, vc + w2)
            hgt = 0.25 + 2.3 * val
            cv.poly([q0, q1, q1 - [0, hgt], q0 - [0, hgt]], fc=OMX, ec="none", z=2.7)
        end = F(u, v1 + 0.012) - [0, 0.4]
        lab = np.array([F(0.62, 1.0)[0] + 5.0, F(0.62, 1.0)[1] - 2.2 + 3.0 * k])
        cv.line([end[0], lab[0] - 0.6], [end[1], lab[1]], color="#6d5aa8", lw=LW_THIN, z=31, alpha=0.8)
        cv.text(lab[0], lab[1], mark, size=F_SEC, color="#6d5aa8", va="center", z=32)
    return F


def panel_a(cv: Canvas, cell):
    cv.letter(0.5, 1.0, "a")
    cv.title(4.8, TITLE_Y, "Assays capture different facets of 3-D genome organisation")
    from PIL import Image
    src = HERE / "art3" / "a_flat_1.png"
    out = CACHE / "a_flat_1_crop.png"
    ox, oy, cw, ch = 26, 17, 973, 988                    # content bbox in the 1024-px original
    if not out.exists():
        Image.open(src).convert("RGB").crop((ox, oy, ox + cw, oy + ch)).save(out)
    yi = 15.0
    hi = A_BOTTOM - 3.2 - yi
    wi = hi * cw / ch
    xi = 90.0 - wi
    place_png(cv, out, xi, yi, w=wi, z=4)
    sx, sy = wi / cw, hi / ch
    Q = lambda px, py: np.array([xi + (px - ox) * sx, yi + (py - oy) * sy])  # noqa: E731
    paint_real_hic(cv, Q)
    F = paint_floor_tracks(cv, Q, cell, out, (xi, xi + wi, yi + hi, yi))

    def block(x, y, title, grey, color, ha="left"):
        cv.text(x, y, title, size=F_LABEL, color=color, weight="bold", ha=ha, z=32)
        cv.text(x, y + 3.2, grey, size=F_SEC, color=GREY, ha=ha, z=32)

    block(1.0, 9.6, "Contacts: which loci touch", "Hi-C, scHi-C", SEQ)
    leader(cv, (10.0, 14.2), Q(150, 420), SEQ)
    block(90.0, 9.6, "Geometry: where loci are", "chromatin tracing", "#c4561f", ha="right")
    leader(cv, (80.0, 14.2), Q(800, 250), IMG)
    block(1.0, A_BOTTOM - 3.4, "Molecular state: what loci carry", "ChIP, ATAC, RNA, IF", "#6d5aa8")
    leader(cv, (14.0, A_BOTTOM - 4.8), F(0.62, 0.30) - [0, 0.6], OMX)


# --------------------------------------------------------------------------- panel b (vector)

def _tads(hic, n_top=5, w=4, dist=4, min_split=9):
    """Two-level domains from an insulation score on the scHiCAR chr2 map (bins)."""
    from scipy.signal import find_peaks
    m = hic
    n = len(m)
    ins = np.array([m[max(0, i - w):i, i + 1:i + w + 1].mean() if w <= i < n - w else np.nan for i in range(n)])
    ins = np.nan_to_num(ins, nan=np.nanmax(ins))
    pk, pr = find_peaks(-ins, distance=dist, prominence=0.01)
    order = np.argsort(-pr["prominences"])
    top = sorted(pk[order[:n_top]].tolist())
    rest = sorted(pk[order[n_top:]].tolist())
    b1 = [0] + top + [n]
    lvl1 = list(zip(b1[:-1], b1[1:]))
    lvl2 = []
    for a0, a1 in lvl1:
        inner = [p for p in rest if a0 + 3 < p < a1 - 3]
        if inner and a1 - a0 > min_split:
            c = inner[len(inner) // 2]
            lvl2 += [(a0, c), (c, a1)]
    return n, lvl1, lvl2


def level_strip(cv: Canvas, x, y_top, y_bot, w):
    """Observation level — orthogonal to the modality plates."""
    cv.box(x, y_top, w, y_bot - y_top, fc="#f6f7f9", ec="#dfe3e8", lw=LW, r=1.6, z=2)
    cx = x + w / 2
    cv.text(cx, y_top + 2.6, "level", size=F_SEC, color=CORE, weight="bold", ha="center", z=30)
    grey, fc = "#5d636b", "#e6e8ec"

    def pop(c):
        for dx, dy in ((-1.9, -0.6), (0.4, -1.3), (-0.7, 1.3), (1.8, 0.9)):
            cv.ax.add_patch(Circle((c[0] + dx, c[1] + dy), 1.15, fc=fc, ec=CORE, lw=LW_THIN, zorder=24))

    def one(c):
        cv.ax.add_patch(Circle(c, 2.3, fc=fc, ec=CORE, lw=LW_THIN * 1.3, zorder=24))
        t = np.linspace(0, 1, 20)
        for ph, col in ((0.0, OUTLINE), (1.7, CORE)):
            cv.line(c[0] - 1.3 + 2.6 * t, c[1] + 0.9 * np.sin(6 * t + ph) + (0.7 if ph else -0.7),
                    color=col, lw=0.45, z=25)

    def chain(c):
        pts = np.array([[c[0] - 3.2 + 1.6 * i, c[1] + (0.55 if i % 2 else -0.55)] for i in range(5)])
        cv.line(pts[:, 0], pts[:, 1], color=OUTLINE, lw=0.45, z=24)
        for i, p in enumerate(pts):
            cv.ax.add_patch(Circle(p, 0.62, fc=CORE if i == 2 else fc, ec=OUTLINE, lw=LW_THIN, zorder=25))

    rows = [(pop, "population", y_top + 10.0), (one, "cell", y_top + 37.0), (chain, "trace › spot", y_top + 63.5)]
    for fn, lab, yy in rows:
        fn(np.array([cx, yy]))
        cv.text(cx, yy + 4.2, lab, size=F_SEC, color=INK, ha="center", z=30)
    ax_, lx = x + 1.4, x + 4.0
    # population ↔ cell
    y0_, y1_ = rows[0][2] + 6.4, rows[1][2] - 3.2
    cv.arrow((ax_, y1_), (ax_, y0_), color=CORE, lw=0.6, head=2.4)
    cv.arrow((ax_ + 1.4, y0_), (ax_ + 1.4, y1_), color=grey, lw=0.5, head=2.4, ls=(0, (1.4, 1.0)))
    ym = (y0_ + y1_) / 2
    cv.text(lx, ym - 3.6, "aggregate", size=F_SEC, color=CORE, z=30)
    cv.text(lx, ym + 0.2, "deconvolve", size=F_SEC, color=grey, z=30)
    cv.text(lx, ym + 2.8, "(planned)", size=F_SEC, color=grey, z=30)
    # cell ↔ trace › spot
    y0_, y1_ = rows[1][2] + 6.4, rows[2][2] - 2.4
    cv.arrow((ax_, y1_), (ax_, y0_), color=CORE, lw=0.6, head=2.4)
    ym = (y0_ + y1_) / 2
    cv.text(lx, ym - 2.6, "aggregate", size=F_SEC, color=CORE, z=30)
    cv.text(lx, ym + 0.2, "assemble ·", size=F_SEC, color=grey, z=30)
    cv.text(lx, ym + 2.8, "impute", size=F_SEC, color=grey, z=30)
    cv.text(cx, y_bot - 5.4, "each layer", size=F_SEC, color=GREY, ha="center", z=30)
    cv.text(cx, y_bot - 2.8, "at every level", size=F_SEC, color=GREY, ha="center", z=30)


def dbl_arrow(cv, p0, p1, color, lw=0.8, rad=0.0):
    a = FancyArrowPatch(p0, p1, arrowstyle="<|-|>,head_length=0.35,head_width=0.21", color=color, lw=lw,
                        zorder=15, shrinkA=0, shrinkB=0, connectionstyle=f"arc3,rad={rad}", mutation_scale=10)
    cv.ax.add_patch(a)


def panel_b(cv: Canvas, cell, hic):
    x0 = 92.5
    cv.letter(x0, 1.0, "b")
    chromdata_mark(cv, x0 + 5.0, 0.0, 6.8)
    t = cv.title(x0 + 12.8, TITLE_Y, "ChromData: one shared index", color=CORE)
    cv.text(x0 + 12.8 + measure(cv, t) + 2.0, TITLE_Y + 1.55, "not a joint model", size=F_SEC, color=GREY)

    strip_w = 15.2
    level_strip(cv, x0 + 0.2, 13.5, A_BOTTOM, strip_w)

    au, av = np.radians(21.0), np.radians(23.0)          # measured from the box in a_flat_1
    L, D = 28.5, 12.5
    U = np.array([np.cos(au), np.sin(au)]) * L           # genomic bins (long axis)
    V = np.array([-np.cos(av), np.sin(av)]) * D          # depth (no level implied)
    th = 1.0
    y0 = 25.0
    foot = U[1] + V[1]
    gap = (A_BOTTOM - 4.2 - th - foot - y0) / 2
    xl = x0 + strip_w + 1.8                              # plates' leftmost vertex
    Ox = xl + np.cos(av) * D
    specs = [("geometry", "geometry", "x, y, z", "#c4561f", "#fbe3d0", "#f0c6a6"),
             ("contacts", "contacts", "bin × bin", SEQ, "#dcefec", "#b7ddd7"),
             ("features", "molecular features", "RNA · ATAC · ChIP · IF", "#6d5aa8", "#e9e4f4", "#cfc6e8")]
    O = {key: np.array([Ox, y0 + k * gap]) for k, (key, *_r) in enumerate(specs)}
    P = lambda nm, s, t: O[nm] + s * U + t * V  # noqa: E731

    def plate(nm, top, side, z):
        o = O[nm]
        down = np.array([0, th])
        cv.poly([o + U, o + U + V, o + U + V + down, o + U + down], fc=side, ec=OUTLINE, lw=LW_THIN * 1.4, z=z)
        cv.poly([o + V, o + U + V, o + U + V + down, o + V + down], fc=side, ec=OUTLINE, lw=LW_THIN * 1.4, z=z)
        cv.poly([o, o + U, o + U + V, o + V], fc=top, ec=OUTLINE, lw=LW_THIN * 1.4, z=z + 0.01)

    zs = {"geometry": 7, "contacts": 5, "features": 3}
    for key, name, sub, col, top, side in specs:
        plate(key, top, side, zs[key])
        ly = O[key][1] - {"geometry": 8.6, "contacts": 4.8, "features": 7.4}[key]
        tt = cv.text(xl, ly, name, size=F_LABEL, color=col, weight="bold", bbox=KO, z=30)
        if key == "features":                              # long label: subtitle on its own line
            cv.text(xl, ly + 2.9, sub, size=F_SEC, color=GREY, bbox=KO, z=30)
        else:
            cv.text(xl + measure(cv, tt) + 1.4, ly + 0.2, sub, size=F_SEC, color=GREY, bbox=KO, z=30)

    # geometry: an evenly spaced bead chain hovering over the plate ----------------------
    tr = cell[cell.trace_id == TRACE].sort_values("start")
    xyz = tr[["x", "y", "z"]].to_numpy()
    xyz = xyz - xyz.mean(0)
    pcs = np.linalg.svd(xyz, full_matrices=False)[2]
    smooth = lambda v: pd.Series(v).rolling(31, center=True, min_periods=1, win_type="gaussian").mean(std=10).to_numpy()  # noqa: E731
    nb = 12
    idx = np.linspace(0, len(tr) - 1, nb).astype(int)
    ii = np.arange(nb)

    def detrended01(v):
        v = v[idx]
        v = v - np.polyval(np.polyfit(ii, v, 1), ii)
        return (v - v.min()) / (np.ptp(v) + 1e-9)
    hh, dd = detrended01(smooth(xyz @ pcs[0])), detrended01(smooth(xyz @ pcs[1]))
    ss = np.linspace(0.07, 0.93, nb)
    tt_ = 0.45 + 0.10 * dd
    base = np.array([P("geometry", s_, t_) for s_, t_ in zip(ss, tt_)])
    beads = base - np.c_[np.zeros(nb), 3.6 + 2.4 * hh]
    for (bx, by), (px_, py_) in zip(beads, base):
        cv.line([bx, px_], [by, py_], color=OUTLINE, lw=LW_THIN, z=8, alpha=0.85)
        tk = V / np.linalg.norm(V) * 0.55
        cv.line([px_ - tk[0], px_ + tk[0]], [py_ - tk[1], py_ + tk[1]], color=OUTLINE, lw=LW_THIN * 1.4, z=8)
    cv.line(beads[:, 0], beads[:, 1], color=OUTLINE, lw=0.5, z=9)
    for (bx, by), c in zip(beads, CM_IMG(np.linspace(0.05, 0.95, nb))):
        cv.ax.add_patch(Circle((bx, by), 0.85, fc=c, ec=OUTLINE, lw=LW_THIN * 1.2, zorder=10))

    # contacts: HiGlass-style band of nested TAD triangles (same window as the wall in a) --
    n, lvl1, lvl2 = _tads(hic_window())
    tb, kd = 0.60, 6.0 / max(b - a for a, b in lvl1)

    def tri(a, b, fc, z):
        s0, s1 = 0.04 + 0.92 * a / n, 0.04 + 0.92 * b / n
        apex = P("contacts", (s0 + s1) / 2, tb) - np.array([0, kd * (b - a)])
        cv.poly([P("contacts", s0, tb), P("contacts", s1, tb), apex], fc=fc, ec=SEQ, lw=LW_THIN, z=z)
    for a, b in lvl1:
        tri(a, b, "#a9d8d1", 5.3)
    for a, b in lvl2:
        tri(a, b, "#5fb3a8", 5.4)
    e0, e1 = P("contacts", 0.04, tb), P("contacts", 0.96, tb)
    cv.line([e0[0], e1[0]], [e0[1], e1[1]], color=SEQ, lw=LW_THIN * 1.6, z=5.5)

    # molecular features: three rows of flat bars (real Takei IF marks) -------------------
    rows = _tracks(cell, nbins=22)
    for k, (mark, t0) in enumerate(zip(rows, (0.25, 0.55, 0.85))):
        v = rows[mark]
        nbins = len(v)
        wbar = 0.92 / nbins * 0.55
        for i, val in enumerate(v):
            sc = 0.04 + 0.92 * (i + 0.5) / nbins
            b0, b1 = P("features", sc - wbar / 2, t0), P("features", sc + wbar / 2, t0)
            hgt = 0.3 + 2.1 * val
            cv.poly([b0, b1, b1 - [0, hgt], b0 - [0, hgt]], fc=OMX, ec="none", z=3.6 + 0.001 * k)
        e0, e1 = P("features", 0.03, t0), P("features", 0.97, t0)
        cv.line([e0[0], e1[0]], [e0[1], e1[1]], color="#6d5aa8", lw=LW_THIN, z=3.7)

    # shared index ------------------------------------------------------------------------
    for sb in (0.2, 0.4, 0.6, 0.8):
        a_, b_ = P("geometry", sb, 0.5), P("features", sb, 0.5)
        cv.line([a_[0], b_[0]], [a_[1], b_[1]], color=CORE, lw=LW_THIN * 1.4, ls=(0, (1.4, 1.1)), z=11)
        for nm in O:
            cv.ax.add_patch(Circle(P(nm, sb, 0.5), 0.5, fc=CORE, ec="white", lw=0.3, zorder=11.5))
    e0, e1 = P("features", 0, 1) + [0, th], P("features", 1, 1) + [0, th]
    mid = (e0 + e1) / 2 + np.array([1.0, 2.7])
    cv.text(mid[0], mid[1], "genomic bins (shared index) →", size=F_SEC, color=INK, ha="center",
            rotation=-np.degrees(au), rotation_mode="anchor")

    # bridges (right) ----------------------------------------------------------------------
    rg, rc, rf = P("geometry", 1, 0), P("contacts", 1, 0), P("features", 1, 0)
    xa = rg[0] + 1.4
    cv.arrow((xa, rc[1] - 0.6), (xa, rg[1] + 1.6), color=SEQ, lw=0.8, rad=-0.22)
    cv.arrow((xa + 2.6, rg[1] + 2.6), (xa + 2.6, rc[1] - 1.6), color=IMG, lw=0.8, rad=-0.16)
    tx, ym = xa + 5.2, (rg[1] + rc[1]) / 2
    cv.text(tx, ym - 4.6, "↑ recon", size=F_LABEL, color=SEQ, weight="bold")
    cv.text(tx, ym - 1.8, "contacts→3-D", size=F_SEC, color=GREY)
    cv.text(tx, ym + 1.8, "↓ distance", size=F_LABEL, color="#c4561f", weight="bold")
    cv.text(tx, ym + 4.6, "   → contact", size=F_LABEL, color="#c4561f", weight="bold")
    dbl_arrow(cv, (xa + 1.2, rc[1] + 3.2), (xa + 1.2, rf[1] - 1.0), OMX, rad=-0.2)
    ym = (rc[1] + rf[1]) / 2 + 1.4
    cv.text(tx, ym - 4.2, "associate ·", size=F_LABEL, color="#6d5aa8", weight="bold")
    cv.text(tx, ym - 1.5, "project", size=F_LABEL, color="#6d5aa8", weight="bold")
    for k, s_ in enumerate(("via same spot ·", "same cell ·", "same cell type")):
        cv.text(tx, ym + 1.4 + 2.5 * k, s_, size=F_SEC, color=GREY)


# --------------------------------------------------------------------------- panel c

LOGO_H = 4.8


def _bead(cv, p, r, fc, z=24):
    cv.ax.add_patch(Circle(p, r, fc=fc, ec=OUTLINE, lw=LW_THIN, zorder=z))


def mod_icon(cv, kind, x, y, s):
    """Flat vector icon for a Methods module in an s × s mm box at (x, y) (top-left)."""
    X = lambda u, v: np.array([x + u * s, y + v * s])  # noqa: E731  (u, v in 0..1, v down)
    if kind == "recon":        # contact triangle → curved arrow → bead chain
        cv.poly([X(0.02, 0.92), X(0.46, 0.92), X(0.24, 0.52)], fc="#bfe3dd", ec=SEQ, lw=LW_THIN, z=23)
        cv.poly([X(0.13, 0.92), X(0.35, 0.92), X(0.24, 0.72)], fc="#3fa697", ec="none", z=23.1)
        cv.arrow(X(0.28, 0.52), X(0.60, 0.24), color=OUTLINE, lw=0.6, rad=-0.45, head=3.0, z=24)
        pts = [X(0.66, 0.62), X(0.80, 0.50), X(0.70, 0.34), X(0.86, 0.20)]
        cv.line([p[0] for p in pts], [p[1] for p in pts], color=OUTLINE, lw=0.45, z=23.5)
        for p, c in zip(pts, CM_IMG(np.linspace(0.2, 0.9, 4))):
            _bead(cv, p, s * 0.075, c)
    elif kind == "im":         # field of view with fluorescent dots joined into a trace
        cv.box(x + s * 0.04, y + s * 0.06, s * 0.88, s * 0.88, fc="#fbe3d0", ec=OUTLINE, lw=LW_THIN, r=0.5, z=23)
        pts = [X(0.20, 0.72), X(0.36, 0.44), X(0.56, 0.62), X(0.66, 0.30), X(0.82, 0.48)]
        cv.line([p[0] for p in pts], [p[1] for p in pts], color="#c4561f", lw=0.45, z=23.5)
        for p in pts:
            cv.ax.add_patch(Circle(p, s * 0.11, color="#ff6a2b", alpha=0.18, lw=0, zorder=23.6))
            cv.ax.add_patch(Circle(p, s * 0.055, fc="#e8501a", ec="white", lw=0.3, zorder=23.8))
    elif kind == "strc":       # nested TAD triangles on a baseline + a loop arc
        cv.poly([X(0.02, 0.90), X(0.64, 0.90), X(0.33, 0.40)], fc="#dbe3f0", ec=CORE, lw=LW_THIN, z=23)
        cv.poly([X(0.06, 0.90), X(0.30, 0.90), X(0.18, 0.70)], fc="#8ea6cf", ec=CORE, lw=LW_THIN, z=23.1)
        cv.poly([X(0.64, 0.90), X(0.98, 0.90), X(0.81, 0.62)], fc="#dbe3f0", ec=CORE, lw=LW_THIN, z=23)
        cv.line([x, x + s], [y + 0.90 * s] * 2, color=OUTLINE, lw=0.45, z=23.2)
        t = np.linspace(0, np.pi, 30)
        c0, r0 = X(0.52, 0.30), 0.30 * s
        cv.line(c0[0] + r0 * np.cos(t), c0[1] - 0.55 * r0 * np.sin(t), color=CORE, lw=0.5, z=23.4)
        for u in (0.22, 0.82):
            cv.ax.add_patch(Circle(X(u, 0.30), s * 0.045, fc=CORE, ec="none", zorder=23.5))
    elif kind == "fea":        # bead chain with a dimension line between two beads
        pts = [X(0.08, 0.78), X(0.30, 0.62), X(0.52, 0.76), X(0.74, 0.58), X(0.93, 0.70)]
        cv.line([p[0] for p in pts], [p[1] for p in pts], color=OUTLINE, lw=0.45, z=23.2)
        for p in pts:
            _bead(cv, p, s * 0.075, "#c9cdd3")
        a_, b_ = pts[1] - [0, 0.34 * s], pts[3] - [0, 0.18 * s]
        cv.arrow(tuple((a_ + b_) / 2), tuple(a_), color="#5d636b", lw=0.45, head=1.6, z=23.4)
        cv.arrow(tuple((a_ + b_) / 2), tuple(b_), color="#5d636b", lw=0.45, head=1.6, z=23.4)
        for p, q in ((pts[1], a_), (pts[3], b_)):
            cv.line([p[0], q[0]], [p[1] - 0.08 * s, q[1]], color="#5d636b", lw=LW_THIN, z=23.3, ls=(0, (1, 0.8)))
    elif kind == "emb":        # 2–3 clusters of dots
        rng = np.random.default_rng(3)
        for (cu, cv_), col in (((0.28, 0.35), "#6d5aa8"), ((0.72, 0.40), "#a898d6"), ((0.45, 0.78), "#8e7cc3")):
            for _ in range(6):
                p = X(cu + rng.normal(0, 0.07), cv_ + rng.normal(0, 0.06))
                cv.ax.add_patch(Circle(p, s * 0.05, fc=col, ec="none", zorder=23.5))


def tag(cv, x, y, s, ec, fc, h=4.4, pad=1.3, dashed=False, z=21):
    t = cv.text(x + pad, y + h / 2 + 0.05, s, size=F_TAG, color=INK, z=z + 1)
    w = measure(cv, t) + 2 * pad
    cv.box(x, y, w, h, fc=fc, ec=ec, lw=LW, r=1.1, z=z, ls=(0, (1.5, 1.0)) if dashed else "-")
    return x + w


def group(cv, x, y, label, color, tags, lg=None, lg_h=LOGO_H, plate=False):
    """[logo] label over tags.  A tag is str, (str,) for 'linked', or (str, icon_key)."""
    blk = 7.0                                           # label row + tag row
    if lg:
        lw_, _ = logo(cv, lg, x, y + (blk - lg_h) / 2, lg_h, z=22, plate=LIGHTGREY if plate else None)
        x += lw_ + 1.8
    x_lab_end = x
    if label:
        t = cv.text(x + 0.2, y + 1.0, label, size=F_SEC, color=color, weight="bold")
        x_lab_end = x + 0.2 + measure(cv, t)
    ty = y + 2.6
    for t in tags:
        dashed, icon = False, None
        if isinstance(t, tuple):
            name, icon = t[0], (t[1] if len(t) > 1 else None)
            dashed = len(t) == 1 or (len(t) > 2 and t[2] == "linked")
        else:
            name = t
        if icon:
            ih = {"cooler": 3.0}.get(icon, 4.0)
            iw, _ = logo(cv, icon, x, ty + (4.4 - ih) / 2, ih, z=22)
            x += iw + 0.9
        x = tag(cv, x, ty, name, ec=color, fc=PALE.get(color, "#f4f5f7"), dashed=dashed) + 1.1
    return max(x, x_lab_end + 1.0) + 3.0


def panel_c(cv: Canvas, y0: float):
    cv.letter(0.5, y0 - 0.5, "c")
    t = cv.title(6, y0, "An open ecosystem")
    cv.text(6 + measure(cv, t) + 3, y0 + 1.6, "interoperates with 4DN · scverse · Open2C · Juicer",
            size=F_SEC, color=GREY)
    x_l, x_r = 1.5, W - 1.0
    lab_w = 21.5
    xs0 = x_l + lab_w
    y = y0 + 6.5
    BAND = "#dfe3e8"

    def band(y, h, title, sub=None):
        cv.box(x_l, y, x_r - x_l, h, fc="white", ec=BAND, lw=LW, r=1.8, z=2)
        cv.text(x_l + 2.2, y + h / 2 - (1.7 if sub else 0), title, size=F_LABEL, weight="bold")
        if sub:
            cv.text(x_l + 2.2, y + h / 2 + 1.9, sub, size=F_SEC, color=GREY)

    # interfaces
    h1 = 10.5
    band(y, h1, "Interfaces", sub="people · agents")
    yc = y + h1 / 2
    x = xs0
    lw_, _ = logo(cv, "python", x, yc - 2.6, 5.2, z=22)
    cv.text(x + lw_ + 1.5, yc, "API", size=F_LABEL)
    x = xs0 + 42
    icon_terminal(cv, x, yc - 2.6, 5.2, CORE)
    cv.text(x + 6.6, yc, "CLI", size=F_LABEL)
    x = xs0 + 68
    icon_browser(cv, x, yc - 2.6, 5.2, CORE)
    cv.text(x + 6.6, yc, "web browser", size=F_LABEL)
    x = xs0 + 106
    lw_, _ = logo(cv, "mcp_icon", x, yc - 2.5, 5.0, z=22)
    cv.text(x + lw_ + 1.8, yc, "MCP server + agent skills", size=F_LABEL)
    y += h1 + 1.8

    # methods
    h2 = 18.4
    band(y, h2, "Methods", sub="one API")
    mods = [("recon", SEQ, "3-D structures from contacts\nsingle-cell and bulk"),
            ("im", IMG, "spots → traces\nfill in missing loci"),
            ("strc", CORE, "TADs, loops,\ncompartments"),
            ("fea", GREY, "per-locus geometric\nfeatures"),
            ("emb", OMX, "cell embeddings\nacross modalities")]
    wds = [31.5, 26.5, 26.0, 26.5, 27.5]
    gapm = (x_r - 2 - xs0 - sum(wds)) / 4
    xm = xs0
    ic_s = 7.0
    for (name, c, txt), wd in zip(mods, wds):
        cv.box(xm, y + 1.5, wd, h2 - 3.0, fc=PALE.get(c, "#f4f5f7"), ec=c, lw=LW, r=1.3, z=3)
        mod_icon(cv, name, xm + 1.4, y + 2.6, ic_s)
        cv.text(xm + 1.4 + ic_s + 1.3, y + 2.6 + ic_s / 2, "uchrom." + name, size=F_LABEL,
                color=c if c != GREY else "#5d636b", weight="bold")
        cv.text(xm + 1.6, y + 2.6 + ic_s + 1.6, txt, size=F_SEC, color=INK, va="top", linespacing=1.25)
        xm += wd + gapm
    y += h2 + 1.8

    # core
    h3 = 8.0
    cv.box(x_l, y, x_r - x_l, h3, fc=CORE, ec=CORE, lw=LW, r=1.8, z=2)
    chromdata_mark(cv, x_l + 3.0, y + 0.5, 6.2)
    cv.text(x_l + 11.5, y + h3 / 2, "ChromData", size=F_TITLE, color="white", weight="bold", z=25)
    cv.text(xs0 + 9.0, y + h3 / 2,
            "cell › trace › spot   ·   geometry · contacts · features   ·   .h5cd, versioned spec",
            size=F_LABEL, color="white", z=25)
    core_y = y
    y += h3 + 1.8

    # formats
    h4 = H - 0.8 - y
    band(y, h4, "Formats", sub="& standards")
    split = x_l + 97.0
    cv.line([split, split], [y + 1.8, y + h4 - 1.8], color=BAND, lw=LW, z=3)
    cv.text(xs0, y + 3.0, "read  ↑", size=F_SEC, color=GREY, weight="bold")
    cv.text(split + 2.4, y + 3.0, "write / link  ↓", size=F_SEC, color=GREY, weight="bold")
    xl = x_r - 29.0
    cv.box(xl, y + 1.5, 4.4, 3.0, fc="white", ec=SEQ, lw=LW, ls=(0, (1.5, 1.0)), r=0.6, z=4)
    cv.text(xl + 5.4, y + 3.0, "linked, not copied", size=F_SEC, color=GREY)
    cv.arrow((x_l + 60, y - 0.1), (x_l + 60, core_y + h3 + 0.1), color=CORE, lw=0.7, head=2.6)
    cv.arrow((split + 34, core_y + h3 + 0.1), (split + 34, y - 0.1), color=CORE, lw=0.7, head=2.6)
    pitch = 9.4
    r1 = y + 5.6
    r2, r3 = r1 + pitch, r1 + 2 * pitch
    x = group(cv, xs0, r1, None, IMG, ["FOF-CT"], lg="4dn")
    col2 = split - 25.0                                   # second column of the read half
    group(cv, col2, r1, "Juicer", SEQ, [".hic"])
    group(cv, xs0, r2, "Open2C", SEQ, [".pairs", (".cool · .mcool · .scool", "cooler")], lg="open2c")
    x = group(cv, xs0, r3, "tracing tools", IMG, ["pyHiM", "seqFISH+", "Bintu et al."], lg="pyhim",
              lg_h=LOGO_H - 0.6, plate=True)
    group(cv, max(x, col2), r3, "structures", "#5d636b", [".3dg"])
    xw = split + 2.4
    x = group(cv, xw, r1, "U-Chrom (HDF5)", CORE, [".h5cd"], lg="hdf5", lg_h=3.8)
    group(cv, x + 2.0, r1, "structures (export)", "#5d636b", ["PDB → PyMOL / ChimeraX"])
    group(cv, xw, r2, None, OMX, [("AnnData", "anndata", "linked"), ("MuData", "mudata", "linked")],
          lg="scverse", lg_h=3.8)
    group(cv, xw, r3, "Open2C", SEQ, [(".mcool",), (".scool",)])



# --------------------------------------------------------------------------- checks + main

def check_text(fig):
    """Every visible text: Arial and >= 6 pt (journal legibility; our own floor)."""
    from matplotlib.text import Text
    rows = []
    for t in fig.findobj(Text):
        if not t.get_visible() or not t.get_text().strip() or t.get_alpha() == 0:
            continue
        rows.append((t.get_fontsize(), t.get_fontname(), t.get_text()[:40]))
    sizes = sorted({r[0] for r in rows})
    fams = sorted({r[1] for r in rows})
    print(f"{len(rows)} text objects; sizes (pt) {sizes}; families {fams}")
    bad = [r for r in rows if r[0] < 6 or r[1] != "Arial"]
    assert not bad, bad
    return rows


def main():
    cell = pd.read_csv(CACHE / "cell_1_0_34.csv")
    hic = np.load(CACHE / "schicar_chr2.npy").astype(float)
    fig = plt.figure(figsize=(W * MM, H * MM))
    cv = Canvas(fig)
    cv.ax.set_zorder(10)
    cv.ax.patch.set_visible(False)
    panel_a(cv, cell)
    panel_b(cv, cell, hic)
    panel_c(cv, A_BOTTOM + 5.5)
    cv.fix()
    check_text(fig)
    out = HERE / "fig1_final.pdf"
    fig.savefig(out, dpi=600)
    fig.savefig(out.with_suffix(".png"), dpi=300)
    print(out)


if __name__ == "__main__":
    main()
