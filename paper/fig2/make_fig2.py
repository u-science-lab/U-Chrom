"""Figure 2 — the shared index at real scale.

Two modes:

* default (DESIGN MOCK-UP): every number comes from ``mock_data()`` — a
  PLACEHOLDER that only fixes layout, plot types, axes and comparisons;
  watermarked "MOCK" → ``fig2_mock.pdf / .png``.
* ``--real``: ``load_results()`` reads the benchmark JSONs in ``results/``
  (written by ``benchmarks/fig2/*.py``) and replaces the mock values of every
  panel it has numbers for; panels without results keep their mock values and
  are tagged "mock" in the corner.  Watermarked "PARTIAL — 1.x only" until
  h5cd 2.x numbers exist → ``fig2_real.pdf / .png``.

  a  ChromData 2.0 schematic (``panel_a.py``; no data)
  b  storage: file size and full-read time vs n_spots, h5cd vs common formats
     ("h5cd 2.x" drawn only when present in the results)
  c  access by level: get_trace / get_cell / get_chrom latency; 1.x scan (dashed),
     2.x index (solid, only when present); resident memory after loading
  d  out-of-core population analysis — not measurable before streaming (mock)
  e  linked contacts: on-disk size linked vs copied; pseudo-bulk time vs cells aggregated
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
GREY, LGREY, INK, RED = "#8a8f98", "#c9ccd1", "#2b2f36", "#c0392b"
# comparison formats: h5cd in indigo (2.x solid, 1.x dashed), others in greys
FORMATS = {
    "FOF-CT / CSV": dict(color="#9aa0a8", ls="-", marker="o"),
    "Parquet": dict(color="#6b7079", ls="-", marker="s"),
    "AnnData (spots as obs)": dict(color=PURPLE, ls="-", marker="^"),
    "h5cd 1.x": dict(color=INDIGO, ls="--", marker="D", mfc="white"),
    "h5cd 2.x": dict(color=INDIGO, ls="-", marker="D"),
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
    size = {"FOF-CT / CSV": 9e-5, "Parquet": 3e-5, "AnnData (spots as obs)": 5e-5, "h5cd 1.x": 4e-5, "h5cd 2.x": 2e-5}
    read = {"FOF-CT / CSV": 2e-6, "Parquet": 2e-7, "AnnData (spots as obs)": 6e-7, "h5cd 1.x": 5e-7, "h5cd 2.x": 3e-7}
    d["storage"] = {f: {"n": n, "size_mb": n * size[f], "read_s": n * read[f], "replicated": np.zeros(5, bool)}
                    for f in FORMATS}
    d["access"] = {  # version -> level -> (n, latency)
        "1.x": {lvl: (n, n * k1) for lvl, k1 in [("trace", 4e-8), ("cell", 4e-8), ("chromosome", 5e-8)]},
        "2.x": {lvl: (n, np.full_like(n, k2) * (1 + 0.05 * np.log10(n)))
                for lvl, k2 in [("trace", 2e-4), ("cell", 1e-3), ("chromosome", 2e-2)]},
    }
    d["resident_mem"] = {"in memory": (n, n * 6e-5), "backed": (n, np.full_like(n, 60.0))}
    t = np.logspace(3, 7, 5)
    d["n_traces"] = t
    d["peak_mem"] = {"in memory": t * 2e-3 + 50, "streaming": np.minimum(t * 2e-3 + 50, 800)}
    d["budget_mb"] = 1000
    x = rng.normal(size=400)
    d["identity"] = (x, x + rng.normal(scale=1e-6, size=400))
    d["contacts_size"] = {"linked": (0.05, 3.0), "copied (1.x)": (11.0, 0), "copied (gzip)": (3.0, 0)}  # GB (own, external)
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
        for label, s in c["series"].items():
            ver = "2.x" if label.startswith("h5cd 2") else "1.x"
            pts = s["points"]
            n = np.array([p["n_spots"] for p in pts], float)
            acc[ver] = {lvl: (n, np.array([p[key]["latency_s"]["median"] for p in pts]),
                              np.array([p[key]["latency_s"]["q1"] for p in pts]),
                              np.array([p[key]["latency_s"]["q3"] for p in pts]))
                        for lvl, key in (("trace", "trace"), ("cell", "cell"), ("chromosome", "chrom"))}
            if ver == "1.x":
                mem["in memory"] = (n, np.array([p["rss_after_open_mb"] - p["baseline_rss_mb"] for p in pts]))
            elif "backed" in label:
                mem["backed"] = (n, np.array([p["rss_after_open_mb"] - p["baseline_rss_mb"] for p in pts]))
        out["access"], out["resident_mem"] = acc, mem
        out["real"].add("c")
    e = _load("e_contacts")
    if e:
        s = e["size"]
        gb = 1 / 2**30
        out["contacts_size"] = {
            "linked": (s["h5cd_linked_bytes"] * gb, s["scool_bytes"] * gb),
            "copied (1.x)": (s["copied_h5cd_1x_settings_bytes"] * gb, 0),
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
    for j, (key, ylab) in enumerate([("size_mb", "file size (MB)"), ("read_s", "full read (s)")]):
        ax = ax_at(fig, x0 + 10 + j * 38, y0 + 9, 28, 30)
        for f, sty in FORMATS.items():
            if f not in st:  # e.g. "h5cd 2.x" before it exists: not drawn
                continue
            s = st[f]
            ax.plot(s["n"], s[key], ms=2.5, **sty, label=f)
            if key == "read_s" and "read_lo" in s:
                ax.vlines(s["n"], s["read_lo"], s["read_hi"], color=sty["color"], lw=0.5)
            rep = s["replicated"]
            if rep.any():
                ax.scatter(s["n"][rep], s[key][rep], s=16, facecolor="none", edgecolor=RED, lw=0.5, zorder=5)
        loglog(ax); ax.set_xlabel("spots"); ax.set_ylabel(ylab)
    handles, labels = ax.get_legend_handles_labels()
    if any(s["replicated"].any() for s in st.values()):
        handles.append(plt.Line2D([], [], marker="o", ls="", mfc="none", mec=RED, mew=0.5, ms=4))
        labels.append("replicated real cells")
    fig.legend(handles, labels, loc="upper left", bbox_to_anchor=((x0 + 9) / W, 1 - (y0 + 48) / H),
               ncol=3, frameon=False, columnspacing=1.0, handlelength=1.8)


def panel_c(fig, d, x0, y0):
    label(fig, x0, y0, "c"); title(fig, x0 + 5, y0 + 0.4, "Access by level", mock=_mock(d, "c"))
    ax = ax_at(fig, x0 + 11, y0 + 9, 34, 32)
    lvl_col = {"trace": ORANGE, "cell": INDIGO, "chromosome": GREY}
    acc = d["access"]
    for ver, ls, lw in (("1.x", "--", 0.9), ("2.x", "-", 1.2)):
        for lvl, v in acc.get(ver, {}).items():
            n, lat = v[0], v[1]
            ax.plot(n, lat, color=lvl_col[lvl], ls=ls, lw=lw, label=f"get_{lvl}" if ver == "1.x" else None)
            if len(v) > 2:
                ax.fill_between(n, v[2], v[3], color=lvl_col[lvl], alpha=0.15, lw=0)
    loglog(ax); ax.set_xlabel("spots"); ax.set_ylabel("latency (s)")
    ax.legend(frameon=False, loc="upper left", handlelength=1.5)
    key = "dashed: 1.x scan" + ("\nsolid: 2.x index" if "2.x" in acc else "")
    ax.text(0.98, 0.03, key, transform=ax.transAxes, ha="right", va="bottom", fontsize=6, color=GREY)
    ax2 = ax_at(fig, x0 + 55, y0 + 9, 22, 32)
    for k, color in (("in memory", GREY), ("backed", INDIGO)):
        if k in d["resident_mem"]:
            n, m = d["resident_mem"][k]
            ax2.plot(n, m, color=color, label=k)
    loglog(ax2); ax2.set_xlabel("spots"); ax2.set_ylabel("resident memory (MB)")
    ax2.legend(frameon=False, loc="upper left", handlelength=1.2)


def panel_d(fig, d, x0, y0):
    label(fig, x0, y0, "d"); title(fig, x0 + 5, y0 + 0.4, "Out-of-core analysis", mock=_mock(d, "d"))
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
    ax = ax_at(fig, x0 + 10, y0 + 9, 13, 30)
    keys = list(d["contacts_size"])
    own = [d["contacts_size"][k][0] for k in keys]
    ext = [d["contacts_size"][k][1] for k in keys]
    x = np.arange(len(keys))
    ax.bar(x, own, color=[TEAL] + [LGREY] * (len(keys) - 1), width=0.6, edgecolor=[TEAL] + [GREY] * (len(keys) - 1),
           lw=0.5)
    ax.bar(x, ext, bottom=own, color="white", width=0.6, edgecolor=TEAL, hatch="////", lw=0.5)
    ax.set_xticks(x, [k.replace(" (", "\n(") for k in keys], rotation=90, fontsize=5.5)
    ax.set_ylabel("on-disk size (GB)")
    if any(ext):
        ax.text(0, own[0] + ext[0], "scool\n(external)", ha="center", va="bottom", fontsize=5, color=TEAL)
    ax2 = ax_at(fig, x0 + 32, y0 + 9, 21, 30)
    c = d["agg_cells"]
    ax2.plot(c, d["agg_time"]["cold"], color=TEAL, marker="o", ms=2.5, label="first query")
    ax2.plot(c, d["agg_time"]["cached"], color=TEAL, ls="--", marker="o", ms=2.5, mfc="white", label="cached")
    loglog(ax2); ax2.set_xlabel("cells aggregated"); ax2.set_ylabel("time (s)")
    ax2.legend(frameon=False, loc="upper left", handlelength=1.5)


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
    y3 = y2 + 59
    panel_d(fig, d, 2, y3)
    panel_e(fig, d, 60, y3)
    panel_f(fig, d, 114, y3)
    if not real:
        fig.text(0.5, 0.28, "MOCK — placeholder data", fontsize=40, color="red", alpha=0.10,
                 ha="center", va="center", rotation=30, fontweight="bold")
        stem = "fig2_mock"
    else:
        has_2x = (("b" in d["real"] and "h5cd 2.x" in d["storage"])
                  or ("c" in d["real"] and "2.x" in d["access"]))
        if not has_2x:
            fig.text(0.5, 0.28, "PARTIAL — 1.x only", fontsize=40, color="red", alpha=0.10,
                     ha="center", va="center", rotation=30, fontweight="bold")
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
