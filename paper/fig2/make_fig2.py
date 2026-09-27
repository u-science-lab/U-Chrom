"""Figure 2 — ChromData at real scale: one store, many communities.

Every panel is drawn from the benchmark JSONs in ``results/`` (written by
``benchmarks/fig2/*.py``); nothing is mock data.

  a  data model and the ``x.chromdata.zarr`` 2.2 layout (``panel_a.py``; schematic)
  b  interoperability with community formats: what survives export → import
     (``f_roundtrip.json``)
  c  storage and full reads vs spots: chromdata.zarr vs the storage schemes
     the community uses for chromatin tracing — FOF-CT (4DN CSV), AnnData
     (spots as obs), SpatialData (points + table) (``b_storage.json``)
  d  access by level: latency of backed chromdata.zarr (get_trace / get_cell /
     get_chrom / get_chrom coordinates only / open) vs the in-memory route
     "load, then subset" (FOF-CT, AnnData) and SpatialData's lazy filter
     (``c_access.json``)
  e  beyond RAM: memory to open and query (backed vs whole table loaded,
     ``c_access.json``) and the streaming population analysis
     (``d_streaming.json``)
  f  groups from one modality, structure from another: RNA Leiden clusters
     of scHiCAR MOp cells → pseudo-bulk Hi-C from the linked per-cell .scool
     (``f_crossmodal.json``, ``e_query.json``, ``e_contacts.json``)

Flat Parquet (the storage engine under chromdata.zarr) and the ChromData
format versions are in ``make_figS_formats.py``; linked vs copied contacts
in ``make_figS_contacts.py``.

    python paper/fig2/make_fig2.py        # -> fig2.pdf / fig2.png
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
MM = 1 / 25.4
W, H = 170.0, 222.0

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
# panel d: backed operations
LEVELS = [("trace", "get_trace", ORANGE, "-"), ("cell", "get_cell", INDIGO, "-"),
          ("chrom", "get_chrom", TEAL, "-"), ("chrom_coords", "get_chrom, coords only", TEAL, (0, (2.5, 1.2))),
          ("open", "open store", INK, "-")]
BASELINES = [  # c_access series, legend label, colour, line style
    ("FOF-CT (load + subset)", "FOF-CT: load + query", FOFCOL, "--"),
    ("AnnData (load + subset)", "AnnData: load + query", ADCOL, "--"),
    ("SpatialData (lazy open + filter)", "SpatialData: lazy filter", SDCOL, (0, (1.2, 1.2))),
]
STATUS_VAL = {"preserved": 1.0, "partial": 0.5, "lost": -1.0, "na": 0.0, "untested": 0.0}
ROLE_COL = {"neuronal": INDIGO, "oligodendrocyte": ORANGE, "astrocyte": TEAL}


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
        base[series] = (n, _arr(bp, lambda p: p["open_s"] + p["trace"]["latency_s"]["median"]))
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

def panel_b(fig, x0, y0):
    """Interoperability dot matrix (f_roundtrip.json)."""
    label(fig, x0, y0, "b")
    title(fig, x0 + 5, y0 + 0.4, "Interoperability with\ncommunity formats")
    fig.text((x0 + 5) / W, 1 - (y0 + 8.2) / H, "what survives export → import", fontsize=6, color=GREY, va="top")
    f = _load("f_roundtrip")
    rows, cols = list(f["rows"]), list(f["cols"])
    v = np.array([[STATUS_VAL[f["cells"][r][c]["status"]] for c in cols] for r in rows])
    direction = {"PDB": "export only", ".3dg": "import only"}
    rh = 4.2
    ax = ax_at(fig, x0 + 19.5, y0 + 23, 24, rh * len(rows))
    for i in range(v.shape[0]):
        for j in range(v.shape[1]):
            val = float(v[i, j])
            if val < 0:
                ax.plot(j + 0.5, i + 0.5, marker="x", ms=4, color=RED, mew=0.8)
                continue
            fill = {1.0: "full", 0.5: "left", 0.0: "none"}[val]
            col = INDIGO if val else LGREY
            ax.plot(j + 0.5, i + 0.5, marker="o", ms=5.2, fillstyle=fill, color=col, mec=col, mew=0.6,
                    markerfacecoloralt="white")
    ax.set_xlim(0, v.shape[1]); ax.set_ylim(v.shape[0], 0)
    ax.set_xticks(np.arange(v.shape[1]) + 0.5, cols, rotation=50, ha="left", rotation_mode="anchor")
    ax.xaxis.tick_top(); ax.tick_params(length=0, pad=1.5)
    ax.set_yticks(np.arange(v.shape[0]) + 0.5, rows)
    for s in ax.spines.values():
        s.set_visible(False)
    for i, r in enumerate(rows):
        if r in direction:
            ax.annotate(direction[r], (0, i + 0.5), xytext=(-2.5, -5.6), textcoords="offset points", ha="right",
                        va="center", fontsize=6, color=GREY, annotation_clip=False)
    hs = [Line2D([], [], marker="o", ls="", ms=4.6, fillstyle=fs, color=c, mec=c, mew=0.6,
                 markerfacecoloralt="white") for fs, c in (("full", INDIGO), ("left", INDIGO), ("none", LGREY))]
    labs = ["preserved", "partial, or not representable\nin that format", "not applicable"]
    if (v < 0).any():
        hs.append(Line2D([], [], marker="x", ls="", ms=4, color=RED, mew=0.8))
        labs.append("lost")
    legend(fig, hs, labs, x0 + 2.5, y0 + 23 + rh * len(rows) + 2.6, handlelength=1.0, labelspacing=0.35)


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
    title(fig, x0 + 5, y0 + 0.4, "Access by level")
    fig.text((x0 + 5) / W, 1 - (y0 + 4.6) / H, "one query, from disk", fontsize=6, color=GREY, va="top")
    a = access()
    ax = ax_at(fig, x0 + 10, y0 + 11, 44, 27)
    for series, _, col, ls in BASELINES:
        if series in a["base"]:
            n, t = a["base"][series]
            points(ax, n, t, col, ls=ls, lw=1.0, ms=2.0, z=2)
    for key, _, col, ls in LEVELS:
        if key + "_q" in a:
            q1, q3 = a[key + "_q"]
            ax.fill_between(a["n"], q1, q3, color=col, alpha=0.12, lw=0, zorder=1)
        points(ax, a["n"], a[key], col, ls=ls, rep=a["rep"], lw=0.9 if key == "chrom_coords" else 1.2)
    loglog(ax)
    ax.set_xlabel("spots"); ax.set_ylabel("time per query (s)")
    decades(ax, 1e4, 1e8)
    lo = min(np.nanmin(a[k]) for k, *_ in LEVELS)
    hi = max([np.nanmax(t) for _, t in a["base"].values()] + [np.nanmax(a[k]) for k, *_ in LEVELS])
    ax.set_ylim(lo / 2, hi * 2)
    decades(ax, lo / 2, hi * 2, axis="y")
    h1 = [Line2D([], [], color=c, ls=ls, lw=0.9 if k == "chrom_coords" else 1.2) for k, _, c, ls in LEVELS]
    l1 = [lab for _, lab, _, _ in LEVELS]
    fig.text((x0 + 3.5) / W, 1 - (y0 + 46.0) / H, "chromdata.zarr 2.2, backed:", fontsize=6, color=INK,
             fontweight="bold", va="top")
    h1.append(Line2D([], [], ls="", marker="o", ms=3.2, mfc="white", mec=INK, mew=0.8))
    l1.append("replicated cells")
    legend(fig, h1, l1, x0 + 3, y0 + 48.8, ncol=2, handlelength=1.5, columnspacing=0.7)
    h2 = [Line2D([], [], color=c, ls=ls, lw=1.0) for _, _, c, ls in BASELINES]
    l2 = [lab for _, lab, _, _ in BASELINES]
    legend(fig, h2, l2, x0 + 3, y0 + 58.4, ncol=2, handlelength=1.5, columnspacing=0.7)
    return ax


def panel_e(fig, x0, y0):
    label(fig, x0, y0, "e")
    title(fig, x0 + 5, y0 + 0.4, "Beyond RAM")
    a = access()
    # left: memory to open the data and run the trace / cell queries
    ax = ax_at(fig, x0 + 10, y0 + 13, 21, 27)
    fig.text((x0 + 7) / W, 1 - (y0 + 6.2) / H, "open + query", fontsize=6.5, color=INK, va="top",
             fontweight="bold")
    for series, _, col, ls in BASELINES:
        if series in a["base_mem"]:
            n, m = a["base_mem"][series]
            points(ax, n, m / 1024, col, ls=ls, lw=1.0, ms=2.0, z=2)
    points(ax, a["n"], a["mem"] / 1024, INDIGO, rep=a["rep"], lw=1.2)
    loglog(ax)
    ax.set_xlabel("spots"); ax.set_ylabel("memory used (GB)")
    decades(ax, 1e4, 1e8)
    ax.set_xticks([1e4, 1e6, 1e8])
    ax.text(0.03, 0.99, "load all", transform=ax.transAxes, fontsize=6, color=GREY, va="top")
    ax.text(0.97, 0.05, "backed", transform=ax.transAxes, fontsize=6, color=INDIGO, ha="right", va="bottom")
    # right: streaming population analysis (d_streaming.json)
    dd = _load("d_streaming")
    pts = dd["points"]
    ax2 = ax_at(fig, x0 + 40, y0 + 13, 24, 27)
    fig.text((x0 + 37) / W, 1 - (y0 + 6.2) / H, "population analysis", fontsize=6.5, color=INK, va="top",
             fontweight="bold")
    fig.text((x0 + 37) / W, 1 - (y0 + 9.2) / H, f"exact median distance map, {dd['chrom']}", fontsize=6,
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
    ax2.text(1.02, budget, f"{budget:g} GB\nbudget", fontsize=6, color=INDIGO, va="center",
             transform=ax2.get_yaxis_transform(), linespacing=1.0)
    for p in pts:
        if "load_all" not in p:
            x = float(p["n_traces"])
            ax2.text(tr.min() * 0.8, budget * 22, "1e8 spots (○): load all\ndoes not fit in RAM", fontsize=6,
                     color=GREY, ha="left", va="center", linespacing=1.0)
    # identity inset
    sc = dd.get("scatter")
    if sc:
        ins = ax_at(fig, x0 + 54.5, y0 + 30.0, 9.0, 6.0)
        a1, b1 = np.asarray(sc["load_all"]), np.asarray(sc["streaming"])
        ins.scatter(a1, b1, s=0.6, color=INDIGO, lw=0, rasterized=True)
        lim = [min(a1.min(), b1.min()), max(a1.max(), b1.max())]
        ins.plot(lim, lim, color=LGREY, lw=0.5, zorder=0)
        ins.set_xticks([]); ins.set_yticks([])
        for sp in ins.spines.values():
            sp.set_linewidth(0.4)
        ins.text(0.02, 0.98, "identical", transform=ins.transAxes, fontsize=6, color=GREY, va="top")
        ins.set_xlabel("in memory", fontsize=6, labelpad=0.5)
        ins.set_ylabel("stream", fontsize=6, labelpad=0.5)
    h = [Line2D([], [], color=INDIGO, marker="o", ms=2.2, lw=1.2), Line2D([], [], color=GREY, marker="o", ms=2.2,
                                                                          lw=1.1)]
    labs = ["chromdata.zarr: backed (left), streaming iter_traces (right)",
            "load the whole table (left: formats as in d)"]
    legend(fig, h, labs, x0 + 3, y0 + 48.0, handlelength=1.5)


def panel_f(fig, x0, y0):
    from matplotlib.colors import LinearSegmentedColormap, LogNorm

    label(fig, x0, y0, "f")
    title(fig, x0 + 5, y0 + 0.4, "Groups from one modality, structure from another")
    fig.text((x0 + 5) / W, 1 - (y0 + 4.6) / H, "scHiCAR mouse MOp (5,313 cells): RNA clusters → pseudo-bulk Hi-C "
             "from the linked .scool", fontsize=6, color=GREY, va="top")
    fx = _load("f_crossmodal")
    q = _load("e_query")["identity"]
    e = _load("e_contacts")["aggregation"]["points"]
    groups = fx["groups"]
    roles = ["neuronal", "oligodendrocyte", "astrocyte"]
    names = {"neuronal": "neurons", "oligodendrocyte": "oligodendrocytes", "astrocyte": "astrocytes"}
    # UMAP of the RNA embedding: Leiden clusters (grey), the three chosen ones coloured
    ax = ax_at(fig, x0 + 2, y0 + 12, 22, 22)
    um = fx["umap"]
    xs, ys, cl = np.asarray(um["x"]), np.asarray(um["y"]), np.asarray(um["cluster"])
    ax.scatter(xs, ys, s=0.4, color="#d9dce1", lw=0, rasterized=True)
    for r in roles:
        m = cl == groups[r]["cluster"]
        ax.scatter(xs[m], ys[m], s=0.5, color=ROLE_COL[r], lw=0, rasterized=True)
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.set_xlabel("RNA UMAP", labelpad=1)
    ax.set_title(f"{fx['clustering']['n_clusters']} Leiden clusters\non the RNA PCA", fontsize=6, color=GREY, pad=1.5,
                 linespacing=1.0)
    hs, labs = [], []
    for r in roles:
        g = groups[r]
        hs.append(Line2D([], [], ls="", marker="o", ms=3.0, color=ROLE_COL[r]))
        labs.append(f"cl. {g['cluster']}: {names[r]} (n = {g['n_cells']:,})")
    legend(fig, hs, labs, x0 + 0.5, y0 + 38.2, handlelength=0.7, handletextpad=0.3, labelspacing=0.2)
    # two pseudo-bulk maps of the same window (each normalised to its cis total)
    cmap = LinearSegmentedColormap.from_list("wt", ["#ffffff", "#b9d9f0", INDIGO, "#101d33"])
    pair = ["neuronal", "oligodendrocyte"]
    mats = [np.asarray(groups[r]["window"]["matrix"], float) / groups[r]["total_cis_contacts"] * 1e6 for r in pair]
    pos = np.concatenate([m[m > 0] for m in mats])
    norm = LogNorm(vmin=np.percentile(pos, 5), vmax=np.percentile(pos, 99.5))
    w = groups[pair[0]]["window"]
    for k, (r, mat) in enumerate(zip(pair, mats)):
        mx = ax_at(fig, x0 + 29 + k * 21, y0 + 12, 19.5, 19.5)
        mx.imshow(mat, cmap=cmap, norm=norm, interpolation="nearest")
        mx.set_xticks([]); mx.set_yticks([])
        for sp in mx.spines.values():
            sp.set_linewidth(0.6)
            sp.set_color(ROLE_COL[r])
        mx.set_title(f"{names[r]} (cl. {groups[r]['cluster']})", fontsize=6, color=ROLE_COL[r], pad=1.5)
    cax = ax_at(fig, x0 + 70.5, y0 + 13, 1.3, 17.5)
    cb = fig.colorbar(mpl.cm.ScalarMappable(norm=norm, cmap=cmap), cax=cax)
    cb.outline.set_linewidth(0.4)
    cb.ax.tick_params(labelsize=6, width=0.4, length=1.5, pad=1)
    fig.text((x0 + 78.5) / W, 1 - (y0 + 13) / H, "contacts\nper million\ncis contacts", fontsize=6, color=GREY,
             va="top", linespacing=1.0)
    fig.text((x0 + 29) / W, 1 - (y0 + 32.4) / H,
             f"{w['chrom']}:{w['start'] // 10**6}–{w['end'] // 10**6} Mb, 1 Mb bins, pseudo-bulk of each cluster",
             fontsize=6, color=GREY, va="top")
    # correctness (e_query.json)
    fig.text((x0 + 29) / W, 1 - (y0 + 35.6) / H,
             f"Pseudo-bulk from the per-cell .scool equals the published per-type .cool\n"
             f"for {q['n_identical']}/{q['n_types']} cell types (max |Δ| = {q['max_abs_diff']:g} over "
             f"{q['n_pixels'] / 1e6:.1f} M pixels)", fontsize=6, color=INK, va="top", linespacing=1.1)
    # P(s) per group
    px = ax_at(fig, x0 + 8, y0 + 45.5, 23, 12.5)
    for r in roles:
        g = groups[r]
        s, p = np.asarray(g["ps_s_mb"], float), np.asarray(g["ps"], float)
        px.plot(s, p, color=ROLE_COL[r], lw=1.0)
    loglog(px)
    px.set_xlabel("distance s (Mb)"); px.set_ylabel("P(s)")
    px.set_xticks([1, 10]); px.set_xticklabels(["1", "10"])
    px.yaxis.set_minor_formatter(mpl.ticker.NullFormatter())
    fig.text((x0 + 33) / W, 1 - (y0 + 45.5) / H, "slope, 2–30 Mb", fontsize=6, color=GREY, va="top")
    for i, r in enumerate(roles):
        fig.text((x0 + 33) / W, 1 - (y0 + 48.7 + 3.0 * i) / H, f"{groups[r]['ps_slope']:.2f}  {names[r]}",
                 fontsize=6, color=ROLE_COL[r], va="top")
    # pseudo-bulk time vs cells (e_contacts.json)
    tx = ax_at(fig, x0 + 66, y0 + 45.5, 20, 12.5)
    c = np.array([p["n_cells"] for p in e])
    cold = np.array([p["cold_s"]["median"] for p in e])
    cached = np.array([p["cached_s"]["median"] for p in e])
    tx.plot(c, cold, color=TEAL, marker="o", ms=2.0, lw=1.0)
    tx.plot(c, cached, color=TEAL, ls="--", marker="o", ms=2.0, mfc="white", lw=1.0)
    loglog(tx)
    tx.set_xlabel("cells aggregated"); tx.set_ylabel("time (s)")
    decades(tx, c.min(), c.max())
    tx.set_yticks([1e-4, 1e-2, 1e0])
    tx.yaxis.set_minor_formatter(mpl.ticker.NullFormatter())
    tx.set_ylim(cached.min() / 3, cold.max() * 6)
    tx.text(c[-1], cold[-1] * 2.0, "first query", fontsize=6, color=TEAL, va="bottom", ha="right")
    tx.text(c[0], cached[0] * 3.5, "cached", fontsize=6, color=TEAL, va="bottom")
    fig.text((x0 + 60) / W, 1 - (y0 + 41.8) / H, "pseudo-bulk of chr1", fontsize=6, color=GREY, va="top")


def make_figure():
    import panel_a

    fig = plt.figure(figsize=(W * MM, H * MM))
    pa_h = panel_a.H
    panel_a.draw(panel_a.C(fig, rect=(0, 1 - pa_h / H, panel_a.W / W, pa_h / H)))
    y2 = pa_h + 1.5
    panel_b(fig, 1, y2)
    panel_c(fig, 50, y2)
    panel_d(fig, 113, y2)
    y3 = y2 + 66
    panel_e(fig, 1, y3)
    panel_f(fig, 72, y3)
    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"fig2.{ext}", dpi=300)
    return HERE / "fig2.pdf"


def main() -> None:
    print(make_figure())


if __name__ == "__main__":
    main()
