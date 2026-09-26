"""Figure 2 — the shared index at real scale.

Two modes:

* default (DESIGN MOCK-UP): every number comes from ``mock_data()`` — a
  PLACEHOLDER that only fixes layout, plot types, axes and comparisons;
  panels b–f boxed as placeholder data → ``fig2_mock.pdf / .png``.
* ``--real``: ``load_results()`` reads the benchmark JSONs in ``results/``
  (written by ``benchmarks/fig2/*.py``) and replaces the mock values of every
  panel it has numbers for; panels without results
  keep their mock values.  No watermark: every panel still on placeholder
  data sits in a grey dashed box labelled "planned … placeholder data"
  (in the mock figure, b–f) →
  ``fig2_real.pdf / .png``.  The ChromData format-version comparison (h5cd
  1.x / 2.0 / chromdata.zarr) is the supplementary ``make_figS_formats.py``.

  a  ChromData 2.0 schematic and the ``x.chromdata.zarr`` layout (``panel_a.py``; no data)
  b  storage: file size and full-read time vs n_spots — chromdata.zarr 2.0 vs
     Parquet, AnnData (spots as obs) and FOF-CT
  c  access by level: backed chromdata.zarr 2.1 from disk (get_trace / get_cell /
     get_chrom, get_chrom with columns="coords", open; solid, up to 1e8 spots,
     hollow = replicated cells; get_chrom of the 2.0 layout as a thin grey
     reference) vs the common in-memory baseline "load the flat table, then
     subset" (Parquet, AnnData; dashed); memory used, backed vs in memory
  d  population analysis beyond RAM (d_streaming.json): peak memory of the
     exact median distance map of one chromosome, load everything vs streaming
     iter_traces under a memory budget; streaming vs in-memory medians
  e  linked contacts queried through the shared index (e_query.json): cell
     group -> linked .scool -> pseudo-bulk (a real Oligo map), identical to the
     published per-type .cool for every cell type; pseudo-bulk time vs cells
     aggregated (e_contacts.json).  Sizes / import time: make_figS_contacts.py
  f  interoperability: what each round trip preserves

    python paper/fig2/make_fig2.py          # -> fig2_mock.pdf / .png
    python paper/fig2/make_fig2.py --real   # -> fig2_real.pdf / .png
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
MM = 1 / 25.4
W, H = 170.0, 226.0

mpl.rcParams.update({
    "pdf.fonttype": 42, "font.family": "sans-serif", "font.sans-serif": ["Arial"],
    "font.size": 7, "axes.titlesize": 7, "axes.labelsize": 7,
    "xtick.labelsize": 6, "ytick.labelsize": 6, "legend.fontsize": 6,
    "axes.linewidth": 0.5, "xtick.major.width": 0.5, "ytick.major.width": 0.5,
    "xtick.major.size": 2, "ytick.major.size": 2, "xtick.minor.size": 1, "ytick.minor.size": 1,
    "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 1.0,
})

ORANGE, TEAL, PURPLE, INDIGO = "#e07a3f", "#2a9d8f", "#8e7cc3", "#34568b"
GREY, LGREY, INK, RED = "#8a8f98", "#c9ccd1", "#2b2f36", "#c0392b"
LINDIGO = "#8fa3c7"
TINT_PURPLE = "#e6e0f3"
# comparison formats (keys = series labels in b_storage.json): ChromData in indigo
# (chromdata.zarr solid, h5cd 2.0 dashed, h5cd 1.x dotted light), others in greys / purple
FORMATS = {
    "chromdata.zarr 2.1": dict(color=INDIGO, ls="-", marker="D", lw=1.3),
    "chromdata.zarr 2.0": dict(color=INDIGO, ls="-", marker="D", lw=1.3),
    "chromdata.zarr 2.0 (float32 coords)": dict(color=INDIGO, ls="", marker="+", ms=4, mew=0.7),
    "h5cd 2.0": dict(color=INDIGO, ls="--", marker="D", mfc="white"),
    "h5cd 1.x": dict(color=LINDIGO, ls=":", marker="D", mfc="white"),
    "Parquet": dict(color="#6b7079", ls="-", marker="s"),
    "AnnData (spots as obs)": dict(color=PURPLE, ls="-", marker="^"),
    "FOF-CT / CSV": dict(color="#9aa0a8", ls="-", marker="o"),
}
FORMAT_LABEL = {
    "chromdata.zarr 2.1": "chromdata.zarr 2.1",
    "chromdata.zarr 2.0": "chromdata.zarr 2.0",
    "chromdata.zarr 2.0 (float32 coords)": "chromdata.zarr, float32 xyz",
    "h5cd 2.0": "h5cd 2.0 (HDF5)",
    "h5cd 1.x": "h5cd 1.x",
    "Parquet": "Parquet (flat table)",
    "AnnData (spots as obs)": "AnnData (spots as obs)",
    "FOF-CT / CSV": "FOF-CT (CSV)",
}
# panel b draws ChromData's container against the formats people use today; the
# ChromData version comparison (h5cd 1.x / 2.0, float32) is in make_figS_formats.py
MAIN_FORMATS = ["chromdata.zarr 2.1", "Parquet", "AnnData (spots as obs)", "FOF-CT / CSV"]
# panel c: backed chromdata.zarr, one colour per operation (solid) ...
LEVEL_COL = {"trace": ORANGE, "cell": INDIGO, "chromosome": TEAL, "chrom_coords": TEAL, "open": INK}
LEVEL_LS = {"chrom_coords": (0, (2.5, 1.2))}
LEVEL_LABEL = {"trace": "get_trace", "cell": "get_cell", "chromosome": "get_chrom",
               "chrom_coords": "get_chrom, coords only", "open": "open store"}
BACKED_SERIES = "chromdata.zarr 2.1 (backed, from disk)"
BACKED_SERIES_20 = "chromdata.zarr 2.0 (backed, from disk)"
# ... against the in-memory baseline "load the flat table, then subset" (dashed)
BASELINES = {  # key -> (series label in c_access.json, legend label, colour, line style)
    "Parquet": ("Parquet (load + subset)", "Parquet: load + get_trace", "#6b7079", "--"),
    "AnnData": ("AnnData (load + subset)", "AnnData: load + get_trace", PURPLE, (0, (1.2, 1.2))),
}
PLANNED = "planned (roadmap step 7) — placeholder data"
STATUS_VAL = {"preserved": 1.0, "partial": 0.5, "lost": -1.0, "na": 0.0, "untested": 0.0}


# --------------------------------------------------------------------------- data

def mock_data() -> dict:
    """PLACEHOLDER numbers — shapes only, not results."""
    n = np.logspace(4, 8, 5)
    rng = np.random.default_rng(0)
    d = {"real": set()}
    d["datasets"] = [  # name, modality, cells, observations, file MB  (approximate / to be measured)
        ("Bintu 2018 IMR90", "imaging", 1.3e3, 8.4e4, 6),
        ("Takei 2021 mESC", "imaging", 2.0e2, 3.2e5, 20),
        ("Takei 2025 FOV0", "imaging", 4.7e1, 3.8e5, 220),
        ("Takei 2025 all FOVs", "imaging", 2.0e3, 2.0e7, 9000),
        ("4DN FOF-CT (TBD)", "imaging", 5.0e3, 5.0e7, 4000),
        ("Stevens 2017 cell1", "sequencing", 1, 2.6e4, 3),
        ("IMR90 bulk Hi-C", "sequencing", 1e6, 1e9, 3000),
        ("H1/HFF sci-Hi-C", "sequencing", 1.5e4, 3e8, 2000),
        ("scHiCAR MOp", "multi-omics", 5.3e3, 1.2e8, 3000),
    ]
    size = {"chromdata.zarr 2.1": 2.6e-5, "FOF-CT / CSV": 9e-5, "Parquet": 3e-5, "AnnData (spots as obs)": 5e-5, "h5cd 1.x": 4e-5,
            "h5cd 2.0": 3.5e-5, "chromdata.zarr 2.0": 2e-5, "chromdata.zarr 2.0 (float32 coords)": 1.9e-5}
    read = {"chromdata.zarr 2.1": 3e-7, "FOF-CT / CSV": 2e-6, "Parquet": 2e-7, "AnnData (spots as obs)": 6e-7, "h5cd 1.x": 5e-7,
            "h5cd 2.0": 4e-7, "chromdata.zarr 2.0": 3e-7, "chromdata.zarr 2.0 (float32 coords)": 2.9e-7}
    d["storage"] = {f: {"n": n, "size_mb": n * size[f], "read_s": n * read[f], "replicated": np.zeros(5, bool)}
                    for f in FORMATS}
    rep = np.array([False] * 4 + [True])
    d["access"] = {  # level -> dict(n, med, q1, q3, rep)  (backed chromdata.zarr)
        lvl: dict(n=n, med=k * (1 + 0.3 * np.log10(n / 1e4)) * (n / 1e4) ** e, q1=None, q3=None, rep=rep)
        for lvl, k, e in [("trace", 1e-3, 0.05), ("cell", 1e-3, 0.05), ("chromosome", 1e-3, 0.8),
                          ("open", 2e-2, 0.1)]}
    d["baseline"] = {"Parquet": (n[:4], n[:4] * 1e-7 + 0.03, rep[:4]),
                     "AnnData": (n[:4], n[:4] * 5e-7 + 0.03, rep[:4])}
    d["resident_mem"] = {"backed": (n, 30 * (n / 1e4) ** 0.35, rep),
                         "Parquet": (n[:4], n[:4] * 1.3e-3, rep[:4]),
                         "AnnData": (n[:4], n[:4] * 2e-3, rep[:4])}
    t = np.logspace(3, 7, 5)
    d["n_traces"] = t
    d["peak_mem"] = {"in memory": t * 2e-3 + 50, "streaming": np.minimum(t * 2e-3 + 50, 800)}
    d["budget_mb"] = 1000
    x = rng.normal(size=400)
    d["identity"] = (x, x + rng.normal(scale=1e-6, size=400))
    d["contacts_size"] = {"linked": (0.05, 3.0), "copied (uncompr.)": (11.0, 0), "copied (gzip)": (3.0, 0)}  # GB (own, external)
    c = np.array([50, 100, 500, 1000, 5313])
    d["agg_cells"] = c
    d["agg_time"] = {"cold": c * 3e-4, "cached": np.full_like(c, 1e-3, dtype=float)}
    d["query"] = {"n_types": 22, "n_identical": 22, "n_pixels": 1_000_000, "max_abs_diff": 0.0,
                  "per_type": [("type%d" % i, 100, True) for i in range(22)],
                  "thumb": np.triu(rng.poisson(5, (50, 50)) + np.diag(np.full(50, 200))).astype(float),
                  "thumb_label": "chr2 40–90 Mb", "thumb_type": "Oligo", "thumb_cells": 268}
    d["interop"] = {
        "rows": ["FOF-CT", "AnnData / MuData", ".cool / .scool", "PDB", ".3dg"],
        "cols": ["coords", "cell › trace", "tracks", "cell table", "contacts"],
        # 1 = preserved, 0.5 = partial / by design, 0 = not applicable, -1 = lost
        "vals": np.array([[1, 1, 1, 1, 0], [1, 1, 1, 1, 0.5], [0, 0.5, 0, 0, 1],
                          [1, 0.5, 0, 0, 0], [1, 0.5, 0, 0, 0]]),
    }
    return d


def _load(name: str):
    p = RESULTS / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def load_results() -> dict:
    """Real numbers from ``results/*.json``; only the keys that exist are
    returned (``make_figure`` keeps mock values for the rest)."""
    out: dict = {"real": set(), "notes": []}
    b = _load("b_storage")
    if b:
        if "chromdata.zarr 2.1" not in b["series"] and "chromdata.zarr 2.0" in b["series"]:
            b["series"]["chromdata.zarr 2.1"] = b["series"]["chromdata.zarr 2.0"]
        st = {}
        for label, s in b["series"].items():
            pts = [p for p in s["points"] if p.get("size_mb", {}).get("median") is not None]
            if not pts:
                continue
            st[label] = {"n": np.array([p["n_spots"] for p in pts], float),
                         "size_mb": np.array([p["size_mb"]["median"] for p in pts]),
                         "read_s": np.array([p["read_s"]["median"] for p in pts]),
                         "read_lo": np.array([p["read_s"]["min"] for p in pts]),
                         "read_hi": np.array([p["read_s"]["max"] for p in pts]),
                         "replicated": np.array([bool(p["replicated"]) for p in pts])}
        if st:
            out["storage"] = st
            out["real"].add("b")
    c = _load("c_access")
    if c and BACKED_SERIES not in c["series"] and BACKED_SERIES_20 in c["series"]:
        c["series"][BACKED_SERIES] = c["series"].pop(BACKED_SERIES_20)   # before the 2.1 run
    if c and BACKED_SERIES in c["series"]:
        def arr(pts, f):
            return np.array([f(p) for p in pts])

        pts = c["series"][BACKED_SERIES]["points"]
        n, rep = arr(pts, lambda p: float(p["n_spots"])), arr(pts, lambda p: bool(p["replicated"]))
        acc = {lvl: dict(n=n, rep=rep, med=arr(pts, lambda p: p[key]["latency_s"]["median"]),
                         q1=arr(pts, lambda p: p[key]["latency_s"]["q1"]),
                         q3=arr(pts, lambda p: p[key]["latency_s"]["q3"]))
               for lvl, key in (("trace", "trace"), ("cell", "cell"), ("chromosome", "chrom"))}
        if all("chrom_coords" in p for p in pts):
            acc["chrom_coords"] = dict(n=n, rep=rep, med=arr(pts, lambda p: p["chrom_coords"]["latency_s"]["median"]),
                                       q1=None, q3=None)
        acc["open"] = dict(n=n, rep=rep, med=arr(pts, lambda p: p["open_s"]), q1=None, q3=None)
        if BACKED_SERIES_20 in c["series"]:
            p20 = c["series"][BACKED_SERIES_20]["points"]
            out["chrom_20"] = (arr(p20, lambda p: float(p["n_spots"])),
                               arr(p20, lambda p: p["chrom"]["latency_s"]["median"]),
                               arr(p20, lambda p: bool(p["replicated"])))
        # backed: peak RSS over open + the get_trace / get_cell queries, above the interpreter baseline
        mem = {"backed": (n, arr(pts, lambda p: (p.get("peak_rss_trace_cell_mb") or p["rss_after_open_mb"])
                                 - p["baseline_rss_mb"]), rep)}
        base = {}
        for key, (series, _, _, _) in BASELINES.items():
            if series not in c["series"]:
                continue
            bp = c["series"][series]["points"]
            bn, brep = arr(bp, lambda p: float(p["n_spots"])), arr(bp, lambda p: bool(p["replicated"]))
            # the user-visible cost of one query: load the whole table, then subset it
            base[key] = (bn, arr(bp, lambda p: p["open_s"] + p["trace"]["latency_s"]["median"]), brep)
            mem[key] = (bn, arr(bp, lambda p: p["rss_after_open_mb"] - p["baseline_rss_mb"]), brep)
        out["access"], out["baseline"], out["resident_mem"] = acc, base, mem
        out["real"].add("c")
    dd = _load("d_streaming")
    if dd and dd.get("points"):
        pts = dd["points"]
        tr = np.array([float(p["n_traces"]) for p in pts])
        rep_ = np.array([bool(p.get("replicated")) for p in pts])
        st = np.array([p["streaming"]["peak_rss_mb"]["median"] - p["streaming"]["baseline_rss_mb"]["median"]
                       for p in pts])
        la = [p for p in pts if "load_all" in p]
        out["peak_mem"] = {"streaming": (tr, st, rep_),
                           "load all": (np.array([float(p["n_traces"]) for p in la]),
                                        np.array([p["load_all"]["peak_rss_mb"]["median"]
                                                  - p["load_all"]["baseline_rss_mb"]["median"] for p in la]))}
        out["d_times"] = {"streaming": np.array([p["streaming"]["seconds"]["median"] for p in pts]),
                          "load all": np.array([p["load_all"]["seconds"]["median"] for p in la])}
        out["budget_mb"] = dd["budget_mb"]
        out["d_chrom"] = dd["chrom"]
        out["d_infeasible"] = [float(p["n_traces"]) for p in pts if "load_all" not in p]
        out["d_identical"] = all(p.get("identical") for p in pts)
        out["d_n_sizes"] = len(pts)
        sc = dd.get("scatter")
        if sc:
            out["identity"] = (np.asarray(sc["load_all"]), np.asarray(sc["streaming"]))
            out["identity_n"] = sc["n_pairs_total"]
        out["real"].add("d")
    q = _load("e_query")
    e = _load("e_contacts")
    if q:
        idt = q["identity"]
        th = q["thumbnail"]
        out["query"] = {"n_types": idt["n_types"], "n_identical": idt["n_identical"], "n_pixels": idt["n_pixels"],
                        "max_abs_diff": idt["max_abs_diff"],
                        "per_type": [(t["cell_type"], t["n_cells"], t["identical"]) for t in idt["per_type"]],
                        "thumb": np.asarray(th["matrix"], float),
                        "thumb_label": f"{th['chrom']} {th['start'] // 10**6}–{th['end'] // 10**6} Mb",
                        "thumb_type": th["cell_type"],
                        "thumb_cells": next(t["n_cells"] for t in idt["per_type"] if t["cell_type"] == th["cell_type"])}
    if e:
        s = e["size"]
        gb = 1 / 2**30
        out["contacts_size"] = {
            "linked": (s["h5cd_linked_bytes"] * gb, s["scool_bytes"] * gb),
            "copied (uncompr.)": (s["copied_h5cd_1x_settings_bytes"] * gb, 0),
            "copied (gzip)": (s["copied_cooler_settings_gzip6_shuffle_bytes"] * gb, 0),
        }
        pts = e["aggregation"]["points"]
        out["agg_cells"] = np.array([p["n_cells"] for p in pts])
        out["agg_time"] = {"cold": np.array([p["cold_s"]["median"] for p in pts]),
                           "cached": np.array([p["cached_s"]["median"] for p in pts])}
        if q:
            out["real"].add("e")
    f = _load("f_roundtrip")
    if f:
        rows = [r for r in f["rows"]]
        out["interop"] = {"rows": rows, "cols": f["cols"],
                          "vals": np.array([[STATUS_VAL[f["cells"][r][c]["status"]] for c in f["cols"]]
                                            for r in rows])}
        out["real"].add("f")
    return out


# --------------------------------------------------------------------------- helpers

def label(fig, x, y, s):
    fig.text(x / W, 1 - y / H, s, fontsize=10, fontweight="bold", va="top")


def title(fig, x, y, s, mock=False):
    """Panel title.  Placeholder panels are marked by :func:`planned_box`, not here."""
    fig.text(x / W, 1 - y / H, s, fontsize=8.5, fontweight="bold", va="top")


# panel extents (x, y, w, h in mm), for the placeholder boxes
def planned_box(fig, x, y, w, h, text=PLANNED):
    """Grey dashed rounded box around a panel on placeholder data, with a small label."""
    from matplotlib.patches import FancyBboxPatch
    fig.patches.append(FancyBboxPatch((x / W, 1 - (y + h) / H), w / W, h / H,
                                      boxstyle="round,pad=0,rounding_size=0.008", transform=fig.transFigure,
                                      fc="none", ec=GREY, lw=0.6, ls=(0, (3, 2)), zorder=0))
    fig.text((x + w - 1.5) / W, 1 - (y + h - 1.2) / H, text, fontsize=6, color=GREY, ha="right", va="bottom")


def ax_at(fig, x, y, w, h):
    return fig.add_axes([x / W, 1 - (y + h) / H, w / W, h / H])


def loglog(ax):
    ax.set_xscale("log"); ax.set_yscale("log")


# --------------------------------------------------------------------------- panels

def panel_a(fig, d, x0, y0):
    """Dataset-coverage scatter (moved to the supplement; kept for reference)."""
    label(fig, x0, y0, "a"); title(fig, x0 + 5, y0 + 0.4, "Datasets on one index")
    ax = ax_at(fig, x0 + 11, y0 + 9, 62, 44)
    col = {"imaging": ORANGE, "sequencing": TEAL, "multi-omics": PURPLE}
    for name, mod, cells, obs, mb in d["datasets"]:
        ax.scatter(cells, obs, s=6 + 14 * np.log10(mb + 1), color=col[mod], alpha=0.85, lw=0.4, ec="white", zorder=3)
        off = {"Takei 2025 FOV0": (-4, 5), "Takei 2021 mESC": (4, -8), "Bintu 2018 IMR90": (4, -7)}.get(name, (3, 2))
        ha = "right" if off[0] < 0 else "left"
        ax.annotate(name, (cells, obs), xytext=off, textcoords="offset points", fontsize=6, color=INK, ha=ha)
    loglog(ax); ax.set_xlim(0.5, 5e6); ax.set_ylim(1e4, 5e9)
    ax.set_xlabel("cells"); ax.set_ylabel("observations (spots or contacts)")
    for i, (k, v) in enumerate(col.items()):
        ax.scatter([], [], color=v, s=14, label=k)
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(0.0, 0.93), handletextpad=0.2)
    ax.text(0.02, 0.98, "marker size: file size", transform=ax.transAxes, fontsize=6, color=GREY, va="top")


def panel_b(fig, d, x0, y0):
    label(fig, x0, y0, "b"); title(fig, x0 + 5, y0 + 0.4, "Storage and full reads")
    st = {f: v for f, v in d["storage"].items() if f in MAIN_FORMATS}
    for j, (key, ylab) in enumerate([("size_mb", "file size (MB)"), ("read_s", "full read into memory (s)")]):
        ax = ax_at(fig, x0 + 10 + j * 39, y0 + 8, 28, 30)
        for f in reversed(MAIN_FORMATS):  # ChromData drawn last, on top
            if f not in st:
                continue
            sty = FORMATS[f]
            s = st[f]
            sty = {"ms": 2.3, **sty}
            ax.plot(s["n"], s[key], **sty, label=FORMAT_LABEL[f],
                    zorder=4 if f.startswith("chromdata") else 3)
            rep = s["replicated"]
            if rep.any():
                ax.scatter(s["n"][rep], s[key][rep], s=16, facecolor="none", edgecolor=RED, lw=0.5, zorder=5)
        loglog(ax); ax.set_xlabel("spots"); ax.set_ylabel(ylab)
        nmax = max(float(v["n"].max()) for v in st.values())
        ax.set_xticks([10.0 ** k for k in range(4, int(np.log10(nmax * 1.5)) + 1)])
    handles, labels = ax.get_legend_handles_labels()
    order = [FORMAT_LABEL[f] for f in MAIN_FORMATS if FORMAT_LABEL[f] in labels]
    handles = [handles[labels.index(l)] for l in order]
    labels = order
    if any(s["replicated"].any() for s in st.values()):
        handles.append(plt.Line2D([], [], marker="o", ls="", mfc="none", mec=RED, mew=0.5, ms=4))
        labels.append("replicated real cells")
    fig.legend(handles, labels, loc="upper left", bbox_to_anchor=((x0 + 6) / W, 1 - (y0 + 45.5) / H),
               ncol=2, frameon=False, columnspacing=1.2, handlelength=2.2, handletextpad=0.4,
               labelspacing=0.35)


def panel_c(fig, d, x0, y0):
    label(fig, x0, y0, "c"); title(fig, x0 + 5, y0 + 0.4, "Access by level")
    from matplotlib.lines import Line2D

    def draw(ax, n, y, color, ls, rep, lw=1.2):
        ax.plot(n, y, color=color, ls=ls, lw=lw, zorder=3)
        ax.plot(n[~rep], y[~rep], ls="", marker="o", ms=2.2, color=color, zorder=4)
        if rep.any():
            ax.plot(n[rep], y[rep], ls="", marker="o", ms=3.2, mfc="white", mec=color, mew=0.8, zorder=4)

    ax = ax_at(fig, x0 + 11, y0 + 8, 36, 30)
    for key, (_, _, col, ls) in BASELINES.items():
        if key in d["baseline"]:
            n, t, rep = d["baseline"][key]
            draw(ax, n, t, col, ls, rep, lw=1.1)
    if "chrom_20" in d:
        n20, t20, r20 = d["chrom_20"]
        ax.plot(n20, t20, color=LGREY, lw=0.8, zorder=2)
        ax.plot(n20[~r20], t20[~r20], ls="", marker="o", ms=1.6, color=LGREY, zorder=2)
        ax.plot(n20[r20], t20[r20], ls="", marker="o", ms=2.4, mfc="white", mec=LGREY, mew=0.6, zorder=2)
    for lvl, v in d["access"].items():
        col = LEVEL_COL[lvl]
        if v.get("q1") is not None:
            ax.fill_between(v["n"], v["q1"], v["q3"], color=col, alpha=0.15, lw=0)
        draw(ax, v["n"], v["med"], col, LEVEL_LS.get(lvl, "-"), v["rep"], lw=0.9 if lvl == "chrom_coords" else 1.2)
    loglog(ax); ax.set_xlabel("spots"); ax.set_ylabel("time per query (s)")
    ax.set_xticks([1e4, 1e5, 1e6, 1e7, 1e8])
    # memory: backed (peak over open + get_trace / get_cell) vs the whole table loaded
    ax2 = ax_at(fig, x0 + 58, y0 + 8, 19, 30)
    mem = d["resident_mem"]
    if "backed" in mem:
        draw(ax2, *mem["backed"][:2], INDIGO, "-", mem["backed"][2])
    for key, (_, _, col, ls) in BASELINES.items():
        if key in mem:
            n, m, rep = mem[key]
            draw(ax2, n, m, col, ls, rep, lw=1.1)
    ax2.text(0.04, 0.99, "load all", transform=ax2.transAxes, fontsize=6, color=INK, ha="left", va="top")
    ax2.text(0.97, 0.16, "backed", transform=ax2.transAxes, fontsize=6, color=INDIGO, ha="right", va="top")
    loglog(ax2); ax2.set_xlabel("spots"); ax2.set_ylabel("memory used (MB)")
    ax2.set_xticks([1e4, 1e6, 1e8])
    # legends below the axes
    lv = [l for l in LEVEL_COL if l in d["access"]]
    h1 = [Line2D([], [], color=LEVEL_COL[l], lw=1.2 if l != "chrom_coords" else 0.9, ls=LEVEL_LS.get(l, "-"))
          for l in lv]
    l1 = [LEVEL_LABEL[l] for l in lv]
    if "chrom_20" in d:
        h1.append(Line2D([], [], color=LGREY, lw=0.8))
        l1.append("get_chrom, 2.0 layout")
    h2 = [Line2D([], [], color=col, ls=ls, lw=1.1) for _, _, col, ls in BASELINES.values()]
    l2 = [lab for _, lab, _, _ in BASELINES.values()]
    h2.append(Line2D([], [], ls="", marker="o", ms=3.2, mfc="white", mec=INK, mew=0.8))
    l2.append("replicated cells (1e8)")
    kw = dict(frameon=False, handlelength=2.2, handletextpad=0.4, columnspacing=0.9, labelspacing=0.35)
    fig.text((x0 + 5.5) / W, 1 - (y0 + 47.6) / H, "chromdata.zarr 2.1, backed (from disk):", fontsize=6,
             color=INK, va="top", fontweight="bold")
    fig.legend(h1, l1, loc="upper left", bbox_to_anchor=((x0 + 5) / W, 1 - (y0 + 49.4) / H), ncol=3, **kw)
    fig.text((x0 + 5.5) / W, 1 - (y0 + 58.2) / H, "in memory (whole table loaded first):", fontsize=6,
             color=INK, va="top", fontweight="bold")
    fig.legend(h2, l2, loc="upper left", bbox_to_anchor=((x0 + 5) / W, 1 - (y0 + 60.0) / H), ncol=2, **kw)


def panel_d(fig, d, x0, y0):
    label(fig, x0, y0, "d"); title(fig, x0 + 5, y0 + 0.4, "Analysis beyond RAM")
    chrom = d.get("d_chrom", "chr11")
    fig.text((x0 + 5) / W, 1 - (y0 + 4.6) / H, f"exact median distance map ({chrom})", fontsize=6,
             color=GREY, va="top")
    ax = ax_at(fig, x0 + 10, y0 + 10, 23, 29)
    pm = d["peak_mem"]
    if "load all" in pm:
        n, m = pm["load all"][:2]
        ax.plot(n, m, color=GREY, marker="o", ms=2.2, lw=1.1, zorder=3)
    if "streaming" in pm:
        n, m = pm["streaming"][:2]
        rep = pm["streaming"][2] if len(pm["streaming"]) > 2 else np.zeros(len(n), bool)
        ax.plot(n, m, color=INDIGO, lw=1.2, zorder=4)
        ax.plot(n[~rep], m[~rep], ls="", marker="o", ms=2.2, color=INDIGO, zorder=5)
        if rep.any():
            ax.plot(n[rep], m[rep], ls="", marker="o", ms=3.2, mfc="white", mec=INDIGO, mew=0.8, zorder=5)
    ax.axhline(d["budget_mb"], color=INDIGO, ls=":", lw=0.8)
    loglog(ax)
    lo, hi = ax.get_ylim()
    ax.set_ylim(lo, max(hi, d["budget_mb"] * 12))
    xs = pm["streaming"][0] if "streaming" in pm else d.get("n_traces")
    ax.text(float(np.min(xs)), d["budget_mb"] * 1.15, f"budget\n{d['budget_mb'] / 1024:g} GB", fontsize=6,
            color=INDIGO, va="bottom", linespacing=1.0)
    ax.set_xlim(float(np.min(xs)) / 2, float(np.max(xs)) * 2)
    for xi in d.get("d_infeasible", []):
        top = ax.get_ylim()[1]
        ax.plot([xi], [top / 1.5], marker="x", ms=4, color=GREY, mew=0.9, zorder=5, clip_on=False)
        ax.text(xi * 1.3, ax.get_ylim()[0] * 1.6, "load all at\n1e8 spots:\nout of RAM", fontsize=6,
                color=GREY, ha="right", va="bottom", linespacing=1.0)
    ax.set_xlabel("traces"); ax.set_ylabel("memory used (MB)")
    ax.xaxis.set_major_locator(mpl.ticker.LogLocator(base=10, numticks=10))
    ax.xaxis.set_minor_formatter(mpl.ticker.NullFormatter())
    from matplotlib.lines import Line2D
    h = [Line2D([], [], color=GREY, marker="o", ms=2.2, lw=1.1),
         Line2D([], [], color=INDIGO, marker="o", ms=2.2, lw=1.2)]
    labs = ["load all, then compute", "stream iter_traces"]
    if "streaming" in pm and len(pm["streaming"]) > 2 and pm["streaming"][2].any():
        h.append(Line2D([], [], ls="", marker="o", ms=3.2, mfc="white", mec=INK, mew=0.8))
        labs.append("replicated cells (1e8)")
    fig.legend(h, labs, loc="upper left", bbox_to_anchor=((x0 + 4) / W, 1 - (y0 + 51.5) / H), ncol=1,
               frameon=False, handlelength=2.0, handletextpad=0.4, labelspacing=0.3)
    # identity: streaming vs in memory
    ax2 = ax_at(fig, x0 + 38.0, y0 + 10, 12, 12)
    a, b = d["identity"]
    ax2.scatter(a, b, s=1.2, color=INDIGO, lw=0, rasterized=True)
    lim = [min(a.min(), b.min()), max(a.max(), b.max())]
    ax2.plot(lim, lim, color=LGREY, lw=0.6, zorder=0)
    ax2.set_xlabel("in memory", labelpad=1); ax2.set_ylabel("streaming", labelpad=1)
    ax2.set_xticks([]); ax2.set_yticks([])
    same = "identical" if d.get("d_identical", True) else "differs"
    ax2.set_title(f"medians {same}", fontsize=6, color=GREY, pad=2)
    if d.get("identity_n"):
        fig.text((x0 + 44.0) / W, 1 - (y0 + 27.0) / H, f"bitwise at all\n{d.get('d_n_sizes', 5)} sizes;"
                 f"\n1e7 shown\n({d['identity_n'] / 1e6:.1f} M pairs)", fontsize=6, color=GREY, ha="center",
                 va="top", linespacing=1.1)


def panel_e(fig, d, x0, y0):
    from matplotlib.colors import LinearSegmentedColormap, LogNorm
    from matplotlib.lines import Line2D
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

    label(fig, x0, y0, "e"); title(fig, x0 + 5, y0 + 0.4, "Linked contacts via the index")
    fig.text((x0 + 5) / W, 1 - (y0 + 4.6) / H,
             "no copy — groups defined in ChromData query\ncommunity .scool files", fontsize=6, color=GREY,
             va="top", linespacing=1.05)
    q = d["query"]
    # schematic overlay, in mm (y down)
    ov = fig.add_axes([x0 / W, 1 - (y0 + 36) / H, 58 / W, 26 / H])
    ov.set_xlim(0, 58); ov.set_ylim(36, 10); ov.axis("off")
    rows, sel = 8, (3, 4)
    for k in range(rows):
        on = k in sel
        ov.add_patch(Rectangle((1.5, 14 + k * 2.0), 8, 2.0, fc=TINT_PURPLE if on else "#eef0f3",
                               ec=PURPLE if on else LGREY, lw=0.6 if on else 0.4))
    ov.text(5.5, 13.4, "cells", fontsize=6, fontweight="bold", ha="center", va="bottom", color=INK)
    ov.text(5.5, 30.6, f"cell_type\n= {q['thumb_type']}", fontsize=6, ha="center", va="top", color=PURPLE,
            linespacing=1.0)
    ov.add_patch(FancyBboxPatch((13.5, 17.5), 11.5, 8, boxstyle="round,pad=0,rounding_size=1.0", fc="white",
                                ec=TEAL, lw=0.6, ls=(0, (2.2, 1.2))))
    ov.text(19.25, 20.2, ".scool", fontsize=6, fontweight="bold", color=TEAL, ha="center", va="center")
    ov.text(19.25, 23.3, "per cell", fontsize=6, color=TEAL, ha="center", va="center")
    for (xa, ya), (xb, yb) in (((9.9, 21.5), (13.1, 21.5)), ((25.4, 21.5), (29.0, 21.5))):
        ov.add_patch(FancyArrowPatch((xa, ya), (xb, yb), arrowstyle="-|>", mutation_scale=5, lw=0.7,
                                     color=TEAL))
    # thumbnail: the real pseudo-bulk (upper triangle), white -> teal
    m = np.asarray(q["thumb"], float)
    n = len(m)
    up = np.where(np.triu(np.ones((n, n), bool)), m, np.nan)
    cmap = LinearSegmentedColormap.from_list("wt", ["#ffffff", "#a8dcd5", TEAL, "#12544c"])
    tax = fig.add_axes([(x0 + 30) / W, 1 - (y0 + 33.5) / H, 21 / W, 21 / H])
    pos = up[np.isfinite(up) & (up > 0)]
    tax.imshow(up, cmap=cmap, norm=LogNorm(vmin=max(1.0, np.percentile(pos, 5)), vmax=np.percentile(pos, 99.5)),
               interpolation="nearest")
    tax.set_xticks([]); tax.set_yticks([])
    for sp in tax.spines.values():
        sp.set_visible(False)
    fig.text((x0 + 51.5) / W, 1 - (y0 + 13.5) / H, f"{q['thumb_type']}\npseudo-\nbulk", fontsize=6,
             color=INK, va="top", linespacing=1.05)
    fig.text((x0 + 51.5) / W, 1 - (y0 + 21.5) / H, f"{q['thumb_label'].replace(' ', chr(10), 1)}\n1 Mb",
             fontsize=6, color=GREY, va="top", linespacing=1.05)
    # correctness: one dot per cell type
    fig.text((x0 + 1.5) / W, 1 - (y0 + 38.0) / H,
             f"= published per-type .cool for\n{q['n_identical']}/{q['n_types']} cell types: "
             f"max |Δ| = {q['max_abs_diff']:g} over\n{q['n_pixels'] / 1e6:.1f} M pixels, all chromosomes",
             fontsize=6, color=INK, va="top", linespacing=1.1)
    sax = fig.add_axes([(x0 + 1.5) / W, 1 - (y0 + 50.5) / H, 33 / W, 3.5 / H])
    k = len(q["per_type"])
    ok = np.array([t[2] for t in q["per_type"]])
    sax.scatter(np.arange(k)[ok], np.zeros(ok.sum()), s=7, color=TEAL, lw=0)
    if (~ok).any():
        sax.scatter(np.arange(k)[~ok], np.zeros((~ok).sum()), s=7, marker="x", color=RED, lw=0.8)
    sax.set_xlim(-0.8, k - 0.2); sax.set_ylim(-1, 1); sax.axis("off")
    fig.text((x0 + 1.5) / W, 1 - (y0 + 51.5) / H, "one dot per type (42–642 cells)" if k == 22
             else "one dot per cell type", fontsize=6, color=GREY, va="top")
    # speed
    ax2 = ax_at(fig, x0 + 46, y0 + 38.5, 12, 14)
    c = d["agg_cells"]
    ax2.plot(c, d["agg_time"]["cold"], color=TEAL, marker="o", ms=2.0)
    ax2.plot(c, d["agg_time"]["cached"], color=TEAL, ls="--", marker="o", ms=2.0, mfc="white")
    loglog(ax2); ax2.set_xlabel("cells aggregated", labelpad=1); ax2.set_ylabel("time (s)", labelpad=0)
    ax2.set_xticks([1e2, 1e3])
    h = [Line2D([], [], color=TEAL, marker="o", ms=2.0), Line2D([], [], color=TEAL, ls="--", marker="o", ms=2.0,
                                                                  mfc="white")]
    fig.legend(h, ["first query", "cached (LRU)"], loc="upper left", frameon=False, ncol=2,
               bbox_to_anchor=((x0 + 0.5) / W, 1 - (y0 + 55.5) / H), handlelength=1.8, columnspacing=1.0)


def panel_f(fig, d, x0, y0):
    label(fig, x0, y0, "f"); title(fig, x0 + 5, y0 + 0.4, "Round trips")
    it = d["interop"]
    v = it["vals"]
    rows_h = 23 * v.shape[0] / 5
    ax = ax_at(fig, x0 + 21, y0 + 14, 28, rows_h)
    for i in range(v.shape[0]):
        for j in range(v.shape[1]):
            val = float(v[i, j])
            if val < 0:  # representable but lost
                ax.plot(j + 0.5, i + 0.5, marker="x", ms=4.5, color=RED, mew=0.8)
                continue
            fill = {1: "full", 0.5: "left", 0: "none"}[val]
            ax.plot(j + 0.5, i + 0.5, marker="o", ms=6, fillstyle=fill, color=INDIGO if val else LGREY,
                    mec=INDIGO if val else LGREY, mew=0.7, markerfacecoloralt="white")
    ax.set_xlim(0, v.shape[1]); ax.set_ylim(v.shape[0], 0)
    ax.set_xticks(np.arange(v.shape[1]) + 0.5, it["cols"], rotation=45, ha="left")
    ax.xaxis.tick_top(); ax.tick_params(length=0)
    ax.set_yticks(np.arange(v.shape[0]) + 0.5, it["rows"])
    for s in ax.spines.values():
        s.set_visible(False)
    from matplotlib.lines import Line2D
    hs = [Line2D([], [], marker="o", ls="", ms=5, fillstyle=f, color=c, mec=c, markerfacecoloralt="white")
          for f, c in (("full", INDIGO), ("left", INDIGO), ("none", LGREY))]
    labs = ["preserved", "partial or by design", "not applicable"]
    if (v < 0).any():
        hs.append(Line2D([], [], marker="x", ls="", ms=4, color=RED, mew=0.8))
        labs.append("lost")
    ax.legend(hs, labs, loc="upper left", bbox_to_anchor=(-0.62, -0.04), ncol=2, frameon=False,
              handletextpad=0.2, columnspacing=1.0)


def make_figure(real: bool = False):
    import panel_a

    d = mock_data()
    if real:
        r = load_results()
        d.update({k: v for k, v in r.items() if k not in ("real", "notes")})
        d["real"] = r["real"]
        d["_mode"] = "real"
    fig = plt.figure(figsize=(W * MM, H * MM))
    pa_h = panel_a.H
    panel_a.draw(panel_a.C(fig, rect=(0, 1 - pa_h / H, panel_a.W / W, pa_h / H)))
    y2 = pa_h + 3
    panel_b(fig, d, 2, y2)
    panel_c(fig, d, 88, y2)
    y3 = y2 + 73
    panel_d(fig, d, 2, y3)
    panel_e(fig, d, 55, y3)
    panel_f(fig, d, 115, y3)
    # placeholder panels: grey dashed box + label (no watermark)
    extents = {"b": (1, y2 - 1.5, 85, 71), "c": (87, y2 - 1.5, 82, 71), "d": (1, y3 - 1.5, 52, H - y3 + 0.5),
               "e": (54, y3 - 1.5, 60, H - y3 + 0.5), "f": (114, y3 - 1.5, 55, H - y3 + 0.5)}
    placeholder = sorted(set("bcdef") - d["real"])
    for k in placeholder:
        planned_box(fig, *extents[k], text="placeholder data")
    stem = "fig2_real" if real else "fig2_mock"
    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"{stem}.{ext}", dpi=300)
    return HERE / f"{stem}.pdf", d


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--real", action="store_true", help="fill panels from results/*.json → fig2_real.pdf")
    args = ap.parse_args()
    path, d = make_figure(real=args.real)
    if args.real:
        print(f"real panels: {sorted(d['real'])}; mock: {sorted(set('bcdef') - d['real'])}")
    print(path)


if __name__ == "__main__":
    main()
