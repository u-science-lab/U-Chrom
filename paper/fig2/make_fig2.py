"""Figure 2 — the shared index at real scale.

Two modes:

* default (DESIGN MOCK-UP): every number comes from ``mock_data()`` — a
  PLACEHOLDER that only fixes layout, plot types, axes and comparisons;
  watermarked "MOCK" → ``fig2_mock.pdf / .png``.
* ``--real``: ``load_results()`` reads the benchmark JSONs in ``results/``
  (written by ``benchmarks/fig2/*.py``) and replaces the mock values of every
  panel it has numbers for; panels without results keep their mock values and
  are tagged "mock" in the corner.  Watermarked "PARTIAL — panel d mock"
  while panel d has no results → ``fig2_real.pdf / .png``.

  a  ChromData 2.0 schematic and the ``x.chromdata.zarr`` layout (``panel_a.py``; no data)
  b  storage: file size and full-read time vs n_spots — chromdata.zarr 2.0,
     h5cd 2.0, h5cd 1.x, Parquet, AnnData, FOF-CT (every series in b_storage.json)
  c  access by level: get_trace / get_cell / get_chrom latency and the time to
     open, backed chromdata.zarr from disk (solid, up to 1e8 spots; hollow =
     replicated cells) vs h5cd 1.x in memory (dashed); memory backed vs in memory
  d  out-of-core population analysis — needs streaming (roadmap step 7): mock
  e  linked contacts: on-disk size linked vs copied (uncompressed / gzip);
     pseudo-bulk time vs cells aggregated
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
W, H = 170.0, 207.0

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
# comparison formats (keys = series labels in b_storage.json): ChromData in indigo
# (chromdata.zarr solid, h5cd 2.0 dashed, h5cd 1.x dotted light), others in greys / purple
FORMATS = {
    "chromdata.zarr 2.0": dict(color=INDIGO, ls="-", marker="D", lw=1.3),
    "chromdata.zarr 2.0 (float32 coords)": dict(color=INDIGO, ls="", marker="+", ms=4, mew=0.7),
    "h5cd 2.0": dict(color=INDIGO, ls="--", marker="D", mfc="white"),
    "h5cd 1.x": dict(color=LINDIGO, ls=":", marker="D", mfc="white"),
    "Parquet": dict(color="#6b7079", ls="-", marker="s"),
    "AnnData (spots as obs)": dict(color=PURPLE, ls="-", marker="^"),
    "FOF-CT / CSV": dict(color="#9aa0a8", ls="-", marker="o"),
}
FORMAT_LABEL = {
    "chromdata.zarr 2.0": "chromdata.zarr 2.0",
    "chromdata.zarr 2.0 (float32 coords)": "chromdata.zarr, float32 xyz",
    "h5cd 2.0": "h5cd 2.0 (HDF5)",
    "h5cd 1.x": "h5cd 1.x",
    "Parquet": "Parquet (flat table)",
    "AnnData (spots as obs)": "AnnData (spots as obs)",
    "FOF-CT / CSV": "FOF-CT (CSV)",
}
# panel c: colour = operation, line style = how the data is held
LEVEL_COL = {"trace": ORANGE, "cell": INDIGO, "chromosome": GREY, "open": INK}
LEVEL_LABEL = {"trace": "get_trace", "cell": "get_cell", "chromosome": "get_chrom", "open": "open / load"}
ACCESS_MODES = {  # key -> (series label in c_access.json, legend label, line style)
    "backed": ("chromdata.zarr 2.0 (backed, from disk)", "chromdata.zarr, backed (disk)", "-"),
    "memory": ("h5cd 1.x (in memory, scan)", "h5cd 1.x, in memory", "--"),
}
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
    size = {"FOF-CT / CSV": 9e-5, "Parquet": 3e-5, "AnnData (spots as obs)": 5e-5, "h5cd 1.x": 4e-5,
            "h5cd 2.0": 3.5e-5, "chromdata.zarr 2.0": 2e-5, "chromdata.zarr 2.0 (float32 coords)": 1.9e-5}
    read = {"FOF-CT / CSV": 2e-6, "Parquet": 2e-7, "AnnData (spots as obs)": 6e-7, "h5cd 1.x": 5e-7,
            "h5cd 2.0": 4e-7, "chromdata.zarr 2.0": 3e-7, "chromdata.zarr 2.0 (float32 coords)": 2.9e-7}
    d["storage"] = {f: {"n": n, "size_mb": n * size[f], "read_s": n * read[f], "replicated": np.zeros(5, bool)}
                    for f in FORMATS}
    rep = np.array([False] * 4 + [True])
    d["access"] = {  # mode -> level -> dict(n, med, q1, q3, rep)
        "memory": {lvl: dict(n=n[:4], med=n[:4] * k, q1=n[:4] * k * 0.9, q3=n[:4] * k * 1.1, rep=rep[:4])
                   for lvl, k in [("trace", 4e-8), ("cell", 4e-8), ("chromosome", 5e-8), ("open", 7e-7)]},
        "backed": {lvl: dict(n=n, med=k * (1 + 0.3 * np.log10(n / 1e4)) * (n / 1e4) ** e, q1=None, q3=None, rep=rep)
                   for lvl, k, e in [("trace", 1e-3, 0.05), ("cell", 1e-3, 0.05), ("chromosome", 1e-3, 0.8),
                                     ("open", 2e-2, 0.1)]},
    }
    d["resident_mem"] = {"memory": (n[:4], n[:4] * 1.3e-3, rep[:4]),
                         "backed": (n, 30 * (n / 1e4) ** 0.35, rep)}
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
    if c:
        acc, mem = {}, {}
        for mode, (series, _, _) in ACCESS_MODES.items():
            if series not in c["series"]:
                continue
            pts = c["series"][series]["points"]
            n = np.array([p["n_spots"] for p in pts], float)
            rep = np.array([bool(p["replicated"]) for p in pts])
            acc[mode] = {lvl: dict(n=n, rep=rep,
                                   med=np.array([p[key]["latency_s"]["median"] for p in pts]),
                                   q1=np.array([p[key]["latency_s"]["q1"] for p in pts]),
                                   q3=np.array([p[key]["latency_s"]["q3"] for p in pts]))
                         for lvl, key in (("trace", "trace"), ("cell", "cell"), ("chromosome", "chrom"))}
            acc[mode]["open"] = dict(n=n, rep=rep, med=np.array([p["open_s"] for p in pts]), q1=None, q3=None)
            base = np.array([p["baseline_rss_mb"] for p in pts])
            if mode == "backed":  # peak RSS over open + the get_trace / get_cell queries
                used = np.array([p.get("peak_rss_trace_cell_mb") or p["rss_after_open_mb"] for p in pts])
            else:  # the whole data set is resident after the load
                used = np.array([p["rss_after_open_mb"] for p in pts])
            mem[mode] = (n, used - base, rep)
        if acc:
            out["access"], out["resident_mem"] = acc, mem
            out["real"].add("c")
    e = _load("e_contacts")
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
    fig.text(x / W, 1 - y / H, s, fontsize=8.5, fontweight="bold", va="top")
    if mock:
        fig.text((x + 1.9 * len(s) + 3) / W, 1 - (y + 0.6) / H, "mock", fontsize=6, color=RED, va="top",
                 fontstyle="italic")


def ax_at(fig, x, y, w, h):
    return fig.add_axes([x / W, 1 - (y + h) / H, w / W, h / H])


def loglog(ax):
    ax.set_xscale("log"); ax.set_yscale("log")


def _mock(d, key):
    return d.get("_mode") == "real" and key not in d["real"]


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
    label(fig, x0, y0, "b"); title(fig, x0 + 5, y0 + 0.4, "Storage and full reads", mock=_mock(d, "b"))
    st = d["storage"]
    unknown = sorted(set(st) - set(FORMATS))
    if unknown:
        raise KeyError(f"b_storage.json series without a style in FORMATS: {unknown}")
    for j, (key, ylab) in enumerate([("size_mb", "file size (MB)"), ("read_s", "full read into memory (s)")]):
        ax = ax_at(fig, x0 + 10 + j * 39, y0 + 8, 28, 30)
        for f, sty in reversed(list(FORMATS.items())):  # ChromData drawn last, on top
            if f not in st:
                continue
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
    order = [FORMAT_LABEL[f] for f in FORMATS if FORMAT_LABEL[f] in labels]
    handles = [handles[labels.index(l)] for l in order]
    labels = order
    if any(s["replicated"].any() for s in st.values()):
        handles.append(plt.Line2D([], [], marker="o", ls="", mfc="none", mec=RED, mew=0.5, ms=4))
        labels.append("replicated real cells")
    fig.legend(handles, labels, loc="upper left", bbox_to_anchor=((x0 + 6) / W, 1 - (y0 + 45.5) / H),
               ncol=2, frameon=False, columnspacing=1.2, handlelength=2.2, handletextpad=0.4,
               labelspacing=0.35)


def panel_c(fig, d, x0, y0):
    label(fig, x0, y0, "c"); title(fig, x0 + 5, y0 + 0.4, "Access by level", mock=_mock(d, "c"))
    from matplotlib.lines import Line2D
    acc = d["access"]
    ax = ax_at(fig, x0 + 11, y0 + 8, 36, 30)
    for mode, (_, _, ls) in ACCESS_MODES.items():
        for lvl, v in acc.get(mode, {}).items():
            col = LEVEL_COL[lvl]
            lw = 1.2 if ls == "-" else 0.9
            ax.plot(v["n"], v["med"], color=col, ls=ls, lw=lw, zorder=3)
            if v.get("q1") is not None:
                ax.fill_between(v["n"], v["q1"], v["q3"], color=col, alpha=0.15, lw=0)
            real = ~v["rep"]
            ax.plot(v["n"][real], v["med"][real], ls="", marker="o", ms=2.2, color=col, zorder=4)
            if v["rep"].any():
                ax.plot(v["n"][v["rep"]], v["med"][v["rep"]], ls="", marker="o", ms=3.2, mfc="white",
                        mec=col, mew=0.8, zorder=4)
    loglog(ax); ax.set_xlabel("spots"); ax.set_ylabel("time (s)")
    ax.set_xticks([1e4, 1e5, 1e6, 1e7, 1e8])
    # memory: backed (peak over open + get_trace / get_cell) vs in memory (after the load)
    ax2 = ax_at(fig, x0 + 58, y0 + 8, 19, 30)
    mem = d["resident_mem"]
    for mode, (_, lab, ls) in ACCESS_MODES.items():
        if mode not in mem:
            continue
        n, m, rep = mem[mode]
        ax2.plot(n, m, color=INDIGO, ls=ls, lw=1.2 if ls == "-" else 0.9)
        ax2.plot(n[~rep], m[~rep], ls="", marker="o", ms=2.2, color=INDIGO)
        if rep.any():
            ax2.plot(n[rep], m[rep], ls="", marker="o", ms=3.2, mfc="white", mec=INDIGO, mew=0.8)
    ax2.text(0.04, 0.99, "in memory\n(h5cd 1.x)", transform=ax2.transAxes, fontsize=6, color=INDIGO,
             ha="left", va="top")
    ax2.text(0.97, 0.18, "backed", transform=ax2.transAxes, fontsize=6, color=INDIGO, ha="right", va="top")
    loglog(ax2); ax2.set_xlabel("spots"); ax2.set_ylabel("memory used (MB)")
    ax2.set_xticks([1e4, 1e6, 1e8])
    # legends below the axes: colour = operation, line style = storage mode
    h1 = [Line2D([], [], color=LEVEL_COL[l], lw=1.2) for l in LEVEL_COL]
    l1 = [LEVEL_LABEL[l] for l in LEVEL_COL]
    h2 = [Line2D([], [], color=INK, ls=ls, lw=1.0) for _, _, ls in ACCESS_MODES.values()]
    l2 = [lab for _, lab, _ in ACCESS_MODES.values()]
    h2.append(Line2D([], [], ls="", marker="o", ms=3.2, mfc="white", mec=INK, mew=0.8))
    l2.append("replicated cells (1e8)")
    kw = dict(frameon=False, handlelength=2.2, handletextpad=0.4, columnspacing=0.9, labelspacing=0.35)
    fig.legend(h1, l1, loc="upper left", bbox_to_anchor=((x0 + 5) / W, 1 - (y0 + 45.5) / H), ncol=4, **kw)
    fig.legend(h2, l2, loc="upper left", bbox_to_anchor=((x0 + 5) / W, 1 - (y0 + 49.3) / H), ncol=2, **kw)


def panel_d(fig, d, x0, y0):
    label(fig, x0, y0, "d"); title(fig, x0 + 5, y0 + 0.4, "Out-of-core analysis", mock=_mock(d, "d"))
    if d.get("_mode") == "real":
        fig.text((x0 + 5) / W, 1 - (y0 + 4.6) / H, "MOCK: needs streaming (roadmap step 7)", fontsize=6,
                 color=RED, va="top", fontweight="bold")
    t = d["n_traces"]
    ax = ax_at(fig, x0 + 10, y0 + 9, 24, 30)
    ax.plot(t, d["peak_mem"]["in memory"], color=GREY, label="load all")
    ax.plot(t, d["peak_mem"]["streaming"], color=INDIGO, label="iter_traces")
    ax.axhline(d["budget_mb"], color=INDIGO, ls=":", lw=0.8)
    ax.text(t[0], d["budget_mb"] * 1.15, "budget", fontsize=6, color=INDIGO)
    loglog(ax); ax.set_xlabel("traces"); ax.set_ylabel("peak memory (MB)")
    ax.legend(frameon=False, loc="lower right", handlelength=1.5)
    ax2 = ax_at(fig, x0 + 45, y0 + 9, 12, 12)
    a, b = d["identity"]
    ax2.scatter(a, b, s=1.5, color=INDIGO, lw=0)
    lim = [min(a.min(), b.min()), max(a.max(), b.max())]
    ax2.plot(lim, lim, color=LGREY, lw=0.6, zorder=0)
    ax2.set_xlabel("load all", labelpad=1); ax2.set_ylabel("streaming", labelpad=1)
    ax2.set_xticks([]); ax2.set_yticks([])
    ax2.set_title("same result", fontsize=6, color=GREY, pad=2)


def panel_e(fig, d, x0, y0):
    label(fig, x0, y0, "e"); title(fig, x0 + 5, y0 + 0.4, "Linked contacts", mock=_mock(d, "e"))
    fig.text((x0 + 5) / W, 1 - (y0 + 4.6) / H, "no duplicate copy; stays in sync with .scool", fontsize=6,
             color=GREY, va="top")
    ax = ax_at(fig, x0 + 10, y0 + 9, 13, 30)
    keys = list(d["contacts_size"])
    own = [d["contacts_size"][k][0] for k in keys]
    ext = [d["contacts_size"][k][1] for k in keys]
    x = np.arange(len(keys))
    ax.bar(x, own, color=[TEAL] + [LGREY] * (len(keys) - 1), width=0.6, edgecolor=[TEAL] + [GREY] * (len(keys) - 1),
           lw=0.5)
    ax.bar(x, ext, bottom=own, color="white", width=0.6, edgecolor=TEAL, hatch="////", lw=0.5)
    ax.set_xticks(x, [k.replace(" (", "\n(") for k in keys], rotation=90, fontsize=6)
    ax.set_ylabel("on-disk size (GB)")
    if any(ext):
        ax.text(0, own[0] + ext[0] + 0.015 * ax.get_ylim()[1], ".scool (external)", ha="center", va="bottom",
                fontsize=6, color=TEAL, rotation=90)
    ax2 = ax_at(fig, x0 + 32, y0 + 9, 21, 30)
    c = d["agg_cells"]
    ax2.plot(c, d["agg_time"]["cold"], color=TEAL, marker="o", ms=2.5, label="first query")
    ax2.plot(c, d["agg_time"]["cached"], color=TEAL, ls="--", marker="o", ms=2.5, mfc="white", label="cached")
    loglog(ax2); ax2.set_xlabel("cells aggregated"); ax2.set_ylabel("time (s)")
    ax2.legend(frameon=False, loc="center right", handlelength=1.5)


def panel_f(fig, d, x0, y0):
    label(fig, x0, y0, "f"); title(fig, x0 + 5, y0 + 0.4, "Round trips", mock=_mock(d, "f"))
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
    y3 = y2 + 62
    panel_d(fig, d, 2, y3)
    panel_e(fig, d, 60, y3)
    panel_f(fig, d, 114, y3)
    if not real:
        fig.text(0.5, 0.28, "MOCK — placeholder data", fontsize=40, color="red", alpha=0.10,
                 ha="center", va="center", rotation=30, fontweight="bold")
        stem = "fig2_mock"
    else:
        missing = sorted(set("bcdef") - d["real"])
        if missing:
            fig.text(0.5, 0.28, "PARTIAL — panel " + ", ".join(missing) + " mock", fontsize=36, color="red",
                     alpha=0.10, ha="center", va="center", rotation=30, fontweight="bold")
        stem = "fig2_real"
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
