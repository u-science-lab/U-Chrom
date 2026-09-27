"""Figure 6 — analysis in code, visualization in the browser, for researchers and agents (draft).

Real data where it exists: b and the views in d draw Takei 2025 FOV 0 (``extract_data.py`` ->
``_cache/takei_fov0.npz``); c reads the browser benchmarks (``benchmarks/fig6`` -> ``results/*.json``); e reads
the agent benchmark (``benchmarks/fig6/agent_bench/summarize.py`` -> ``results/agent_bench.json``).  Anything
that is not yet a real result sits in a red dashed **placeholder** frame, with the reason.

  a  analysis = uchrom Python API (notebooks; coding agents + skills); visualization = browser (GUI; WebMCP)
  b  linked exploration in the browser (annotated screenshot, Takei 2025)
  c  browser performance: time to first frame, interaction latency
  d  handoff: coding agent reads the lasso, analyses in uchrom, opens views in the browser
  e  skills: anatomy of a skill; agent benchmark score with API docs only vs + skills

    python paper/fig6/make_fig6.py          # -> fig6.pdf / fig6.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PolyCollection
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle

HERE = Path(__file__).resolve().parent
MM = 1 / 25.4
W, H = 170.0, 201.0

mpl.rcParams.update({
    "pdf.fonttype": 42, "font.family": "sans-serif", "font.sans-serif": ["Arial"],
    "font.size": 7, "axes.titlesize": 7, "axes.labelsize": 6.5,
    "xtick.labelsize": 6, "ytick.labelsize": 6, "legend.fontsize": 6,
    "axes.linewidth": 0.5, "xtick.major.width": 0.5, "ytick.major.width": 0.5,
    "xtick.major.size": 2, "ytick.major.size": 2, "xtick.minor.size": 1, "ytick.minor.size": 1,
    "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 1.0,
})

MIN_PT = 5.0


def F(size):
    """Print font size: draft sizes scaled up, never below MIN_PT (Genome Biology legibility)."""
    return max(MIN_PT, round(size * 1.15, 2))


ORANGE, TEAL, PURPLE, INDIGO = "#e07a3f", "#2a9d8f", "#8e7cc3", "#34568b"
GREY, LGREY, INK, PANEL = "#8a8f98", "#c9ccd1", "#2b2f36", "#f4f5f7"
# muted cell-type palette (Okabe-Ito, desaturated)
CT = {"Granule": "#5b8db8", "Bergmann": "#6aa77f", "Purkinje": "#c9745a", "other": "#b9bdc4"}
RNG = np.random.default_rng(7)


# --------------------------------------------------------------------------- data

def mock_data() -> dict:
    """PLACEHOLDER numbers — shapes only, not results."""
    n = np.logspace(4, 8, 5)
    d = {"n_spots": n}
    d["first_frame"] = {"per-layer streaming": 0.25 + n * 1.5e-8,
                        "load whole file": 0.4 + n * 2.5e-7}
    d["latency_ms"] = [  # interaction, median, p95  (to be measured)
        ("focus a cell", 18, 35), ("lasso → re-scope views", 60, 110),
        ("pan locus (tracks)", 40, 80), ("distance map, group", 120, 260),
        ("contact map, 1k bins", 70, 150), ("pseudo-bulk, 500 cells", 300, 600)]
    t = np.logspace(2, 5, 7)
    d["fps"] = {"lines": np.clip(60 * (2e5 / (t + 2e5)) ** 0.3 + 0 * t, 0, 60),
                "tubes": np.clip(60 * (3e3 / (t + 3e3)), 2, 60)}
    d["traces"] = t
    d["rg"] = {k: RNG.lognormal(np.log(m), 0.25, s)
               for k, m, s in [("Granule", 1.16, 400), ("Bergmann", 1.47, 160), ("Purkinje", 1.86, 60)]}
    x = RNG.lognormal(2, 1.2, 1500)
    d["pb"] = (x, x)
    return d


def load_results() -> dict:
    """Real benchmark results (benchmarks/fig6 -> results/*.json); missing files -> {}."""
    out = {}
    for k in ("frontend", "server", "agent_bench"):
        f = HERE / "results" / f"{k}.json"
        if f.exists():
            import json
            out[k] = json.loads(f.read_text())
    return out


# --------------------------------------------------------------------------- canvas helpers

# Layout coordinates are mm on a W x H canvas; they are mapped into the page with a MARGIN on every side
# (geometry is scaled by SCALE, font sizes are not).
MARGIN = 1.5
SCALE = (W - 2 * MARGIN) / W
PW, PH = W, H * SCALE + 2 * MARGIN                # physical page size (mm)
fig = plt.figure(figsize=(PW * MM, PH * MM))
A = fig.add_axes([0, 0, 1, 1])
A.set_xlim(-MARGIN / SCALE, PW / SCALE - MARGIN / SCALE)
A.set_ylim(PH / SCALE - MARGIN / SCALE, -MARGIN / SCALE)
A.axis("off")


def _rect(x, y, w, h):
    """Layout mm rect -> figure fraction rect."""
    px, py = MARGIN + x * SCALE, MARGIN + y * SCALE
    return [px / PW, 1 - (py + h * SCALE) / PH, w * SCALE / PW, h * SCALE / PH]


def ax_mm(x, y, w, h, **kw):
    return fig.add_axes(_rect(x, y, w, h), **kw)


def text(x, y, s, size=6, color=INK, **kw):
    return A.text(x, y, s, fontsize=F(size), color=color, **kw)


def panel(x, y, letter, title, sub=None):
    text(x, y, letter, 8, weight="bold", va="top")
    text(x + 4, y + 0.1, title, 7, weight="bold", va="top")
    if sub:
        text(x + 4, y + 3.4, sub, 5.5, GREY, va="top")


def box(x, y, w, h, fc="white", ec=LGREY, lw=0.5, r=0.8, ls="-", z=1):
    A.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                               fc=fc, ec=ec, lw=lw, ls=ls, zorder=z))


def arrow(x0, y0, x1, y1, color=GREY, lw=0.6, style="-|>", ls="-", rad=0.0, z=3, shrink=None):
    kw = {} if shrink is None else dict(shrinkA=shrink[0], shrinkB=shrink[1])
    A.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle=style, mutation_scale=5, color=color,
                                lw=lw, ls=ls, connectionstyle=f"arc3,rad={rad}", zorder=z, **kw))


def pane(x, y, w, h, title, active=False):
    """A browser pane: header strip + content area; returns the content box."""
    box(x, y, w, h, ec=INDIGO if active else LGREY, lw=0.7 if active else 0.4, r=0.5, z=2)
    A.add_patch(Rectangle((x + 0.2, y + 0.2), w - 0.4, 2.6, fc=PANEL, ec="none", zorder=2))
    text(x + 1, y + 1.6, title, 4.5, GREY, va="center", zorder=3)
    return x + 1, y + 3.4, w - 2, h - 4.2


# --------------------------------------------------------------------------- glyphs (wireframe content)

def glyph_nuclei(x, y, w, h, focus="Purkinje", n=9):
    cells = [("Granule", 0.9)] * 5 + [("Bergmann", 1.1)] * 2 + [("Purkinje", 1.5)] * 2
    pts = RNG.uniform([x + 3, y + 3], [x + w - 3, y + h - 3], (n, 2))
    s = min(w, h) / 9
    for (ct, r), (cx, cy) in zip(cells, pts):
        on = ct == focus or focus is None
        A.add_patch(Circle((cx, cy), r * s, fc=CT[ct] if on else "#eceef1", ec="none",
                           alpha=0.25 if on else 1, zorder=3))
        for _ in range(3 if on else 2):
            walk = np.cumsum(RNG.normal(0, 0.18 * r * s, (12, 2)), 0) + (cx, cy)
            A.plot(walk[:, 0], walk[:, 1], lw=0.5 if on else 0.3, color=CT[ct] if on else LGREY, zorder=4)


def glyph_umap(x, y, w, h, lasso="Purkinje", pt=0.6):
    centers = {"Granule": (0.3, 0.35), "Bergmann": (0.72, 0.3), "Purkinje": (0.62, 0.75), "other": (0.25, 0.75)}
    for ct, (u, v) in centers.items():
        p = RNG.normal((x + u * w, y + v * h), (w * 0.07, h * 0.08), (60, 2))
        A.scatter(p[:, 0], p[:, 1], s=pt, color=CT[ct], lw=0, zorder=4)
    if lasso:
        u, v = centers[lasso]
        t = np.linspace(0, 2 * np.pi, 40)
        rr = 1 + 0.12 * np.sin(3 * t)
        A.add_patch(Polygon(np.c_[x + u * w + 0.19 * w * rr * np.cos(t), y + v * h + 0.2 * h * rr * np.sin(t)],
                            fc="none", ec=INK, lw=0.5, ls=(0, (2, 1)), zorder=5))


def glyph_triangle(x, base, w, n=20, cmap="viridis_r", kind="distance", flip=False):
    """HiGlass-style rotated upper triangle; base = y of the diagonal (grows upward)."""
    s = w / n
    i, j = np.triu_indices(n, 1)
    sep = (j - i).astype(float)
    if kind == "distance":
        v = np.sqrt(sep) + RNG.normal(0, 0.3, sep.size)
    else:
        v = -np.log(sep) + 1.5 * ((i // 5) == (j // 5)) + RNG.normal(0, 0.3, sep.size)
    sign = 1 if flip else -1
    polys = []
    for a, b in zip(i, j):
        cx, cy = x + (a + b + 1) / 2 * s, base + sign * (b - a) * s / 2
        polys.append([(cx - s / 2, cy), (cx, cy - s / 2), (cx + s / 2, cy), (cx, cy + s / 2)])
    pc = PolyCollection(polys, array=v, cmap=cmap, edgecolors="none", zorder=4)
    A.add_collection(pc)
    return w / 2


def glyph_track(x, y, w, h, color, n=40):
    v = np.abs(RNG.normal(0, 1, n)).cumsum() % 3 + RNG.uniform(0, 1, n)
    v = v / v.max() * h
    A.bar(x + (np.arange(n) + 0.5) * w / n, -v, bottom=y + h, width=w / n * 0.9, color=color, lw=0, zorder=4)


def glyph_hist(x, y, w, h):
    for ct, mu, k in [("Granule", 0.3, 1.0), ("Bergmann", 0.5, 0.6), ("Purkinje", 0.7, 0.4)]:
        xs = np.linspace(0, 1, 30)
        ys = k * np.exp(-((xs - mu) ** 2) / 0.01)
        A.plot(x + xs * w, y + h - ys * h * 0.9, color=CT[ct], lw=0.7, zorder=4)
    A.plot([x, x + w], [y + h, y + h], color=GREY, lw=0.4, zorder=4)


def callout(x, y, k):
    A.add_patch(Circle((x, y), 1.5, fc=INK, ec="white", lw=0.4, zorder=8))
    text(x, y + 0.05, str(k), 4.8, "white", ha="center", va="center", weight="bold", zorder=9)


MONO = "Menlo"


# --------------------------------------------------------------------------- images

FIG1 = HERE.parent / "fig1"
LOGO = {k: HERE / "_cache/logos" / f"{k}.png" for k in ["claudecode", "codex", "jupyter", "pantheon"]}
LOGO.update({k: FIG1 / "_cache/logos" / f"{k}.png" for k in ["python", "hdf5", "cooler", "mudata"]})
LOGO.update({"uchrom": FIG1 / "logos/uchrom_logo.png", "uchrom_mark": FIG1 / "logos/uchrom_mark.png"})


def place_png(path, x, y, w=None, h=None, z=6):
    """Place a PNG (aspect kept) with its top-left at (x, y) mm; give w or h. Returns (w, h)."""
    from PIL import Image
    im = Image.open(path).convert("RGBA")
    iw, ih = im.size
    w = h * iw / ih if w is None else w
    h = w * ih / iw if h is None else h
    px = max(2, int(round(w * MM * 600)))            # pre-scale to 600 dpi at print size
    im = im.resize((px, max(2, int(round(px * ih / iw)))), Image.LANCZOS)
    ax = fig.add_axes(_rect(x, y, w, h))
    ax.imshow(np.asarray(im), interpolation="antialiased")
    ax.axis("off"), ax.set_zorder(z)
    return w, h


def shadow_box(x, y, w, h, fc="white", ec=LGREY, lw=0.5, r=1.2, z=1):
    A.add_patch(FancyBboxPatch((x + 0.5, y + 0.6), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                               fc="#000000", ec="none", alpha=0.06, zorder=z - 0.1))
    box(x, y, w, h, fc=fc, ec=ec, lw=lw, r=r, z=z)


def person_icon(x, y, s, col):
    """A simple researcher glyph centred at x, top at y, height s."""
    A.add_patch(Circle((x, y + s * 0.22), s * 0.2, fc=col, ec="none", zorder=5))
    A.add_patch(FancyBboxPatch((x - s * 0.34, y + s * 0.5), s * 0.68, s * 0.46,
                               boxstyle=f"round,pad=0,rounding_size={s * 0.22}", fc=col, ec="none", zorder=5))


def elbow(pts, color, lw=0.7, ls="-", z=2):
    xs, ys = zip(*pts)
    A.plot(xs[:-1], ys[:-1], color=color, lw=lw, ls=ls, zorder=z, solid_capstyle="round")
    arrow(xs[-2], ys[-2], xs[-1], ys[-1], color=color, lw=lw, ls=ls, z=z + 1)


def tag(x, y, s, col, fc="white"):
    t = A.text(x, y, s, fontsize=F(4.4), color=col, ha="center", va="center", zorder=8,
               bbox=dict(boxstyle="round,pad=0.25,rounding_size=0.6", fc=fc, ec=col, lw=0.4))
    return t


# --------------------------------------------------------------------------- a  architecture

def panel_a(x0=0, y0=2):
    panel(x0, y0, "a", "Analysis in code, visualization in the browser — for researchers and agents")
    ty = y0 + 12.5                    # top of the boxes
    bh = 32                           # box height
    RES, AGT = INDIGO, ORANGE
    # ---------------------------------------------------------------- users (left)
    ux, uw = x0 + 1, 37
    shadow_box(ux, ty, uw, 9, fc="#f5f7fb", ec="#c9d3e6")
    person_icon(ux + 6, ty + 1.2, 6.8, RES)
    text(ux + 12, ty + 3.3, "researcher", 6, RES, va="center", weight="bold")
    text(ux + 12, ty + 6.4, "notebooks · GUI", 4.6, GREY, va="center")
    ay = ty + 14
    shadow_box(ux, ay, uw, bh - 14, fc="#fdf6f1", ec="#efcfb8")
    # researcher <-> agents: a conversation, drawn as two message arrows
    xa, xb = ux + 8, ux + 21
    arrow(xa, ty + 9.3, xa, ay - 0.3, color=RES, lw=0.7)
    arrow(xb, ay - 0.3, xb, ty + 9.3, color=AGT, lw=0.7)
    text(xa + 1.0, ty + 11.6, "asks", 4.4, RES, va="center")
    text(xb + 1.0, ty + 11.6, "answers · views", 4.4, AGT, va="center")
    text(ux + 1.8, ay + 2.4, "agents", 6, AGT, va="center", weight="bold")
    A.text(ux + uw - 1.8, ay + 2.4, "+ any coding agent", fontsize=F(4.3), color=AGT, ha="right", va="center",
           zorder=5, bbox=dict(boxstyle="round,pad=0.3,rounding_size=0.7", fc="white", ec=AGT, lw=0.4))
    for k, (key, lab) in enumerate([("claudecode", "Claude Code"), ("codex", "Codex"), ("pantheon", "Pantheon")]):
        cx = ux + uw * (1 + 2 * k) / 6
        if key == "codex":
            place_png(LOGO[key], cx - 2.6, ay + 4.6, h=5.2)
        else:
            place_png(LOGO[key], cx - 3.0, ay + 5.4 if key == "claudecode" else ay + 5.1, w=6.0)
        text(cx, ay + 11.4, lab, 4.3, INK, ha="center", va="center")
    box(ux + 1.8, ay + 13.6, uw - 3.6, 3.6, fc="white", ec=AGT, lw=0.5, r=0.8, z=3)
    text(ux + 3.2, ay + 15.4, "skills", 5, AGT, va="center", weight="bold", zorder=4)
    text(ux + uw - 3, ay + 15.4, "recipes · checks · reports", 4.3, GREY, ha="right", va="center", zorder=4)

    # ---------------------------------------------------------------- analysis (middle)
    mx, mw = x0 + 48, 54
    shadow_box(mx, ty, mw, bh, fc=PANEL, ec=LGREY)
    place_png(LOGO["uchrom"], mx + 1.8, ty + 1.0, h=4.4)
    text(mx + mw - 1.8, ty + 3.1, "analysis", 5, GREY, ha="right", va="center")
    box(mx + 1.8, ty + 6.4, mw - 3.6, 10.5, fc="white", ec=INK, lw=0.6, r=0.8, z=3)
    text(mx + 3.2, ty + 8.9, "Python API", 5.6, INK, va="center", weight="bold", zorder=4)
    place_png(LOGO["python"], mx + mw - 30, ty + 7.4, h=3.2)
    place_png(LOGO["jupyter"], mx + mw - 14.2, ty + 7.0, h=4.0)
    text(mx + mw - 10.8, ty + 9.0, "Jupyter", 5.4, "#4e4e4e", va="center")
    mods = ["recon", "im", "strc", "fea", "emb", "pl"]
    pw_ = (mw - 3.6 - 2.4 - 5 * 1.0) / 6
    for k, m in enumerate(mods):
        bx = mx + 3 + k * (pw_ + 1.0)
        box(bx, ty + 12.2, pw_, 3.2, fc="#e9eef6", ec="none", r=0.6, z=4)
        A.text(bx + pw_ / 2, ty + 13.8, m, fontsize=F(4.5), family=MONO, color=INDIGO, ha="center", va="center",
               zorder=5)
    # data strip
    text(mx + 1.8, ty + 19.4, "data", 4.6, GREY, va="center")
    items = [("hdf5", "data.h5cd", INDIGO, "-"), ("cooler", ".cool · .scool", TEAL, (0, (2, 1))),
             ("mudata", ".h5mu", TEAL, (0, (2, 1)))]
    for k, (key, lab, col, ls) in enumerate(items):
        bx = mx + 1.8 + k * 17
        box(bx, ty + 21, 16, 9.2, fc="white", ec=col, lw=0.5, r=0.8, ls=ls, z=3)
        lh = {"hdf5": 3.8, "cooler": 3.0, "mudata": 3.8}[key]
        from PIL import Image as _I
        iw, ih = _I.open(LOGO[key]).size
        place_png(LOGO[key], bx + 8 - lh * iw / ih / 2, ty + 22.0 + (3.8 - lh) / 2, h=lh)
        text(bx + 8, ty + 27.8, lab, 4.5, col, ha="center", va="center", zorder=4)
    text(mx + mw - 1.8, ty + 19.4, "dashed: linked, not copied", 4.2, GREY, ha="right", va="center")

    # ---------------------------------------------------------------- visualization (right): a browser window
    wx, ww = x0 + 112, 57
    shadow_box(wx, ty, ww, bh, fc="white", ec="#9fb0cc", lw=0.7)
    A.add_patch(FancyBboxPatch((wx, ty), ww, 4.6, boxstyle="round,pad=0,rounding_size=1.2", fc="#e9eef6",
                               ec="none", zorder=2))
    A.add_patch(Rectangle((wx, ty + 3), ww, 1.6, fc="#e9eef6", ec="none", zorder=2))
    for k, c in enumerate(["#ec6a5e", "#f4bf4f", "#61c554"]):
        A.add_patch(Circle((wx + 2.2 + k * 2, ty + 2.3), 0.62, fc=c, ec="none", zorder=3))
    box(wx + 9, ty + 1.1, ww - 32, 2.5, fc="white", ec="none", r=1.2, z=3)
    text(wx + 10.2, ty + 2.35, "localhost:8765", 4.2, GREY, va="center", zorder=4)
    text(wx + ww - 1.8, ty + 2.35, "visualization", 5, INDIGO, ha="right", va="center", zorder=4,
         weight="bold")
    # GUI row with a thumbnail
    gy = ty + 6.2
    box(wx + 1.8, gy, ww - 3.6, 10.8, fc="white", ec=INDIGO, lw=0.6, r=0.8, z=3)
    text(wx + 3.2, gy + 2.5, "GUI", 5.6, INDIGO, va="center", weight="bold", zorder=4)
    text(wx + 3.2, gy + 5.6, "linked views\n3D · Embedding · Genome", 4.3, GREY, va="top", zorder=4, linespacing=1.15)
    tx = wx + ww - 25
    for k in range(3):
        box(tx + k * 7.6, gy + 1.2, 7, 8.4, fc="#f7f8fa", ec=LGREY, lw=0.3, r=0.4, z=4)
    rng = np.random.default_rng(3)
    for cxy, col in [((0.35, 0.4), CT["Granule"]), ((0.65, 0.65), CT["Purkinje"]), ((0.3, 0.72), CT["Bergmann"])]:
        p = rng.normal(cxy, 0.09, (18, 2))
        A.scatter(tx + 0.5 + p[:, 0] * 6, gy + 1.8 + p[:, 1] * 7.2, s=0.35, color=col, lw=0, zorder=5)
    walk = np.cumsum(rng.normal(0, 0.5, (24, 2)), 0)
    walk = (walk - walk.min(0)) / np.ptp(walk, 0)
    A.plot(tx + 7.6 + 0.8 + walk[:, 0] * 5.4, gy + 2 + walk[:, 1] * 6.6, lw=0.5, color=CT["Purkinje"], zorder=5)
    glyph_track(tx + 15.6, gy + 1.8, 5.8, 1.4, ORANGE, n=16)
    glyph_triangle(tx + 15.6, gy + 8.9, 5.8, n=10)
    # workspace + WebMCP
    box(wx + 1.8, gy + 12.2, ww - 3.6, 5.6, fc="white", ec=LGREY, lw=0.5, r=0.8, z=3)
    text(wx + 3.2, gy + 15, "workspace", 5.3, INK, va="center", weight="bold", zorder=4)
    text(wx + ww - 3.2, gy + 15, "groups · views · locus · log", 4.3, GREY, ha="right", va="center", zorder=4)
    box(wx + 1.8, gy + 19, ww - 3.6, 5.8, fc="#fdf6f1", ec=AGT, lw=0.6, r=0.8, z=3)
    text(wx + 3.2, gy + 20.9, "WebMCP", 5.3, AGT, va="center", weight="bold", zorder=4)
    text(wx + 3.2, gy + 23.4, "open_view · focus · get_selection · capture", 4.3, GREY, va="center",
         zorder=4, family=MONO)

    # ---------------------------------------------------------------- links
    arrow(mx + mw, ty + 14, wx, ty + 14, style="<|-|>", color=GREY, lw=0.6)
    text((mx + mw + wx) / 2, ty + 13, "REST\nSSE", 4.3, GREY, ha="center", va="bottom", linespacing=1.1)
    # researcher: bus above the boxes
    by = ty - 4.2
    d1, d2 = mx + mw * 0.72, wx + ww * 0.72
    A.plot([ux + uw, ux + uw + 3, ux + uw + 3, d2], [ty + 5.5, ty + 5.5, by, by], color=RES, lw=0.7, zorder=2,
           solid_capstyle="projecting", solid_joinstyle="miter")
    arrow(d1, by, d1, ty - 0.2, color=RES, lw=0.7, shrink=(0, 0))
    arrow(d2, by, d2, ty - 0.2, color=RES, lw=0.7, shrink=(0, 0))
    tag(mx + mw * 0.36, by, "notebooks", RES)
    tag(wx + ww * 0.3, by, "GUI", RES)
    # agents: bus below the boxes
    ly = ty + bh + 4.2
    A.plot([ux + uw / 2, ux + uw / 2, d2], [ty + bh, ly, ly], color=AGT, lw=0.8, zorder=2,
           solid_capstyle="projecting", solid_joinstyle="miter")
    arrow(d1, ly, d1, ty + bh + 0.2, color=AGT, lw=0.8, shrink=(0, 0))
    arrow(d2, ly, d2, ty + bh + 0.2, color=AGT, lw=0.8, shrink=(0, 0))
    tag(mx + mw * 0.36, ly, "writes uchrom code, guided by skills", AGT)
    tag(wx + ww * 0.3, ly, "WebMCP · uchrom.browser.connect()", AGT)


# --------------------------------------------------------------------------- real data (Takei 2025 FOV 0)

REAL = np.load(HERE / "_cache/takei_fov0.npz")          # extract_data.py
CT_REAL = {"Granule": "#5b8db8", "Bergmann": "#5aa577", "Purkinje": "#c9745a", "MLI1": "#a58bc7",
           "MLI2+PLI": "#d4a24c", "Other": "#b9bdc4"}
LASSO = "Bergmann"


def window(x, y, w, h, url, right=None, z=1):
    """A browser window: shadow, title bar with traffic lights and address pill. Returns y of the content."""
    shadow_box(x, y, w, h, fc="white", ec="#9fb0cc", lw=0.7, z=z)
    A.add_patch(FancyBboxPatch((x, y), w, 4.4, boxstyle="round,pad=0,rounding_size=1.2", fc="#e9eef6",
                               ec="none", zorder=z + 1))
    A.add_patch(Rectangle((x, y + 3), w, 1.4, fc="#e9eef6", ec="none", zorder=z + 1))
    for k, c in enumerate(["#ec6a5e", "#f4bf4f", "#61c554"]):
        A.add_patch(Circle((x + 2.2 + k * 2, y + 2.2), 0.6, fc=c, ec="none", zorder=z + 2))
    box(x + 9, y + 1.0, min(w - (34 if right else 12), 60), 2.4, fc="white", ec="none", r=1.2, z=z + 2)
    text(x + 10.2, y + 2.2, url, 4.2, GREY, va="center", zorder=z + 3)
    if right:
        text(x + w - 1.8, y + 2.2, right, 5, INDIGO, ha="right", va="center", zorder=z + 3, weight="bold")
    return y + 4.4


def pane2(x, y, w, h, title, active=False, badge=None, num=None, scope=None):
    """A pane with a one-line header; returns the content box (x, y, w, h)."""
    box(x, y, w, h, fc="white", ec=INDIGO if active else "#d5dae2", lw=0.8 if active else 0.4, r=0.6, z=3)
    A.add_patch(Rectangle((x + 0.3, y + 0.3), w - 0.6, 2.7, fc="#f5f6f8", ec="none", zorder=3))
    tx = x + 1.2
    if num is not None:
        A.add_patch(Circle((x + 1.8, y + 1.65), 1.05, fc=INK, ec="none", zorder=5))
        text(x + 1.8, y + 1.7, str(num), 4.2, "white", ha="center", va="center", weight="bold", zorder=6)
        tx = x + 3.5
    text(tx, y + 1.65, title, 4.5, INK, va="center", zorder=4)
    text(x + w - 1.2, y + 1.65, "□  ×", 4.2, GREY, ha="right", va="center", zorder=4)
    if scope:
        A.text(x + w - 6.4, y + 1.65, scope, fontsize=F(3.9), color=CT_REAL[LASSO], ha="right", va="center", zorder=5,
               bbox=dict(boxstyle="round,pad=0.2,rounding_size=0.5", fc="#e8f4ec", ec="none"))
    if badge:
        text(x + w - 5.2, y + 1.65, badge, 4.2, INDIGO, ha="right", va="center", zorder=4)
    return x + 0.6, y + 3.2, w - 1.2, h - 3.8


def draw_umap(ax, lasso=LASSO, s=7):
    u = REAL["umap"]
    ct = REAL["cell_type"]
    sel = ct == lasso
    ax.scatter(u[~sel, 0], u[~sel, 1], s=s, c=[CT_REAL.get(c, GREY) for c in ct[~sel]], lw=0.3,
               edgecolors="white", alpha=0.45, zorder=2)
    ax.scatter(u[sel, 0], u[sel, 1], s=s * 1.4, c=CT_REAL[lasso], lw=0.4, edgecolors="white", zorder=3)
    c = u[sel].mean(0)
    r = np.ptp(u[sel], 0) / 2 + np.ptp(u, 0) * 0.07
    t = np.linspace(0, 2 * np.pi, 60)
    wob = 1 + 0.06 * np.sin(3 * t + 1)
    ax.plot(c[0] + r[0] * wob * np.cos(t), c[1] + r[1] * wob * np.sin(t), color=INK, lw=0.6, ls=(0, (2.5, 1.2)),
            zorder=4)
    ax.set_xticks([]), ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    pad = np.ptp(u, 0) * 0.08
    ax.set_xlim(u[:, 0].min() - pad[0], u[:, 0].max() + pad[0])
    ax.set_ylim(u[:, 1].min() - pad[1], u[:, 1].max() + pad[1])


def draw_nuclei(ax, focus=LASSO):
    xyz, cell, tr = REAL["xyz"], REAL["xyz_cell"], REAL["xyz_trace"]
    ct = REAL["cell_type"]
    vol = REAL["nuc_volume"]
    for i in range(len(ct)):
        m = cell == i
        if not m.any():
            continue
        on = ct[i] == focus
        cen = xyz[m, :2].mean(0)
        r = (3 * vol[i] / (4 * np.pi)) ** (1 / 3) if np.isfinite(vol[i]) else 3
        ax.add_patch(Circle(cen, r, fc=CT_REAL[ct[i]] if on else "#eef0f3", ec="none",
                            alpha=0.22 if on else 1, zorder=1))
        for t in np.unique(tr[m]):
            mm = m & (tr == t)
            p = xyz[mm]
            ax.plot(p[:, 0], p[:, 1], lw=0.45 if on else 0.2, color=CT_REAL[ct[i]] if on else "#c8ccd3",
                    alpha=0.95 if on else 0.6, zorder=3 if on else 2, solid_capstyle="round")
    ax.set_aspect("equal"), ax.axis("off")
    ax.set_xlim(xyz[:, 0].min() - 2, xyz[:, 0].max() + 2), ax.set_ylim(xyz[:, 1].min() - 2, xyz[:, 1].max() + 2)


def draw_triangle(ax, mat, base, height, flip=False, cmap="viridis_r", vmin=None, vmax=None):
    """HiGlass-style rotated triangle of a symmetric matrix in axis data coords, x in [0, n]."""
    n = mat.shape[0]
    i, j = np.triu_indices(n, 0)
    v = mat[i, j]
    ok = np.isfinite(v) & ((j - i) <= height)
    sgn = -1 if flip else 1
    polys = [[((a + b) / 2, base + sgn * (b - a) / 2 - sgn * 0.5 + sgn * 0.5),
              ((a + b + 1) / 2, base + sgn * ((b - a) / 2 + 0.5)),
              ((a + b + 2) / 2, base + sgn * (b - a) / 2),
              ((a + b + 1) / 2, base + sgn * ((b - a) / 2 - 0.5))] for a, b in zip(i[ok], j[ok])]
    pc = PolyCollection(polys, array=v[ok], cmap=cmap, edgecolors="face", linewidths=0.05, zorder=3)
    pc.set_clim(vmin, vmax)
    ax.add_collection(pc)
    return pc


def genome_window(groups=(LASSO, "Granule"), n=30):
    """The n-bin window with the most finite pixels in both groups' maps."""
    ma, mb = REAL[f"dist_{groups[0]}"], REAL[f"dist_{groups[1]}"]
    ok = np.isfinite(ma) & np.isfinite(mb)
    best = max(range(ma.shape[0] - n), key=lambda s0: ok[s0:s0 + n, s0:s0 + n].sum())
    return best, best + n


def draw_genome(ax, groups=(LASSO, "Granule"), labels=True, n=30, depth=12):
    """Two groups' distance maps as HiGlass-style bands (up to `depth` bins apart), mirrored, + a track."""
    s0, s1 = genome_window(groups, n)
    ma, mb = REAL[f"dist_{groups[0]}"][s0:s1, s0:s1], REAL[f"dist_{groups[1]}"][s0:s1, s0:s1]
    both = np.r_[ma[np.isfinite(ma)], mb[np.isfinite(mb)]]
    vmin, vmax = np.nanpercentile(both, [3, 97])
    half = depth / 2 + 0.5
    trk_h = 3.2
    base = half + 0.2
    draw_triangle(ax, ma, base + 0.2, depth, vmin=vmin, vmax=vmax)
    draw_triangle(ax, mb, base - 0.2, depth, flip=True, vmin=vmin, vmax=vmax)
    tr = REAL[f"h3k27ac_{groups[0]}"][s0:s1]
    tr = np.nan_to_num(tr - np.nanmin(tr))
    top = base + half + 1.2
    ax.bar(np.arange(n) + 0.5, tr / max(tr.max(), 1e-9) * trk_h, bottom=top, width=0.85, color=ORANGE, lw=0,
           zorder=3)
    ax.set_xlim(0, n), ax.set_ylim(base - half - 2.6, top + trk_h + 2.4)
    ax.axis("off")
    if labels:
        ax.text(0.2, base + half - 1.0, groups[0], fontsize=F(4.3), color=CT_REAL[groups[0]], weight="bold", va="top", bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.85), 
                zorder=5)
        ax.text(0.2, base - half + 1.0, groups[1], fontsize=F(4.3), color=CT_REAL[groups[1]], weight="bold", bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.85), 
                va="bottom", zorder=5)
        ax.text(n, top + trk_h + 0.2, "H3K27ac", fontsize=F(4.2), color=ORANGE, ha="right", va="bottom")
        ax.text(n, base - half - 2.4, f"chr15 : {s0}–{s1} Mb · median distance", fontsize=F(4.0), color=GREY,
                ha="right", va="bottom")


def draw_rg(ax, highlight=LASSO, fs=4.5):
    fs = F(fs)
    bins = np.linspace(0.2, 3.6, 35)
    for g in ["Granule", "Bergmann", "Purkinje"]:
        v = REAL[f"rg_{g}"]
        on = g in (highlight, "Granule")
        hh, e = np.histogram(v, bins=bins, density=True)
        ax.fill_between(e[:-1], hh, step="post", color=CT_REAL[g], alpha=0.25 if on else 0.08, lw=0)
        ax.step(e[:-1], hh, where="post", color=CT_REAL[g], lw=0.8 if on else 0.5, alpha=1 if on else 0.5,
                label=f"{g} {np.median(v):.2f}")
        ax.axvline(np.median(v), color=CT_REAL[g], lw=0.5, ls=":", alpha=1 if on else 0.5)
    ax.set_yticks([]), ax.spines["left"].set_visible(False)
    ax.set_xlabel("trace Rg (µm)", fontsize=fs, labelpad=0.5)
    ax.tick_params(labelsize=max(MIN_PT, fs - 0.3), length=1.5, pad=1)
    ax.legend(frameon=False, fontsize=max(MIN_PT, fs - 0.3), handlelength=0.9, loc="upper left", bbox_to_anchor=(1.0, 1.05),
              title="median Rg", title_fontsize=max(MIN_PT, fs - 0.3), labelspacing=0.3, alignment="left")


# --------------------------------------------------------------------------- b: the four panes

import matplotlib.patheffects as pe

CHROM_COL = ["#4c72b0", "#dd8452", "#8172b3", "#c44e52", "#937860"]
SHOW_CHROMS = {"chr7": "#dd6b2f", "chr15": "#3b63a8"}      # chromosomes drawn in colour in the 3-D pane


def _clean(ax):
    ax.set_xticks([]), ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)


def _smooth_hull(pts, pad):
    """A smooth closed curve around pts (convex hull, padded, Chaikin-smoothed)."""
    from scipy.spatial import ConvexHull
    c = pts.mean(0)
    if len(pts) >= 3:
        h = pts[ConvexHull(pts).vertices]
    else:
        h = pts
    ang = np.arctan2(h[:, 1] - c[1], h[:, 0] - c[0])
    h = h[np.argsort(ang)]
    d = h - c
    h = c + d * (1 + pad / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9))
    for _ in range(4):
        q = np.roll(h, -1, 0)
        h = np.vstack([np.c_[0.75 * h + 0.25 * q], np.c_[0.25 * h + 0.75 * q]])
        h = h.reshape(2, -1, 2).transpose(1, 0, 2).reshape(-1, 2)
    return np.vstack([h, h[:1]])


def draw_umap_b(ax, lasso=LASSO):
    u, ct = REAL["umap"], REAL["cell_type"]
    sel = ct == lasso
    span = np.ptp(u, 0)
    hull = _smooth_hull(u[sel], pad=span.mean() * 0.07)
    ax.fill(hull[:, 0], hull[:, 1], color=CT_REAL[lasso], alpha=0.12, lw=0, zorder=1)
    ax.plot(hull[:, 0], hull[:, 1], color=INK, lw=0.6, ls=(0, (3, 1.5)), zorder=2)
    for g in dict.fromkeys(ct):
        m = ct == g
        on = g == lasso
        ax.scatter(u[m, 0], u[m, 1], s=16 if on else 11, color=CT_REAL.get(g, GREY), lw=0.5, edgecolors="white",
                   alpha=1 if on else 0.75, zorder=4 if on else 3)
        if m.sum() >= 2 and g != "Other":
            c = u[m].mean(0)
            off = np.array([0, span[1] * 0.1]) * (1 if g not in ("Granule", lasso) else -1)
            if g == lasso:
                c = np.array([u[m, 0].mean(), u[m, 1].min()])
                off = np.array([0, -span[1] * 0.12])
            ax.text(*(c + off), g, fontsize=F(4.1), color=CT_REAL[g], ha="center", va="center", weight="bold",
                    zorder=6, path_effects=[pe.withStroke(linewidth=1.5, foreground="white")])
    ax.text(*(hull[np.argmax(hull[:, 1])] + [0, span[1] * 0.02]), "lasso 1", fontsize=F(4.1), color=INK,
            ha="center", va="bottom", zorder=6, path_effects=[pe.withStroke(linewidth=1.5, foreground="white")])
    pad = span * 0.12
    ax.set_xlim(u[:, 0].min() - pad[0], u[:, 0].max() + pad[0])
    ax.set_ylim(u[:, 1].min() - pad[1] * 1.3, u[:, 1].max() + pad[1])
    _clean(ax)
    x0, y0 = ax.get_xlim()[0] + pad[0] * 0.25, ax.get_ylim()[0] + pad[1] * 0.25
    L = span.mean() * 0.12
    ax.annotate("", (x0 + L, y0), (x0, y0), arrowprops=dict(arrowstyle="-|>", lw=0.5, color=GREY, mutation_scale=4))
    ax.annotate("", (x0, y0 + L * span[1] / span[0]), (x0, y0),
                arrowprops=dict(arrowstyle="-|>", lw=0.5, color=GREY, mutation_scale=4))
    ax.text(x0 + L * 1.1, y0, "UMAP", fontsize=F(3.9), color=GREY, va="center")


def _sphere(ax, c, r, col, alpha=1.0, z=1):
    """Shaded sphere: concentric discs, lighter and shifted towards the upper left."""
    base = np.array(mpl.colors.to_rgb(col))
    for k in range(9):
        f = k / 8
        cc = base + (1 - base) * (0.15 + 0.7 * f ** 1.5)
        ax.add_patch(Circle((c[0] - r * 0.28 * f, c[1] + r * 0.28 * f), r * (1 - 0.75 * f), fc=cc, ec="none",
                            alpha=alpha, zorder=z))


def draw_nuclei_b(ax, focus=LASSO):
    xyz, cell, tr, chrom = REAL["xyz"], REAL["xyz_cell"], REAL["xyz_trace"], REAL["xyz_chrom"]
    ct, vol = REAL["cell_type"], REAL["nuc_volume"]
    sel_cells = np.flatnonzero(ct == focus)
    cen_all = np.array([np.nanmedian(xyz[cell == i, :2], 0) if (cell == i).any() else [np.nan, np.nan]
                        for i in range(len(ct))])
    sc = cen_all[sel_cells]
    dd = np.linalg.norm(sc[:, None] - sc[None], axis=-1)
    best = np.argmax((dd < 22).sum(1))                      # the selected cell with most selected neighbours
    ctr = sc[best]
    half = 8.0                                               # about one nucleus and its neighbours
    for i in range(len(ct)):
        m = cell == i
        if not m.any():
            continue
        on = i in sel_cells
        cen = np.nanmedian(xyz[m, :2], 0)
        if np.any(np.abs(cen - ctr) > half * 1.6):
            continue
        r = np.nanpercentile(np.linalg.norm(xyz[m, :2] - cen, axis=1), 90)   # nucleus extent from its spots
        _sphere(ax, cen, r * 1.1, CT_REAL[ct[i]] if on else "#c9ced6", alpha=0.5 if on else 0.35, z=1)
        for t in np.unique(tr[m]):
            mm = m & (tr == t)
            p = xyz[mm, :2]
            cname = REAL["draw_chroms"][chrom[mm][0]]
            col = SHOW_CHROMS.get(cname) if on else None
            # the browser's default "max bond": no line across a gap > 10x the median spacing
            step = np.linalg.norm(np.diff(p, axis=0), axis=1)
            cut = step > 10 * np.nanmedian(step) if len(step) else step
            q = p.copy().astype(float)
            q = np.insert(q, np.flatnonzero(cut) + 1, np.nan, axis=0)
            if col:
                ax.plot(q[:, 0], q[:, 1], lw=0.35, color=col, alpha=0.6, zorder=4)
                ax.scatter(p[:, 0], p[:, 1], s=0.9, color=col, lw=0, zorder=5)
            else:
                ax.scatter(p[:, 0], p[:, 1], s=0.35, color="#9aa1ab" if on else "#c3c8cf", lw=0,
                           alpha=0.55 if on else 0.4, zorder=3 if on else 2)
    ax.set_xlim(ctr[0] - half * 1.45, ctr[0] + half * 1.45), ax.set_ylim(ctr[1] - half, ctr[1] + half)
    ax.set_aspect("equal", adjustable="datalim")
    ax.axis("off")
    xl, yl = ax.get_xlim(), ax.get_ylim()
    sb = 2.0
    ax.plot([xl[0] + 0.05 * (xl[1] - xl[0]), xl[0] + 0.05 * (xl[1] - xl[0]) + sb], [yl[0] + 0.06 * (yl[1] - yl[0])] * 2,
            color=INK, lw=0.9, solid_capstyle="butt", zorder=6)
    ax.text(xl[0] + 0.05 * (xl[1] - xl[0]) + sb / 2, yl[0] + 0.08 * (yl[1] - yl[0]), "2 µm", fontsize=F(3.9),
            color=INK, ha="center", va="bottom", zorder=6)
    for k, (n, col) in enumerate(list(SHOW_CHROMS.items()) + [("other chr.", "#8a93a0")]):
        ax.text(0.995, 0.03 + (len(SHOW_CHROMS) - k) * 0.11, n, transform=ax.transAxes, fontsize=F(3.9),
                color=col, ha="right", va="bottom", weight="bold", zorder=6,
                path_effects=[pe.withStroke(linewidth=1.5, foreground="white")])


def draw_tracks_b(ax, n=30, depth=10):
    """IF tracks (lasso vs all cells) above the lasso group's distance band, on one genomic axis."""
    s0, s1 = genome_window((LASSO, "Granule"), n)
    x = np.arange(n) + 0.5
    rows = [("H3K27ac", ORANGE), ("H3K9me3", PURPLE), ("LaminB1", "#6b7280")]
    rh, gap = 3.0, 1.0
    base = depth / 2 + 0.6
    top = base + depth / 2 + 1.0
    for k, (tr, col) in enumerate(rows[::-1]):
        y0 = top + k * (rh + gap)
        a = REAL[f"trk_{tr}_{LASSO}"][s0:s1]
        b = REAL[f"trk_{tr}_all"][s0:s1]
        both = np.r_[a[np.isfinite(a)], b[np.isfinite(b)]]
        lo_, hi_ = np.nanpercentile(both, [2, 98]) if len(both) else (0, 1)
        sc = lambda v: y0 + np.clip((v - lo_) / max(hi_ - lo_, 1e-9), 0, 1) * rh
        ax.fill_between(x, y0, sc(np.nan_to_num(a, nan=lo_)), step="mid", color=CT_REAL[LASSO], alpha=0.55, lw=0)
        ax.step(x, sc(np.nan_to_num(b, nan=lo_)), where="mid", color=INK, lw=0.5)
        ax.text(-0.3, y0 + rh / 2, tr, fontsize=F(3.9), color=col, ha="right", va="center", weight="bold")
    ma = REAL[f"dist_{LASSO}"][s0:s1, s0:s1]
    vmin, vmax = np.nanpercentile(ma[np.isfinite(ma)], [3, 97])
    draw_triangle(ax, ma, base, depth, vmin=vmin, vmax=vmax)
    ax.text(-0.3, base + depth / 4, "3-D\ndistance", fontsize=F(3.9), color=INK, ha="right", va="center",
            linespacing=0.95)
    ax.set_xlim(-7.5, n), ax.set_ylim(base - 1.5, top + len(rows) * (rh + gap))
    ax.axis("off")
    ax.text(n, base - 1.2, f"chr15 : {s0}–{s1} Mb", fontsize=F(3.9), color=GREY, ha="right", va="top")
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=CT_REAL[LASSO], alpha=0.55, label="lasso 1"),
                       Line2D([], [], color=INK, lw=0.6, label="all cells")], loc="upper right",
              bbox_to_anchor=(1.0, 1.06), ncol=2, frameon=False, fontsize=F(3.9), handlelength=1.0,
              handletextpad=0.4, columnspacing=0.8, borderaxespad=0)


def draw_scatter_b(ax, lasso=LASSO):
    ct = REAL["cell_type"]
    xv, yv = REAL["nuc_volume"], REAL["cell_if_H3K9me3"]
    sel = ct == lasso
    for g in dict.fromkeys(ct):
        m = (ct == g) & ~sel
        ax.scatter(xv[m], yv[m], s=9, color=CT_REAL.get(g, GREY), lw=0.4, edgecolors="white", alpha=0.7, zorder=2)
    ax.scatter(xv[sel], yv[sel], s=14, color=CT_REAL[lasso], lw=0.7, edgecolors=INK, zorder=3)
    ax.set_xscale("log")
    ax.set_xlabel("nuclear volume (µm³)", fontsize=F(4.3), labelpad=0.5)
    ax.set_ylabel("H3K9me3 IF", fontsize=F(4.3), labelpad=0.5)
    ax.tick_params(labelsize=F(4.0), length=1.5, pad=1)
    ax.xaxis.set_minor_formatter(mpl.ticker.NullFormatter())
    ax.set_xticks([100, 300, 1000], ["100", "300", "1000"])
    for g in ["Granule", "Purkinje"]:
        m = ct == g
        ax.text(np.exp(np.log(xv[m]).mean()), np.nanmax(yv[m]) * 1.06, g, fontsize=F(3.9), color=CT_REAL[g],
                ha="center", va="bottom", weight="bold")


# --------------------------------------------------------------------------- b  browser, linked exploration

def panel_b(x0=0, y0=61, w=104, h=66):
    panel(x0, y0, "b", "Linked exploration in the browser",
          "Takei 2025 cerebellum · lasso Bergmann cells in the RNA UMAP; every pane follows the selection")
    y = window(x0, y0 + 8, w, h - 8, "localhost:8765  ·  U-Chrom", right="takei2025_fov0.h5cd")
    # toolbar
    A.add_patch(Rectangle((x0 + 0.35, y), w - 0.7, 3.6, fc="white", ec="none", zorder=2))
    A.plot([x0 + 0.4, x0 + w - 0.4], [y + 3.6, y + 3.6], color="#e3e6eb", lw=0.4, zorder=3)
    box(x0 + 17.5, y + 0.6, 24, 2.4, fc="#f5f6f8", ec="#d5dae2", lw=0.3, r=1.2, z=3)
    text(x0 + 18.7, y + 1.8, "chr15 : 3 – 104 Mb", 4.3, INK, va="center", zorder=4)
    text(x0 + 43, y + 1.8, "−   +   full", 4.3, GREY, va="center", zorder=4)
    for k, lab in enumerate(["Tabs", "Columns", "Rows", "Grid"]):
        bx = x0 + w - 36 + k * 8.6
        box(bx, y + 0.6, 8.2, 2.4, fc=INDIGO if lab == "Grid" else "#f5f6f8", ec="none", r=0.5, z=3)
        text(bx + 4.1, y + 1.8, lab, 4.1, "white" if lab == "Grid" else GREY, ha="center", va="center", zorder=4)
    text(x0 + 1.5, y + 1.8, "+ View", 4.3, INDIGO, va="center", zorder=4, weight="bold")
    y += 4.4
    bottom = y0 + h - 0.8
    # sidebar
    sx, sw = x0 + 0.8, 15.5
    A.add_patch(Rectangle((sx, y), sw, bottom - y, fc="#f7f8fa", ec="none", zorder=2))
    text(sx + 1, y + 1.6, "GROUPS", 3.9, GREY, va="center", weight="bold", zorder=3)
    ct = REAL["cell_type"]
    rows = [("Granule", (ct == "Granule").sum()), ("Bergmann", (ct == "Bergmann").sum()),
            ("Purkinje", (ct == "Purkinje").sum()), ("MLI1", (ct == "MLI1").sum())]
    for k, (g, n) in enumerate(rows):
        yy = y + 3.7 + k * 2.4
        if g == LASSO:
            box(sx + 0.4, yy - 1.1, sw - 0.8, 2.2, fc="#e3eaf6", ec="none", r=0.4, z=3)
        A.add_patch(Circle((sx + 1.6, yy), 0.55, fc=CT_REAL[g], ec="none", zorder=4))
        text(sx + 2.8, yy, g, 4.2, INK, va="center", zorder=4, weight="bold" if g == LASSO else "normal")
        text(sx + sw - 0.8, yy, str(n), 4.0, GREY, ha="right", va="center", zorder=4)
    yy = y + 3.7 + len(rows) * 2.4
    A.add_patch(Circle((sx + 1.6, yy), 0.55, fc="white", ec=INK, lw=0.4, ls=(0, (1, 0.6)), zorder=4))
    text(sx + 2.8, yy, "lasso 1", 4.2, INK, va="center", zorder=4)
    text(sx + sw - 0.8, yy, "8", 4.0, GREY, ha="right", va="center", zorder=4)
    y2 = yy + 3.2
    text(sx + 1, y2, "CELLS  (47)", 3.9, GREY, va="center", weight="bold", zorder=3)
    ids, cts = REAL["cell_id"], REAL["cell_type"]
    order = np.argsort([c != LASSO for c in cts], kind="stable")[:9]
    for k, i in enumerate(order):
        yy = y2 + 2.2 + k * 2.1
        if yy > bottom - 1.2:
            break
        A.add_patch(Rectangle((sx + 1.0, yy - 0.55), 1.1, 1.1, fc=CT_REAL[cts[i]], ec="none", zorder=4))
        text(sx + 2.8, yy, ids[i], 4.0, INK if cts[i] == LASSO else GREY, va="center", zorder=4)
    # panes 2x2
    gx = sx + sw + 1.0
    gw, gh = x0 + w - 0.8 - gx, bottom - y - 0.8
    pw, ph = (gw - 1.0) / 2, (gh - 1.0) / 2
    y += 0.4
    boxes = [(gx, y), (gx + pw + 1.0, y), (gx, y + ph + 1.0), (gx + pw + 1.0, y + ph + 1.0)]
    titles = ["Embedding · RNA UMAP", "3D", "Genome · IF + 3-D", "Stats · cell fields"]
    cs = [pane2(bx, by, pw, ph, t, active=(k == 0), num=k + 1, scope=None if k == 0 else "lasso 1")
          for k, ((bx, by), t) in enumerate(zip(boxes, titles))]
    draw_umap_b(ax_mm(cs[0][0] + 0.5, cs[0][1] + 0.3, cs[0][2] - 1, cs[0][3] - 0.6))
    draw_nuclei_b(ax_mm(cs[1][0] + 0.3, cs[1][1] + 0.2, cs[1][2] - 0.6, cs[1][3] - 0.4))
    draw_tracks_b(ax_mm(cs[2][0] + 0.5, cs[2][1] + 0.4, cs[2][2] - 1, cs[2][3] - 0.8))
    draw_scatter_b(ax_mm(cs[3][0] + 7.5, cs[3][1] + 1.2, cs[3][2] - 9.5, cs[3][3] - 6.2))


# --------------------------------------------------------------------------- c  browser performance

LAT_ROWS = [  # (label, dataset kind, interaction name in server.json)
    ("focus a cell", "imaging", "focus a cell"),
    ("pan locus · 2 IF tracks", "imaging", "pan locus (2 tracks, 20 Mb)"),
    ("pseudo-bulk Hi-C · 50 cells", "hic", "pseudo-bulk, 50 cells, chr1"),
    ("contact map · ≤1,000 bins", "hic", "contact map, chr1 (≤1,000 bins)"),
    ("pseudo-bulk Hi-C · 500 cells", "hic", "pseudo-bulk, 500 cells, chr1"),
    ("distance map · 20 cells", "imaging", "distance map, chr15, 20-cell group"),
    ("lasso → all views", "imaging", "lasso → re-scope views"),
    ("distance map · all cells", "imaging", "distance map, chr15, all cells"),
]


def panel_c(d, x0=108, y0=61):
    panel(x0, y0, "c", "Interactive at real scale")
    res = load_results()
    fe_, sv_ = res.get("frontend"), res.get("server")
    if fe_ and sv_:
        gpu = fe_["machine"].get("gpu", "")
        gpu = gpu.split("Renderer: ")[-1].split(",")[0] if "Renderer: " in gpu else gpu
        loads = [x for d_ in (fe_, sv_) for x in (d_.get("load_avg_start", [None])[0],
                                                   d_.get("load_avg_end", [None])[0]) if x is not None]
        browser = fe_["machine"]["browser"].replace("chromium", "Chromium").split(".")[0]
        text(x0 + 4, y0 + 3.6, f"{gpu} · {browser} · load avg {min(loads):.1f}–{max(loads):.1f}", 4.0, GREY,
             va="top")
    ty = y0 + 8.5
    fe, sv = res.get("frontend"), res.get("server")
    # c1: time to first frame vs size
    ax = ax_mm(x0 + 9, ty + 2.0, 50, 18)
    if fe:
        n = np.array([x["n_spots"] for x in fe["datasets"]], float)
        ff = np.array([[l["first_frame_ms"] for l in x["loads"]] for x in fe["datasets"]]) / 1e3
        op = np.array([x["open_s"] for x in fe["datasets"]])
        pts = np.array([x["loads"][0]["points"] for x in fe["datasets"]])
        real = np.array(["_x1." in x["file"] for x in fe["datasets"]])
        med = np.median(ff, 1)
        ax.plot(n, med, color=INDIGO, lw=1.0, zorder=3, label="open page → first frame")
        ax.vlines(n, ff.min(1), ff.max(1), color=INDIGO, lw=0.6, zorder=3)
        ax.plot(n, op, color=GREY, lw=0.8, ls=(0, (3, 1.5)), zorder=2, label="load file on the server (once)")
        for arr, col in [(med, INDIGO), (op, GREY)]:
            ax.scatter(n[real], arr[real], s=9, color=col, zorder=4, lw=0)
            ax.scatter(n[~real], arr[~real], s=9, facecolor="white", edgecolor=col, lw=0.7, zorder=4)
        cap = pts < n
        for xi, yi in zip(n[cap], med[cap]):
            ax.annotate(f"{pts[cap][0] / 1e6:.0f} M drawn (cap)", (xi, yi), (0, -8), textcoords="offset points",
                        fontsize=F(4.3), color=GREY, ha="center", va="top")
        fps = [x["loads"][0]["fps"]["fps"] for x in fe["datasets"]]
        ax.text(0.02, 0.98, f"{min(fps):.0f}–{max(fps):.0f} frames/s at every size", transform=ax.transAxes,
                fontsize=F(4.3), color=INDIGO, va="top")
        ax.set_xscale("log"), ax.set_yscale("log")
        ax.set_xlim(2.5e5, 2e7)
        ax.legend(frameon=False, loc="lower right", fontsize=F(4.3), handlelength=1.6, borderaxespad=0.1)
    ax.set_xlabel("spots in the file  (● real · ○ tiled copies)", labelpad=1)
    ax.set_ylabel("time (s)", labelpad=1)
    # c2: latency per interaction
    ax = ax_mm(x0 + 25, ty + 28.5, 34, 20.5)
    if sv:
        by = {}
        for ds in sv["datasets"]:
            key = "imaging" if ds["kind"] == "imaging" else ds["kind"]
            by.setdefault(key, ds)
            if ds["kind"] == "imaging-replicated":
                by.setdefault("rep", []).append(ds)
        yy = np.arange(len(LAT_ROWS))[::-1]
        for y, (lab, kind, name) in zip(yy, LAT_ROWS):
            row = {r["interaction"]: r for r in by[kind]["interactions"]}[name]
            col = TEAL if kind == "hic" else INDIGO
            ax.barh(y, row["median_ms"], color=col, height=0.6, alpha=0.9)
            ax.plot([row["median_ms"], row["p95_ms"]], [y, y], color=INK, lw=0.5)
            if kind == "imaging":
                for ds, mk in zip(by.get("rep", []), ["o", "D"]):
                    r2 = {r["interaction"]: r for r in ds["interactions"]}.get(name)
                    if r2:
                        ax.scatter(r2["median_ms"], y, s=7, marker=mk, facecolor="white", edgecolor=INK, lw=0.5,
                                   zorder=4)
        ax.axvline(100, color=ORANGE, lw=0.6, ls=(0, (3, 1.5)))
        ax.set_ylim(-1.3, len(LAT_ROWS) - 0.4)
        ax.text(115, -0.95, "100 ms", fontsize=F(4.3), color=ORANGE, ha="left", va="center")
        ax.set_yticks(yy, [r[0] for r in LAT_ROWS], fontsize=F(4.4))
        ax.set_xscale("log"), ax.set_xlim(2, 5000)
        ax.tick_params(axis="y", length=0)
        from matplotlib.lines import Line2D
        from matplotlib.patches import Patch
        hs = [Patch(color=INDIGO, label="Takei 2025 FOV 0"), Patch(color=TEAL, label="scHiCAR MOp")]
        for ds, mk in zip(by.get("rep", []), ["o", "D"]):
            hs.append(Line2D([], [], ls="none", marker=mk, ms=3, mfc="white", mec=INK, mew=0.5,
                             label=f"{ds['n_spots'] / 1e6:.1f} M spots, tiled"))
        ax.legend(handles=hs, frameon=False, ncol=2, fontsize=F(4.2), loc="upper center",
                  bbox_to_anchor=(0.2, -0.36), handlelength=1.0, columnspacing=1.0, handletextpad=0.4)
    ax.set_xlabel("response time (ms) · median, p95", labelpad=1)


# --------------------------------------------------------------------------- d  agent sessions

def chat_line(x, y, s, color=INK, size=4.5, mono=False, **kw):
    text(x, y, s, size, color, va="top", family=MONO if mono else None, zorder=5, **kw)


def transcript(x, y, w, h, tag, question, skill, calls, answer):
    box(x, y, w, h, fc="#fbfbfc", ec=LGREY, lw=0.5)
    chat_line(x + 1.2, y + 1, tag, GREY, 4.3, weight="bold")
    box(x + 10, y + 3.8, w - 11, 5.6, fc="#e9eef6", ec="none", r=1.0, z=4)
    chat_line(x + 11, y + 4.4, question, INK, 4.5, linespacing=1.15)
    yy = y + 10.6
    box(x + 1.2, yy, 21, 3, fc="#fcefe6", ec=ORANGE, lw=0.4, r=0.5, z=4)
    chat_line(x + 2, yy + 0.5, "skill · " + skill, ORANGE, 4.3, weight="bold")
    for k, s in enumerate(calls):
        chat_line(x + 2, yy + 4 + k * 2.4, "▸ " + s, GREY, 4.1, mono=True)
    chat_line(x + 2, yy + 4.6 + len(calls) * 2.4, answer, INK, 4.4, linespacing=1.2)


AGENT_RUN = HERE / "agent_run"


def panel_d(d, x0=0, y0=133, w=104, h=67):
    import json as _json
    run = _json.loads((AGENT_RUN / "run.json").read_text())
    import re as _re
    m = _re.match(r"claude-([a-z]+)-(\d+)(?:-(\d+))?", str(run.get("model", "")))
    model = f"{m.group(1).title()} {m.group(2)}{'.' + m.group(3) if m.group(3) else ''}" if m else "Claude"
    panel(x0, y0, "d", "Researcher and agent hand work to each other",
          f"real Claude Code session ({model}, {run['num_turns']} turns, {run['elapsed_s']:.0f} s), trimmed (…); "
          "its two views redrawn from the data")
    ty = y0 + 9
    H_ = h - 10
    cw = 57
    x, y = x0 + 1, ty
    box(x, y, cw, H_, fc="#fbfbfc", ec=LGREY, lw=0.5)
    place_png(LOGO["claudecode"], x + 1.4, y + 1.0, h=2.6)
    chat_line(x + 6.2, y + 1, "Claude Code", ORANGE, 4.5, weight="bold")
    box(x + 9, y + 4, cw - 10, 5.4, fc="#e9eef6", ec="none", r=1.0, z=4)
    chat_line(x + 10, y + 4.5, "What is different about the cells I just\nselected in the browser? Show me.", INK, 4.5,
              linespacing=1.15)
    yy = y + 10.6
    for k, sk in enumerate(["show-in-browser", "compare-groups"]):
        box(x + 1.2 + k * 25, yy, 23.5, 3, fc="#fcefe6", ec=ORANGE, lw=0.4, r=0.5, z=4)
        chat_line(x + 2 + k * 25, yy + 0.5, "skill · " + sk, ORANGE, 4.2, weight="bold")
    code = [("ws = ub.connect(); sel = ws.selected_cells()", INDIGO),
            ("U, p = mannwhitneyu(x, y)   # each cell field, BH", INK),
            ("r = compare(cd, sel, rest, stat=s)  # rg, nuc vol", ORANGE),
            ("r = ws.select_cells(cells=rest,", INDIGO),
            ("                    name='other 39 cells')", INDIGO),
            ("ws.open_view('stats', stats='rg',", INDIGO),
            ("             compare_groups=[g, r])", INDIGO),
            ("ws.color_by('if.SOX2')", INDIGO),
            ("ws.open_view('embedding', embedding='if_umap')", INDIGO)]
    box(x + 1.2, yy + 3.7, cw - 2.4, len(code) * 2.35 + 1.0, fc="#f3f4f6", ec="none", r=0.6, z=4)
    for k, (c, col) in enumerate(code):
        chat_line(x + 2, yy + 4.2 + k * 2.35, c, col, 4.35, mono=True)
    ya = yy + 5.2 + len(code) * 2.35
    chat_line(x + 2, ya,
              "Your 8 cells are the Bergmann glia. … SOX2 (IF) 0.215 vs 0.041,\n"
              "r = +0.83, q = 0.002 — the only robust difference. … The\n"
              "chromatin looks slightly less compact (Rg 1.42 vs 1.26 µm,\n"
              "p = 0.055), but I wouldn't trust it: Rg tracks nuclear volume\n"
              "(ρ = 0.75). … One field of view, 8 vs 39 cells: exploratory.", INK, 4.3, linespacing=1.18)
    A.text(x + 2, y + H_ - 3.0, "uchrom analysis", fontsize=F(4.0), color=INK, va="top", zorder=6)
    A.text(x + 20, y + H_ - 3.0, "browser (connect)", fontsize=F(4.0), color=INDIGO, va="top", zorder=6)
    A.text(x + 40, y + H_ - 3.0, "skill script", fontsize=F(4.0), color=ORANGE, va="top", zorder=6)
    # the researcher's browser: the views the agent opened (captured from the page)
    bx, bw = x0 + cw + 4, w - cw - 4
    arrow(x0 + cw + 1.3, ty + 22, bx - 0.3, ty + 22, color=INDIGO, lw=0.8)
    yb = window(bx, ty, bw, H_, "researcher's browser")
    views = {v["type"]: v["pane"] for v in run["new_views"]}
    ph1 = 30.0
    c = pane2(bx + 0.8, yb + 0.7, bw - 1.6, ph1, f"{views.get('stats', 'P5')} · Stats · Rg", active=True, scope="lasso 1")
    draw_agent_rg(ax_mm(c[0] + 5.2, c[1] + 1.4, c[2] - 6.4, c[3] - 6.8))
    y2 = yb + 0.7 + ph1 + 0.7
    c2 = pane2(bx + 0.8, y2, bw - 1.6, ty + H_ - 0.8 - y2, f"{views.get('embedding', 'P4')} · Embedding · IF UMAP",
               active=True)
    draw_agent_umap(ax_mm(c2[0] + 0.5, c2[1] + 0.3, c2[2] - 9.5, c2[3] - 0.6),
                    ax_mm(c2[0] + c2[2] - 6.2, c2[1] + 2.5, 1.2, c2[3] - 5.5))


def draw_agent_rg(ax, lasso=LASSO):
    """The agent's Rg view: every trace, the selection vs the other cells (as in the browser)."""
    ct, tc, rg = REAL["cell_type"], REAL["rg_trace_cell"], REAL["rg_trace"]
    sel = np.isin(tc, np.flatnonzero(ct == lasso))
    rest = ~sel & (tc >= 0)
    bins = np.linspace(0.3, 4.2, 30)
    for m, col, lab, fill in [(sel, CT_REAL[lasso], "lasso 1", True), (rest, "#8a93a0", "other 39 cells", False)]:
        v = rg[m & np.isfinite(rg)]
        hh, e = np.histogram(v, bins=bins)
        hh = hh / hh.sum()
        if fill:
            ax.fill_between(e[:-1], hh, step="post", color=col, alpha=0.45, lw=0)
        ax.step(e[:-1], hh, where="post", color=col, lw=0.9 if not fill else 0.6)
        n_cells = len(np.unique(tc[m]))
        ax.plot([], [], color=col, lw=2.5 if fill else 1.0,
                label=f"{lab}: {np.median(v):.2f} µm · {n_cells} cells")
    ax.set_xlabel("trace Rg (µm)", fontsize=F(4.3), labelpad=0.5)
    ax.set_ylabel("fraction", fontsize=F(4.3), labelpad=0.5)
    ax.tick_params(labelsize=F(4.0), length=1.5, pad=1)
    ax.set_yticks([0, 0.1])
    ax.set_ylim(0, ax.get_ylim()[1] * 1.75)       # room for the legend above the bars
    ax.legend(frameon=False, fontsize=F(4.0), handlelength=0.9, loc="upper right", borderaxespad=0.1,
              title="median over traces", title_fontsize=F(4.0), alignment="right")


def draw_agent_umap(ax, cax, lasso=LASSO):
    """The agent's embedding view: IF UMAP, cells coloured by SOX2 IF; the selection ringed."""
    u, v, ct = REAL["if_umap"], REAL["cell_if_SOX2"], REAL["cell_type"]
    sel = ct == lasso
    vmax = np.nanpercentile(v, 99)
    sc = ax.scatter(u[:, 0], u[:, 1], c=v, cmap="viridis", vmin=np.nanmin(v), vmax=vmax, s=10, lw=0.3,
                    edgecolors="white", zorder=2)
    ax.scatter(u[sel, 0], u[sel, 1], s=22, facecolor="none", edgecolor=INK, lw=0.6, zorder=3)
    _clean(ax)
    pad = np.ptp(u, 0) * 0.08
    ax.set_xlim(u[:, 0].min() - pad[0], u[:, 0].max() + pad[0])
    ax.set_ylim(u[:, 1].min() - pad[1], u[:, 1].max() + pad[1])
    ax.text(0.01, 0.01, "○ lasso 1", transform=ax.transAxes, fontsize=F(4.0), color=INK, va="bottom")
    cb = fig.colorbar(sc, cax=cax)
    cb.outline.set_linewidth(0.3)
    cb.ax.tick_params(labelsize=F(3.9), length=1, pad=0.5)
    cb.set_label("SOX2 IF", fontsize=F(4.0), labelpad=1)


# --------------------------------------------------------------------------- e  skills

BENCH_CATS = [("inspect", "inspect\ndata"), ("structure", "call\nstructures"), ("compare", "compare\ngroups"),
              ("associate", "cross-\nmodal"), ("knowhow", "know-\nhow")]
BENCH_MODELS = [("opus", "Opus 5.5", "o"), ("sonnet", "Sonnet 5", "s"), ("haiku", "Haiku 4.5", "^")]


def panel_e(r, x0=108, y0=133):
    panel(x0, y0, "e", "Agent skills: anatomy and benchmark")
    ty = y0 + 9
    box(x0 + 2, ty, 60, 21, fc="#fcefe6", ec=ORANGE, lw=0.5)
    chat_line(x0 + 3.5, ty + 1.2, "skills/compare-groups/", ORANGE, 4.8, mono=True, weight="bold")
    rows = [("SKILL.md", "when to use · steps · checks · how to report"),
            ("scripts/", "compare.py (template using the uchrom API)"),
            ("checks", "n per group · test + effect size · confounders"),
            ("shows", "uchrom.browser.connect() → views as evidence")]
    for k, (a_, b_) in enumerate(rows):
        chat_line(x0 + 3.5, ty + 5.2 + k * 3.8, a_, INK, 4.5, mono=a_.endswith((".md", "/")), weight="bold")
        chat_line(x0 + 16, ty + 5.2 + k * 3.8, b_, GREY, 4.4)

    # e2: mean score (% of grading checks passed) per task category, docs only vs docs + skills.
    # Bars = mean of the three Claude models; markers = each model.
    ms = r["models"]
    keys = [k for k, _ in BENCH_CATS] + ["all"]
    labels = [lab for _, lab in BENCH_CATS] + ["all\ntasks"]

    def score(m, c, k):
        cond = ms[m]["conditions"][c]
        return 100 * (cond["score"] if k == "all" else cond["by_category"][k])

    ax = ax_mm(x0 + 9, ty + 27, 53, 22)
    cols, labs = [LGREY, ORANGE], ["API docs only", "API docs + skills"]
    bw = 0.36
    for j, c in enumerate(("docs", "skills")):
        xx = np.arange(len(keys)) + (j - 0.5) * bw + np.array([0.25 if k == "all" else 0 for k in keys])
        v = [np.mean([score(m, c, k) for m, _, _ in BENCH_MODELS]) for k in keys]
        ax.bar(xx, v, width=bw, color=cols[j], label=labs[j])
        for m, _, mk in BENCH_MODELS:
            ax.scatter(xx, [score(m, c, k) for k in keys], s=3, marker=mk, facecolor="white", edgecolor=INK,
                       lw=0.4, zorder=4, clip_on=False)
    ax.axvline(len(keys) - 1.5 + 0.125, color=LGREY, lw=0.4, ls=(0, (2, 2)))
    ax.set_xticks(np.arange(len(keys)) + np.array([0.25 if k == "all" else 0 for k in keys]), labels,
                  fontsize=F(4.4), linespacing=1.0)
    ax.set_ylabel("checks passed (%)", labelpad=1), ax.set_ylim(0, 100)
    ax.tick_params(axis="x", length=0)
    from matplotlib.lines import Line2D
    hs = [Line2D([], [], ls="none", marker=mk, ms=2.6, mfc="white", mec=INK, mew=0.4,
                 label=f"{name} {ms[m]['conditions']['skills']['n_skill_loaded']}/"
                       f"{ms[m]['conditions']['skills']['n_tasks']}") for m, name, mk in BENCH_MODELS]
    ax.add_artist(ax.legend(handles=hs, frameon=False, fontsize=F(4.1), ncol=3, loc="upper center",
                            bbox_to_anchor=(0.5, -0.29), handlelength=0.6, handletextpad=0.3, columnspacing=0.7,
                            labelcolor=GREY, borderaxespad=0))
    ax.legend(frameon=False, fontsize=F(4.5), ncol=2, loc="upper center", bbox_to_anchor=(0.5, 1.22),
              handles=ax.get_legend_handles_labels()[0][:2], handlelength=0.8, columnspacing=0.8)
    ax.text(0.5, -0.50, "n/40: skill loaded · 1 run per task · judge Sonnet 5",
            transform=ax.transAxes, fontsize=F(4.1), color=GREY, ha="center")


# --------------------------------------------------------------------------- main

PH_RED = "#c0392b"
_TOP = None


def placeholder(x, y, w, h, note):
    """Red dashed frame + 'PLACEHOLDER' tag over a part that is not a real result yet (drawn above everything)."""
    global _TOP
    if _TOP is None:
        _TOP = fig.add_axes(A.get_position(), zorder=100)
        _TOP.set_xlim(A.get_xlim()), _TOP.set_ylim(A.get_ylim()), _TOP.axis("off")
        _TOP.patch.set_alpha(0)
    _TOP.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.2", fc="none",
                                  ec=PH_RED, lw=0.9, ls=(0, (4, 2))))
    _TOP.text(x + w - 1.0, y, f"PLACEHOLDER · {note}", fontsize=F(4.3), color=PH_RED, ha="right", va="center",
              weight="bold", bbox=dict(boxstyle="round,pad=0.25,rounding_size=0.6", fc="white", ec=PH_RED, lw=0.5))


def main():
    d = mock_data()
    panel_a()
    panel_b()
    panel_c(d)
    panel_d(d)
    r = load_results()
    if "agent_bench" in r:
        panel_e(r["agent_bench"])
    else:
        raise SystemExit("results/agent_bench.json missing: run benchmarks/fig6/agent_bench/summarize.py")
    fig.savefig(HERE / "fig6.pdf")
    fig.savefig(HERE / "fig6.png", dpi=300)


if __name__ == "__main__":
    main()
