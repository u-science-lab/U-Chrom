"""Figure 2 — ChromData at real scale: one store, many communities.

Every data panel is drawn from the JSONs in ``results/`` (written by
``benchmarks/fig2/*.py``); nothing is mock data.

  a  data model and the ``x.chromdata.zarr`` 2.2 layout (``panel_a.py``; schematic)
  b  what each format can represent: chromdata.zarr, FOF-CT, AnnData,
     SpatialData, MuData, cooler × twelve chromatin data elements, native /
     linked / by convention / not supported (``b_capabilities.json``, evidence per cell)
  c  storage and full reads vs spots: chromdata.zarr vs the storage schemes
     the community uses for chromatin tracing — FOF-CT (4DN CSV), AnnData
     (spots as obs), SpatialData (points + table) (``b_storage.json``)
  d  left: access by level, backed chromdata.zarr only (get_trace / get_cell /
     get_chrom coordinates only / open); right: one cell, across formats
     (``c_access.json``)
  e  beyond RAM: memory to open and query (backed vs whole table loaded,
     ``c_access.json``) and the streaming population analysis
     (``d_streaming.json``)

Supplementary: ``make_figS_formats.py`` (format versions, flat Parquet,
backed access by layout, per-format get_trace / get_chrom, round trips),
``make_figS_crossmodal.py`` (RNA groups → pseudo-bulk Hi-C),
``make_figS_contacts.py`` (linked vs copied contacts).

    python paper/fig2/make_fig2.py        # -> fig2.pdf / fig2.png
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.legend_handler import HandlerTuple
from matplotlib.lines import Line2D

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
MM = 1 / 25.4
W, H = 170.0, 194.0

mpl.rcParams.update({
    "pdf.fonttype": 42, "font.family": "sans-serif", "font.sans-serif": ["Arial"],
    "font.size": 7, "axes.titlesize": 7, "axes.labelsize": 7,
    "xtick.labelsize": 6, "ytick.labelsize": 6, "legend.fontsize": 6,
    "axes.linewidth": 0.5, "xtick.major.width": 0.5, "ytick.major.width": 0.5,
    "xtick.minor.width": 0.4, "ytick.minor.width": 0.4,
    "xtick.major.size": 2, "ytick.major.size": 2, "xtick.minor.size": 1, "ytick.minor.size": 1,
    "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 1.0,
    "axes.labelpad": 1.5, "xtick.major.pad": 1.5, "ytick.major.pad": 1.5,
})

ORANGE, TEAL, PURPLE, INDIGO = "#e07a3f", "#2a9d8f", "#8e7cc3", "#34568b"
GREY, LGREY, INK, RED = "#8a8f98", "#c9ccd1", "#2b2f36", "#c0392b"
LINDIGO = "#8fa3c7"
SDCOL = "#c2185b"          # SpatialData
FOFCOL = "#8a8f98"         # FOF-CT
ADCOL = PURPLE             # AnnData
PQCOL = "#6b7079"          # Parquet (supplement)

ZARR = "chromdata.zarr 2.2"
BACKED = "chromdata.zarr 2.2 (backed, from disk)"
# panel c: the storage schemes the community uses for chromatin tracing
FORMATS = {
    ZARR: dict(color=INDIGO, ls="-", marker="D", lw=1.3, label="chromdata.zarr 2.2"),
    "FOF-CT / CSV": dict(color=FOFCOL, ls="-", marker="o", label="FOF-CT (4DN CSV)"),
    "AnnData (spots as obs)": dict(color=ADCOL, ls="-", marker="^", label="AnnData (spots as obs)"),
    "SpatialData (points + table)": dict(color=SDCOL, ls="-", marker="v", label="SpatialData (points)"),
}
# supplement: format versions and the flat Parquet reference
SUPP_FORMATS = {
    "Parquet": dict(color=PQCOL, ls="--", marker="s", label="flat Parquet (reference)"),
    "chromdata.zarr 2.2": dict(color=INDIGO, ls="-", marker="D", lw=1.3, label="chromdata.zarr 2.2"),
    "chromdata.zarr 2.1": dict(color=LINDIGO, ls="-", marker="D", mfc="white", label="chromdata.zarr 2.1"),
    "chromdata.zarr 2.0": dict(color=LINDIGO, ls="--", marker="D", mfc="white", label="chromdata.zarr 2.0"),
    "chromdata.zarr 2.0 (float32 coords)": dict(color=LINDIGO, ls="", marker="+", ms=4, mew=0.7,
                                                label="chromdata.zarr 2.0, float32 xyz"),
    "h5cd 2.0": dict(color=GREY, ls="--", marker="o", mfc="white", label="h5cd 2.0 (HDF5)"),
    "h5cd 1.x": dict(color=LGREY, ls=":", marker="o", mfc="white", label="h5cd 1.x"),
}
# panel d (left): backed operations of chromdata.zarr; get_chrom with all tracks is in the supplement
LEVELS = [("trace", "get_trace", ORANGE, "-"), ("cell", "get_cell", INDIGO, "-"),
          ("chrom", "get_chrom", TEAL, "-"), ("chrom_coords", "get_chrom,\ncoords only", TEAL, "-"),
          ("open", "open", INK, "-")]
D_LEVELS = ["open", "chrom_coords", "cell", "trace"]
BASELINES = [  # c_access series, short label, colour, line style
    ("FOF-CT (load + subset)", "FOF-CT", FOFCOL, "-"),
    ("AnnData (load + subset)", "AnnData", ADCOL, "-"),
    ("SpatialData (lazy open + filter)", "SpatialData", SDCOL, "-"),
]
# panel b: capability marks
MARK_ROWS = {"chromdata.zarr": "chromdata.zarr", "FOF-CT (4DN)": "FOF-CT (4DN)", "AnnData": "AnnData",
             "SpatialData": "SpatialData", "MuData": "MuData", "cooler (.cool / .scool)": "cooler (.cool, .scool)"}
MARK_COLS = {"coords": "spot coordinates (x, y, z)", "hierarchy": "cell › trace › spot", "spot_signals": "per-spot signals",
             "bin_signals": "per-locus signals", "cells": "cell table", "cell_emb": "cell embeddings",
             "cell_pos": "cell spatial position", "contacts": "contact maps",
             "intervals": "intervals (TADs, loops)", "points": "RNA spots (points)",
             "provenance": "results + provenance", "partial": "partial reads (cell, chrom)"}


# --------------------------------------------------------------------------- data

def _load(name: str):
    p = RESULTS / f"{name}.json"
    if not p.exists():
        raise SystemExit(f"{p} missing — run benchmarks/fig2/ (see benchmarks/fig2/README.md)")
    return json.loads(p.read_text())


def _arr(pts, f):
    return np.array([f(p) for p in pts])


def storage(labels=None) -> dict:
    b = _load("b_storage")
    out = {}
    for label, s in b["series"].items():
        if labels is not None and label not in labels:
            continue
        pts = [p for p in s["points"] if p.get("size_mb", {}).get("median") is not None]
        out[label] = {"n": _arr(pts, lambda p: float(p["n_spots"])),
                      "size_mb": _arr(pts, lambda p: p["size_mb"]["median"]),
                      "read_s": _arr(pts, lambda p: p["read_s"]["median"]),
                      "peak_mb": _arr(pts, lambda p: p["read_peak_rss_mb"]["median"]
                                      - p["read_baseline_rss_mb"]["median"]),
                      "replicated": _arr(pts, lambda p: bool(p["replicated"]))}
    return out


def access() -> dict:
    c = _load("c_access")
    s = c["series"]
    pts = s[BACKED]["points"]
    out = {"n": _arr(pts, lambda p: float(p["n_spots"])), "rep": _arr(pts, lambda p: bool(p["replicated"]))}
    for key, *_ in LEVELS:
        if key == "open":
            out[key] = _arr(pts, lambda p: p["open_s"])
        else:
            out[key] = _arr(pts, lambda p: p[key]["latency_s"]["median"])
            out[key + "_q"] = (_arr(pts, lambda p: p[key]["latency_s"]["q1"]),
                               _arr(pts, lambda p: p[key]["latency_s"]["q3"]))
    out["mem"] = _arr(pts, lambda p: (p.get("peak_rss_trace_cell_mb") or p["rss_after_open_mb"])
                      - p["baseline_rss_mb"])
    base, mem = {}, {}
    for series, *_ in BASELINES:
        if series not in s:
            continue
        bp = s[series]["points"]
        n = _arr(bp, lambda p: float(p["n_spots"]))
        # time to get one trace / cell / chromosome from the file: load (or lazy open) + the query
        base[series] = {"n": n, **{k: _arr(bp, lambda p, k=k: p["open_s"] + p[k]["latency_s"]["median"])
                                   for k in ("trace", "cell", "chrom")}}
        mem[series] = (n, _arr(bp, lambda p: (p.get("peak_rss_trace_cell_mb") or p["rss_after_open_mb"])
                                - p["baseline_rss_mb"]))
    out["base"], out["base_mem"] = base, mem
    return out


# --------------------------------------------------------------------------- helpers

def label(fig, x, y, s):
    fig.text(x / W, 1 - y / H, s, fontsize=10, fontweight="bold", va="top")


def title(fig, x, y, s, sub=None):
    fig.text(x / W, 1 - y / H, s, fontsize=8.5, fontweight="bold", va="top")
    if sub:
        fig.text(x / W, 1 - (y + 4.2) / H, sub, fontsize=6, color=GREY, va="top")


def ax_at(fig, x, y, w, h):
    return fig.add_axes([x / W, 1 - (y + h) / H, w / W, h / H])


def loglog(ax):
    ax.set_xscale("log")
    ax.set_yscale("log")


def decades(ax, lo, hi, axis="x"):
    ticks = [10.0 ** k for k in range(int(np.floor(np.log10(lo))), int(np.ceil(np.log10(hi))) + 1)]
    (ax.set_xticks if axis == "x" else ax.set_yticks)(ticks)
    loc = mpl.ticker.LogLocator(base=10, subs=np.arange(2, 10) * 0.1, numticks=50)
    (ax.xaxis if axis == "x" else ax.yaxis).set_minor_locator(loc)
    (ax.xaxis if axis == "x" else ax.yaxis).set_minor_formatter(mpl.ticker.NullFormatter())


def points(ax, n, y, color, ls="-", rep=None, lw=1.1, ms=2.2, marker="o", z=3, **kw):
    rep = np.zeros(len(n), bool) if rep is None else rep
    ax.plot(n, y, color=color, ls=ls, lw=lw, zorder=z, **kw)
    ax.plot(n[~rep], y[~rep], ls="", marker=marker, ms=ms, color=color, zorder=z + 1)
    if rep.any():
        ax.plot(n[rep], y[rep], ls="", marker=marker, ms=ms + 1.0, mfc="white", mec=color, mew=0.8, zorder=z + 1)


def legend(fig, handles, labels, x, y, ncol=1, **kw):
    opts = dict(frameon=False, handlelength=2.0, handletextpad=0.4, columnspacing=0.9, labelspacing=0.3,
                borderaxespad=0, borderpad=0)
    opts.update(kw)
    return fig.legend(handles, labels, loc="upper left", bbox_to_anchor=(x / W, 1 - y / H), ncol=ncol, **opts)


# --------------------------------------------------------------------------- panels

def direct_labels(ax, items, min_gap_mm=2.5, dx_pts=3.0, size=6):
    """Label line ends directly: ``items`` = [(x_end, y_end, text, colour)].  Labels sit to the right of
    each line end and are spread in log-y so that neighbours are at least ``min_gap_mm`` apart."""
    import matplotlib.transforms as mt

    fig = ax.figure
    h_mm = ax.get_position().height * fig.get_figheight() * 25.4
    lo, hi = np.log10(ax.get_ylim())
    gap = min_gap_mm / h_mm * (hi - lo)
    items = sorted(items, key=lambda t: t[1])
    pos = [np.log10(t[1]) for t in items]
    hts = [1 + 0.9 * t[2].count("\n") for t in items]      # label height in lines
    for _ in range(500):
        moved = False
        for i in range(1, len(pos)):
            need = gap * (hts[i] + hts[i - 1]) / 2
            d = pos[i] - pos[i - 1]
            if d < need - 1e-9:
                pos[i - 1] -= (need - d) / 2
                pos[i] += (need - d) / 2
                moved = True
        if not moved:
            break
    off = mt.offset_copy(ax.transData, fig=fig, x=dx_pts, y=0, units="points")
    for (xe, _, text, col), p in zip(items, pos):
        ax.text(xe, 10 ** p, text, transform=off, fontsize=size, color=col, va="center", ha="left",
                clip_on=False, linespacing=1.0)


def panel_b(fig, x0, y0):
    """What each format can represent (b_capabilities.json)."""
    label(fig, x0, y0, "b")
    title(fig, x0 + 5, y0 + 0.4, "What each format can represent", "evidence for every cell: Supplementary Table S1")
    cap = _load("b_capabilities")
    rows, cols = [r for r in MARK_ROWS if r in cap["cells"]], [c for c in MARK_COLS if c in cap["cols"]]
    cw, rh = 4.7, 3.6
    gx, gy = x0 + 24.5, y0 + 26.5
    ax = ax_at(fig, gx, gy, cw * len(cols), rh * len(rows))
    ax.set_xlim(0, len(cols)); ax.set_ylim(len(rows), 0)
    ax.axhspan(0, 1, color="#e7ecf4", lw=0, zorder=0)           # our row
    for i, r in enumerate(rows):
        for j, c in enumerate(cols):
            v = cap["cells"][r][c]["value"]
            if v == "native":
                ax.plot(j + 0.5, i + 0.5, marker="o", ms=4.4, color=INDIGO, mec=INDIGO, mew=0.6)
            elif v == "linked":                              # external file, queried through the index
                ax.plot(j + 0.5, i + 0.5, marker="o", ms=4.4, mfc="white", mec=TEAL, mew=0.8, ls="")
                ax.plot(j + 0.5, i + 0.5, marker="o", ms=1.9, color=TEAL, mec=TEAL, ls="")
            elif v == "convention":
                ax.plot(j + 0.5, i + 0.5, marker="o", ms=4.4, mfc="white", mec=INDIGO, mew=0.8)
            else:
                ax.plot([j + 0.36, j + 0.64], [i + 0.5, i + 0.5], color=GREY, lw=0.8, solid_capstyle="butt")
    # column headers: 45°, anchored bottom-left just above each column, reading up-right
    ax.set_xticks([])
    for j, c in enumerate(cols):
        ax.annotate(MARK_COLS[c], (j + 0.5, 0), xytext=(-1.2, 2.0), textcoords="offset points",
                    rotation=45, ha="left", va="bottom", rotation_mode="anchor", fontsize=6,
                    annotation_clip=False)
    ax.tick_params(length=0, pad=1.5)
    ax.set_yticks(np.arange(len(rows)) + 0.5, [MARK_ROWS[r] for r in rows])
    ax.get_yticklabels()[0].set_fontweight("bold")
    for sp in ax.spines.values():
        sp.set_visible(False)
    hs = [Line2D([], [], marker="o", ls="", ms=4.2, color=INDIGO, mec=INDIGO, mew=0.6),
          (Line2D([], [], marker="o", ls="", ms=4.2, mfc="white", mec=TEAL, mew=0.8),
           Line2D([], [], marker="o", ls="", ms=1.8, color=TEAL, mec=TEAL)),
          Line2D([], [], marker="o", ls="", ms=4.2, mfc="white", mec=INDIGO, mew=0.8),
          Line2D([], [], color=GREY, lw=0.8)]
    legend(fig, hs, ["native", "linked", "by convention", "not supported"],
           x0 + 3, gy + rh * len(rows) + 1.6, ncol=4,
           handlelength=1.0, handletextpad=0.4, columnspacing=1.2,
           handler_map={tuple: HandlerTuple(ndivide=1, pad=0)})


def panel_c(fig, x0, y0):
    label(fig, x0, y0, "c")
    title(fig, x0 + 5, y0 + 0.4, "Storage and full reads")
    fig.text((x0 + 5) / W, 1 - (y0 + 4.6) / H, "Takei 2025 cerebellum, 62 spot tracks", fontsize=6, color=GREY,
             va="top")
    st = storage(list(FORMATS))
    axes = []
    for j, (key, ylab) in enumerate([("size_mb", "file size (MB)"), ("read_s", "full read into memory (s)")]):
        ax = ax_at(fig, x0 + 9 + j * 31, y0 + 11, 21.5, 27)
        for f in reversed(list(FORMATS)):
            if f not in st:
                continue
            sty = {k: v for k, v in FORMATS[f].items() if k != "label"}
            s = st[f]
            ax.plot(s["n"], s[key], **{"ms": 2.3, **sty}, zorder=4 if f == ZARR else 3)
        loglog(ax)
        ax.set_xlabel("spots"); ax.set_ylabel(ylab)
        decades(ax, 1e4, 1e7)
        axes.append(ax)
    hs = [Line2D([], [], **{"ms": 2.6, **{k: v for k, v in FORMATS[f].items() if k != "label"}}) for f in FORMATS]
    legend(fig, hs, [FORMATS[f]["label"] for f in FORMATS], x0 + 3, y0 + 45.5, ncol=2, handlelength=2.2)
    return axes


def panel_d(fig, x0, y0):
    label(fig, x0, y0, "d")
    title(fig, x0 + 5, y0 + 0.4, "Access from disk")
    a = access()
    lv = {k: (lab, col) for k, lab, col, _ in LEVELS}
    aw, ah = 27.0, 29.0
    # left: our store only, by level
    axl = ax_at(fig, x0 + 10, y0 + 13, aw, ah)
    fig.text((x0 + 5) / W, 1 - (y0 + 6.0) / H, "Access by level", fontsize=6.5, color=INK, va="top",
             fontweight="bold")
    fig.text((x0 + 5) / W, 1 - (y0 + 9.0) / H, "chromdata.zarr, backed", fontsize=6, color=GREY, va="top")
    dash = {"chrom_coords": (0, (2.5, 1.2))}
    for key in D_LEVELS:
        lab, col = lv[key]
        if key + "_q" in a:
            q1, q3 = a[key + "_q"]
            axl.fill_between(a["n"], q1, q3, color=col, alpha=0.12, lw=0, zorder=1)
        points(axl, a["n"], a[key], col, ls=dash.get(key, "-"), rep=a["rep"], lw=1.2)
    loglog(axl)
    axl.set_xlabel("spots"); axl.set_ylabel("time (s)")
    decades(axl, 1e4, 1e8)
    axl.set_xticks([1e4, 1e6, 1e8])
    axl.set_ylim(4e-4, 1)
    decades(axl, 1e-3, 1, axis="y")
    direct_labels(axl, [(a["n"][-1], a[k][-1], lv[k][0], lv[k][1]) for k in D_LEVELS], min_gap_mm=2.4)
    # right: one cell's data, across formats
    axr = ax_at(fig, x0 + 60, y0 + 13, aw, ah)
    fig.text((x0 + 55) / W, 1 - (y0 + 6.0) / H, "One cell, across formats", fontsize=6.5, color=INK,
             va="top", fontweight="bold")
    fig.text((x0 + 55) / W, 1 - (y0 + 9.0) / H, "open or load the file, then get one cell", fontsize=6,
             color=GREY, va="top")
    items = []
    for series, lab, col, _ in BASELINES:
        if series in a["base"]:
            b = a["base"][series]
            points(axr, b["n"], b["cell"], col, lw=1.1)
            items.append((b["n"][-1], b["cell"][-1], lab, col))
    ours = a["open"] + a["cell"]
    points(axr, a["n"], ours, INDIGO, rep=a["rep"], lw=1.3)
    items.append((a["n"][-1], ours[-1], "chromdata\n.zarr", INDIGO))
    loglog(axr)
    axr.set_xlabel("spots"); axr.set_ylabel("time (s)")
    decades(axr, 1e4, 1e8)
    axr.set_xticks([1e4, 1e6, 1e8])
    axr.set_ylim(1e-2, 30)
    decades(axr, 1e-2, 30, axis="y")
    direct_labels(axr, items, min_gap_mm=2.4)
    return axl, axr


def panel_e(fig, x0, y0):
    label(fig, x0, y0, "e")
    title(fig, x0 + 5, y0 + 0.4, "Beyond RAM")
    a = access()
    ah = 29.0
    # left: memory to open the data and run the trace / cell queries
    ax = ax_at(fig, x0 + 10, y0 + 13, 20, ah)
    fig.text((x0 + 5) / W, 1 - (y0 + 6.0) / H, "Open + query", fontsize=6.5, color=INK, va="top",
             fontweight="bold")
    fig.text((x0 + 5) / W, 1 - (y0 + 9.0) / H, "formats as in d", fontsize=6, color=GREY, va="top")
    for series, _, col, _ in BASELINES:
        if series in a["base_mem"]:
            n, m = a["base_mem"][series]
            points(ax, n, m / 1024, col, lw=1.0, ms=2.0, z=2)
    points(ax, a["n"], a["mem"] / 1024, INDIGO, rep=a["rep"], lw=1.2)
    loglog(ax)
    ax.set_xlabel("spots"); ax.set_ylabel("memory used (GB)")
    decades(ax, 1e4, 1e8)
    ax.set_xticks([1e4, 1e6, 1e8])
    ax.text(0.04, 0.99, "load all", transform=ax.transAxes, fontsize=6, color=GREY, va="top")
    ax.text(0.97, 0.04, "backed", transform=ax.transAxes, fontsize=6, color=INDIGO, ha="right", va="bottom")
    # right: streaming population analysis (d_streaming.json)
    dd = _load("d_streaming")
    pts = dd["points"]
    ax2 = ax_at(fig, x0 + 43, y0 + 13, 22, ah)
    fig.text((x0 + 36) / W, 1 - (y0 + 6.0) / H, "Population analysis", fontsize=6.5, color=INK, va="top",
             fontweight="bold")
    fig.text((x0 + 36) / W, 1 - (y0 + 9.0) / H, f"median distance map, {dd['chrom']}", fontsize=6,
             color=GREY, va="top")
    tr = _arr(pts, lambda p: float(p["n_traces"]))
    rep = _arr(pts, lambda p: bool(p.get("replicated")))
    st = _arr(pts, lambda p: (p["streaming"]["peak_rss_mb"]["median"] - p["streaming"]["baseline_rss_mb"]["median"]))
    la = [p for p in pts if "load_all" in p]
    lt = _arr(la, lambda p: float(p["n_traces"]))
    lm = _arr(la, lambda p: p["load_all"]["peak_rss_mb"]["median"] - p["load_all"]["baseline_rss_mb"]["median"])
    points(ax2, lt, lm / 1024, GREY, lw=1.1)
    points(ax2, tr, st / 1024, INDIGO, rep=rep, lw=1.2)
    budget = dd["budget_mb"] / 1024
    ax2.axhline(budget, color=INDIGO, ls=":", lw=0.8)
    loglog(ax2)
    ax2.set_xlabel("traces"); ax2.set_ylabel("memory used (GB)")
    decades(ax2, tr.min(), tr.max())
    ax2.set_xticks([1e2, 1e4, 1e6])
    lo, hi = ax2.get_ylim()
    ax2.set_ylim(lo, max(hi, budget * 45))
    ax2.text(0.03, budget * 0.85, f"{budget:g} GB\nbudget", fontsize=6, color=INDIGO, va="top", ha="left",
             linespacing=1.0,
             transform=ax2.get_yaxis_transform())
    ax2.text(lt[-1] * 0.7, lm[-1] / 1024 * 1.1, "load all", fontsize=6, color=GREY, ha="right", va="bottom")
    ax2.text(tr[-1], st[-1] / 1024 * 0.55, "stream", fontsize=6, color=INDIGO, ha="right", va="top")
    if any("load_all" not in p for p in pts):
        ax2.text(0.04, 0.99, "1e8 (○): load all\nexceeds RAM", fontsize=6, color=GREY, ha="left", va="top",
                 transform=ax2.transAxes, linespacing=1.0)
    return ax, ax2


def make_figure():
    import panel_a

    fig = plt.figure(figsize=(W * MM, H * MM))
    pa_h = panel_a.H
    panel_a.draw(panel_a.C(fig, rect=(0, 1 - pa_h / H, panel_a.W / W, pa_h / H)))
    y2 = pa_h + 2.0
    panel_b(fig, 1, y2)
    panel_c(fig, 100, y2)
    y3 = y2 + 52.5
    panel_d(fig, 1, y3)
    panel_e(fig, 102, y3)
    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"fig2.{ext}", dpi=300)
    return HERE / "fig2.pdf"


def main() -> None:
    print(make_figure())


if __name__ == "__main__":
    main()
