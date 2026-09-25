"""Figure 2 — the shared index at real scale (DESIGN MOCK-UP).

Every number drawn here comes from ``mock_data()`` and is a PLACEHOLDER that
only fixes the layout, plot types, axes and comparisons.  The figure is
watermarked "MOCK".  Once the benchmarks exist, ``load_results()`` replaces
``mock_data()`` and the drawing code stays the same.

  a  datasets covered: cells x observations, by modality (real datasets)
  b  storage: file size and full-read time vs n_spots, h5cd vs common formats
  c  access by level: get_trace / get_cell / get_chrom latency, 1.x scan vs 2.x index;
     backed-mode memory
  d  out-of-core population analysis: peak memory vs n_traces, streaming vs in-memory;
     identical results
  e  linked contacts: file size copied vs linked; pseudo-bulk time vs cells aggregated
  f  interoperability: what each round trip preserves

    python paper/fig2/make_fig2.py          # -> fig2_mock.pdf / .png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
MM = 1 / 25.4
W, H = 170.0, 197.0

mpl.rcParams.update({
    "pdf.fonttype": 42, "font.family": "sans-serif", "font.sans-serif": ["Arial"],
    "font.size": 7, "axes.titlesize": 7, "axes.labelsize": 7,
    "xtick.labelsize": 6, "ytick.labelsize": 6, "legend.fontsize": 6,
    "axes.linewidth": 0.5, "xtick.major.width": 0.5, "ytick.major.width": 0.5,
    "xtick.major.size": 2, "ytick.major.size": 2, "xtick.minor.size": 1, "ytick.minor.size": 1,
    "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 1.0,
})

ORANGE, TEAL, PURPLE, INDIGO = "#e07a3f", "#2a9d8f", "#8e7cc3", "#34568b"
GREY, LGREY, INK = "#8a8f98", "#c9ccd1", "#2b2f36"
# comparison formats: h5cd in indigo (2.x solid, 1.x dashed), others in greys
FORMATS = {
    "FOF-CT / CSV": dict(color="#9aa0a8", ls="-", marker="o"),
    "Parquet": dict(color="#6b7079", ls="-", marker="s"),
    "AnnData (spots as obs)": dict(color=PURPLE, ls="-", marker="^"),
    "h5cd 1.x": dict(color=INDIGO, ls="--", marker="D", mfc="white"),
    "h5cd 2.x": dict(color=INDIGO, ls="-", marker="D"),
}


# --------------------------------------------------------------------------- data

def mock_data() -> dict:
    """PLACEHOLDER numbers — shapes only, not results."""
    n = np.logspace(4, 8, 5)
    rng = np.random.default_rng(0)
    d = {}
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
    d["n_spots"] = n
    d["size_mb"] = {"FOF-CT / CSV": n * 9e-5, "Parquet": n * 3e-5, "AnnData (spots as obs)": n * 5e-5,
                    "h5cd 1.x": n * 4e-5, "h5cd 2.x": n * 2e-5}
    d["read_s"] = {"FOF-CT / CSV": n * 2e-6, "Parquet": n * 2e-7, "AnnData (spots as obs)": n * 6e-7,
                   "h5cd 1.x": n * 5e-7, "h5cd 2.x": n * 3e-7}
    d["access"] = {  # level -> (1.x latency, 2.x latency) vs n_spots
        lvl: (n * k1, np.full_like(n, k2) * (1 + 0.05 * np.log10(n)))
        for lvl, k1, k2 in [("trace", 4e-8, 2e-4), ("cell", 4e-8, 1e-3), ("chromosome", 5e-8, 2e-2)]}
    d["backed_mem"] = {"in memory": n * 6e-5, "backed": np.full_like(n, 60.0)}
    t = np.logspace(3, 7, 5)
    d["n_traces"] = t
    d["peak_mem"] = {"in memory": t * 2e-3 + 50, "streaming": np.minimum(t * 2e-3 + 50, 800)}
    d["budget_mb"] = 1000
    x = rng.normal(size=400)
    d["identity"] = (x, x + rng.normal(scale=1e-6, size=400))
    d["contacts_size"] = {"linked (.scool)": 3.0, "copied into h5cd": 11.0}  # GB
    c = np.array([50, 100, 500, 1000, 5313])
    d["agg_cells"] = c
    d["agg_time"] = {"cold": c * 3e-4, "cached": np.full_like(c, 1e-3, dtype=float)}
    d["interop"] = {
        "rows": ["FOF-CT", "AnnData / MuData", ".cool / .scool", "PDB", ".3dg"],
        "cols": ["coords", "cell › trace", "tracks", "cell table", "contacts"],
        # 1 = preserved, 0.5 = partial / by design, 0 = not applicable
        "vals": np.array([[1, 1, 1, 1, 0], [1, 1, 1, 1, 0.5], [0, 0.5, 0, 0, 1],
                          [1, 0.5, 0, 0, 0], [1, 0.5, 0, 0, 0]]),
    }
    return d


def load_results() -> dict:
    raise NotImplementedError("benchmarks not run yet — see paper/fig2/PLAN.md")


# --------------------------------------------------------------------------- helpers

def label(fig, x, y, s):
    fig.text(x / W, 1 - y / H, s, fontsize=10, fontweight="bold", va="top")


def title(fig, x, y, s):
    fig.text(x / W, 1 - y / H, s, fontsize=8.5, fontweight="bold", va="top")


def ax_at(fig, x, y, w, h):
    return fig.add_axes([x / W, 1 - (y + h) / H, w / W, h / H])


def loglog(ax):
    ax.set_xscale("log"); ax.set_yscale("log")


# --------------------------------------------------------------------------- panels

def panel_a(fig, d, x0, y0):
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
    n = d["n_spots"]
    for j, (key, ylab) in enumerate([("size_mb", "file size (MB)"), ("read_s", "full read (s)")]):
        ax = ax_at(fig, x0 + 10 + j * 38, y0 + 9, 28, 30)
        for f, st in FORMATS.items():
            ax.plot(n, d[key][f], ms=2.5, **st, label=f)
        loglog(ax); ax.set_xlabel("spots"); ax.set_ylabel(ylab)
    fig.legend(*ax.get_legend_handles_labels(), loc="upper left", bbox_to_anchor=((x0 + 9) / W, 1 - (y0 + 48) / H),
               ncol=3, frameon=False, columnspacing=1.0, handlelength=1.8)


def panel_c(fig, d, x0, y0):
    label(fig, x0, y0, "c"); title(fig, x0 + 5, y0 + 0.4, "Access by level")
    n = d["n_spots"]
    ax = ax_at(fig, x0 + 11, y0 + 9, 34, 32)
    lvl_col = {"trace": ORANGE, "cell": INDIGO, "chromosome": GREY}
    for lvl, (v1, v2) in d["access"].items():
        ax.plot(n, v1, color=lvl_col[lvl], ls="--", lw=0.9)
        ax.plot(n, v2, color=lvl_col[lvl], ls="-", lw=1.2, label=f"get_{lvl}")
    loglog(ax); ax.set_xlabel("spots"); ax.set_ylabel("latency (s)")
    ax.legend(frameon=False, loc="upper left", handlelength=1.5)
    ax.text(0.98, 0.03, "dashed: 1.x scan\nsolid: 2.x index", transform=ax.transAxes, ha="right", va="bottom",
            fontsize=6, color=GREY)
    ax2 = ax_at(fig, x0 + 55, y0 + 9, 22, 32)
    ax2.plot(n, d["backed_mem"]["in memory"], color=GREY, label="in memory")
    ax2.plot(n, d["backed_mem"]["backed"], color=INDIGO, label="backed")
    loglog(ax2); ax2.set_xlabel("spots"); ax2.set_ylabel("resident memory (MB)")
    ax2.legend(frameon=False, loc="upper left", handlelength=1.2)


def panel_d(fig, d, x0, y0):
    label(fig, x0, y0, "d"); title(fig, x0 + 5, y0 + 0.4, "Out-of-core analysis")
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
    label(fig, x0, y0, "e"); title(fig, x0 + 5, y0 + 0.4, "Linked contacts")
    ax = ax_at(fig, x0 + 10, y0 + 9, 10, 30)
    keys = list(d["contacts_size"])
    ax.bar(range(2), [d["contacts_size"][k] for k in keys], color=[TEAL, LGREY], width=0.6,
           edgecolor=[TEAL, GREY], hatch=["", ""], lw=0.5)
    ax.set_xticks(range(2), ["linked", "copied"], rotation=90); ax.set_ylabel("on-disk size (GB)")
    ax2 = ax_at(fig, x0 + 32, y0 + 9, 21, 30)
    c = d["agg_cells"]
    ax2.plot(c, d["agg_time"]["cold"], color=TEAL, marker="o", ms=2.5, label="first query")
    ax2.plot(c, d["agg_time"]["cached"], color=TEAL, ls="--", marker="o", ms=2.5, mfc="white", label="cached")
    loglog(ax2); ax2.set_xlabel("cells aggregated"); ax2.set_ylabel("time (s)")
    ax2.legend(frameon=False, loc="upper left", handlelength=1.5)


def panel_f(fig, d, x0, y0):
    label(fig, x0, y0, "f"); title(fig, x0 + 5, y0 + 0.4, "Round trips")
    it = d["interop"]
    ax = ax_at(fig, x0 + 21, y0 + 14, 28, 23)
    v = it["vals"]
    for i in range(v.shape[0]):
        for j in range(v.shape[1]):
            val = float(v[i, j])
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
    ax.legend(hs, ["preserved", "partial or by design", "not applicable"], loc="upper left",
              bbox_to_anchor=(-0.62, -0.04), ncol=2, frameon=False, handletextpad=0.2, columnspacing=1.0)


def main() -> None:
    import panel_a
    d = mock_data()
    fig = plt.figure(figsize=(W * MM, H * MM))
    pa_h = panel_a.H
    panel_a.draw(panel_a.C(fig, rect=(0, 1 - pa_h / H, panel_a.W / W, pa_h / H)))
    y2 = pa_h + 3
    panel_b(fig, d, 2, y2)
    panel_c(fig, d, 88, y2)
    y3 = y2 + 59
    panel_d(fig, d, 2, y3)
    panel_e(fig, d, 60, y3)
    panel_f(fig, d, 114, y3)
    fig.text(0.5, 0.28, "MOCK — placeholder data", fontsize=40, color="red", alpha=0.10,
             ha="center", va="center", rotation=30, fontweight="bold")
    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"fig2_mock.{ext}", dpi=300)
    print(HERE / "fig2_mock.pdf")


if __name__ == "__main__":
    main()
