"""Figure 3 — reconstruction from contacts, on each method's own benchmark data.

Real results are read from ``results/`` (benchmark JSONs, ``fig3_panels.npz`` from
``prepare_fig3.py``).  Parts whose runs are not finished yet are drawn from
placeholder values inside a dashed frame (``mock_frame``); nothing else is mocked.
One panel per letter:

  a  3-D render of the U-Chrom reconstruction of Stevens 2017 Cell 1 (U-Chrom web browser);
     published vs U-Chrom from four viewpoints: make_figS_fig3_views.py
  b  NucDynamics (native engine) vs the published Stevens 2017 structure, Cell 1
  c  ensemble precision, 8 cells: published / original code / U-Chrom
  d  NucDynamics speed, original vs U-Chrom (CPU, GPU)
  e  MDS vs miniMDS agreement (Rao 2014 IMR90 chr21)
  f  MDS runtime
  g  GEM-FISH vs the paper (Wang 2016 FISH, chr21)
  h  held-out error vs FISH constraints used (placeholder: not run yet)
  i  held-out FISH error per chromosome, with HIPPS

The imaging -> contacts comparison (former panel b) is Supplementary Fig. S2
(``make_figS_fig3.py``).

    python paper/fig3/make_fig3.py      # -> fig3.pdf / .png
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
FEAS = HERE / "feasibility"
MM = 1 / 25.4
W, H = 170.0, 192.0

mpl.rcParams.update({
    "pdf.fonttype": 42, "font.family": "sans-serif", "font.sans-serif": ["Arial"],
    "font.size": 7, "axes.titlesize": 7, "axes.labelsize": 7,
    "xtick.labelsize": 6, "ytick.labelsize": 6, "legend.fontsize": 6,
    "axes.linewidth": 0.5, "xtick.major.width": 0.5, "ytick.major.width": 0.5,
    "xtick.major.size": 2, "ytick.major.size": 2, "axes.spines.top": False, "axes.spines.right": False,
    "lines.linewidth": 1.0,
})
ORANGE, TEAL, PURPLE, INDIGO = "#e07a3f", "#2a9d8f", "#8e7cc3", "#34568b"
GREY, LGREY, INK = "#8a8f98", "#c9ccd1", "#2b2f36"
OURS, PAPER = INDIGO, "#9aa0a8"          # U-Chrom vs the original / published result
OTHER = "#c9a227"                        # external baseline (HIPPS / DIMES)


# --------------------------------------------------------------------------- data

def _j(path: Path):
    return json.loads(path.read_text())


def _mean_scores(rows, key=lambda s: s["model"]):
    acc = defaultdict(list)
    for s in rows:
        acc[key(s)].append((s["re_train"], s["re_heldout"]))
    return {k: np.mean(v, axis=0) for k, v in acc.items()}


def load_results() -> dict:
    d = {}
    # a1 NucDynamics: native engine (Sherlock, full schedule, 10 models) vs GEO models
    sc = _j(RES / "a_nucdyn_score_all.json")["cells"]
    # ensemble precision as in Stevens et al. 2017 ED Table 2: RMSD of each model to the superposed
    # ensemble mean (mirror allowed); for the GEO models this reproduces ED Table 2 (0.41 ... 1.75)
    d["nd_prec_pub"] = [c["published"]["rmsd_to_mean_mirror_mean"] for c in sc]
    d["nd_prec_orig"] = [c["orig_master_full"]["rmsd_to_mean_mirror_mean"] for c in sc]
    d["nd_prec_ours"] = [c["native_gpu_full"]["rmsd_to_mean_mirror_mean"] for c in sc]
    p = np.load(RES / "fig3_panels.npz")
    d["nd_scatter"] = (p["nd_pub_d"], p["nd_ours_d"])
    sp = _j(RES / "a_nucdyn_speed_cpu_same_node.json")     # Cell 1, full schedule, one node
    d["nd_time"] = {"labels": ["original", "U-Chrom", "U-Chrom"], "hw": ["10 CPU", "10 CPU", "1 GPU"],
                    "t": [sp["orig_10models_10cores"]["wall_seconds"] / 60,
                          sp["native_10models_10threads"]["wall_seconds"] / 60,
                          sp["native_gpu_10models_h100"]["wall_seconds"] / 60]}
    # a2 MDS vs miniMDS, Rao 2014 IMR90 chr21 (feasibility run)
    m = _j(FEAS / "a_mds_vs_minimds_imr90_chr21.json")
    rs = ("100kb", "25kb")
    d["mds"] = {"res": ["100 kb", "25 kb"],
                "ours_r": [m[r]["minimds_full_vs_uchrom"]["pearson"] for r in rs],
                "seed_r": [m[r]["minimds_full_rep1_vs_rep2"]["pearson"] for r in rs],
                "t_ours": [m[r]["uchrom_run_mds_s"] for r in rs],
                "t_orig": [np.mean([m[r]["minimds_full_s"], m[r]["minimds_full_rep2_s"]]) for r in rs]}
    # a3 / c: GEM-FISH (3 cell splits) and HIPPS, relative error vs FISH
    hipps = _mean_scores(_j(RES / "c_hipps_wang2016.json")["scores"], key=lambda s: (s["chrom"], s["model"]))
    d["joint"] = {}
    for c in ("chr20", "chr21", "chr22"):
        g = _mean_scores(_j(RES / f"c_gemfish_wang2016_{c}.json"))
        d["joint"][c] = {"U-Chrom, Hi-C only": g["uchrom hic_only"], "U-Chrom, Hi-C + FISH": g["uchrom hic+fish"],
                         "GEM-FISH (paper model)": g["paper GEM-FISH final (nm, no rescale)"],
                         "HIPPS, Hi-C only": hipps[(c, "hipps tad-level")]}
    # paper values (Abbas et al. 2019): Table 1 (training cells) and Supp. Table 9 (held-out, chr21)
    d["gemfish_paper"] = {"GEM (paper)": [0.30, 0.362], "GEM-FISH (paper)": [0.14, 0.188]}
    # b maps and correlations
    d["maps"] = (p["hic_map"], p["img_map"], p["med_dist"])
    bd = _j(RES / "b_dimes.json")["results"]
    by = {r["pair"]: r for r in bd}
    imr = by["Bintu2018 IMR90 chr21:28-30Mb"]["by_radius"]["200"]
    k5 = by["Bintu2018 K562 chr21:28-30Mb"]["by_radius"]["200"]
    ci = by["control: IMR90 imaging vs K562 Hi-C, chr21:28-30Mb"]["by_radius"]["200"]
    ck = by["control: K562 imaging vs IMR90 Hi-C, chr21:28-30Mb"]["by_radius"]["200"]
    d["oe"] = np.array([[imr["uchrom"]["pearson_log_oe"], ci["uchrom"]["pearson_log_oe"]],
                        [ck["uchrom"]["pearson_log_oe"], k5["uchrom"]["pearson_log_oe"]]])
    su = [r for r in bd if r["pair"].startswith("Su2020")][0]["by_radius"]["200"]
    tk = [r for r in bd if r["pair"].startswith("Takei2021")][0]["by_radius_um"]["0.2"]
    d["datasets"] = [(n, x["uchrom"]["pearson_log"], x["dimes"]["pearson_log"]) for n, x in (
        ("IMR90 chr21 2 Mb\n(Bintu 2018)", imr), ("K562 chr21 2 Mb\n(Bintu 2018)", k5),
        ("IMR90 chr21 whole\n(Su 2020)", su), ("mESC 20 loci\n(Takei 2021)", tk))]
    # c curve: not run yet -> placeholder between the two measured endpoints (0 % and the 90 % split)
    f = np.array([0, 0.05, 0.1, 0.25, 0.5, 1.0])
    shape = (1 - np.exp(-f / 0.25)) / (1 - np.exp(-4))
    d["frac_curve"] = {"frac": f, **{c: v["U-Chrom, Hi-C only"][1] - (v["U-Chrom, Hi-C only"][1]
                                                                      - v["U-Chrom, Hi-C + FISH"][1]) * shape
                                     for c, v in d["joint"].items()}}
    return d


# --------------------------------------------------------------------------- helpers

def ax_at(fig, x, y, w, h):
    return fig.add_axes([x / W, 1 - (y + h) / H, w / W, h / H])


def label(fig, x, y, s):
    fig.text(x / W, 1 - y / H, s, fontsize=10, fontweight="bold", va="top")


def title(fig, x, y, s, sub=None, size=8.5):
    fig.text(x / W, 1 - y / H, s, fontsize=size, fontweight="bold", va="top")
    if sub:
        fig.text(x / W, 1 - (y + 4.2) / H, sub, fontsize=6, color=GREY, va="top")


def sub(fig, x, y, s, note=None):
    fig.text(x / W, 1 - y / H, s, fontsize=7, fontweight="bold", color=INK, va="top")
    if note:
        fig.text(x / W, 1 - (y + 3.2) / H, note, fontsize=6, color=GREY, va="top")


def mock_frame(fig, x, y, w, h, note="placeholder: run not finished"):
    """Dashed frame (mm) around a region drawn from placeholder values."""
    fig.add_artist(Rectangle((x / W, 1 - (y + h) / H), w / W, h / H, transform=fig.transFigure, fill=False,
                             ls=(0, (3, 2)), lw=0.6, ec=GREY))
    fig.text((x + w - 1) / W, 1 - (y + 1) / H, note, fontsize=5, color=GREY, ha="right", va="top", style="italic")


def rot(axis: str, deg: float) -> np.ndarray:
    """Right-handed rotation matrix about a screen axis ('x' right, 'y' up, 'z' to the viewer)."""
    c, s_ = np.cos(np.radians(deg)), np.sin(np.radians(deg))
    return {"x": np.array([[1, 0, 0], [0, c, -s_], [0, s_, c]]),
            "y": np.array([[c, 0, s_], [0, 1, 0], [-s_, 0, c]]),
            "z": np.array([[c, -s_, 0], [s_, c, 0], [0, 0, 1]])}[axis]


def triad(fig, x, y, size, R=np.eye(3), note=None):
    """3-D axes glyph (mm): the structure's own x / y / z axes after rotation R, drawn in a
    slightly oblique projection so that the axis pointing at the viewer stays visible."""
    ax = ax_at(fig, x, y, size, size)
    P = rot("x", 22) @ rot("y", -35)                 # fixed oblique view of the glyph
    cols = {"x": "#c0392b", "y": "#27ae60", "z": "#2e6fbf"}
    tips = (P @ R @ np.eye(3)).T                        # rows: rotated unit axes
    for (name, col), t in sorted(zip(cols.items(), tips), key=lambda it: it[1][2]):   # far first
        ax.annotate("", xy=(t[0], t[1]), xytext=(0, 0),
                    arrowprops=dict(arrowstyle="-|>", lw=1.1, color=col, mutation_scale=7, shrinkA=0, shrinkB=0,
                                    alpha=1.0 if t[2] > -0.3 else 0.55))
        ax.text(t[0] * 1.25, t[1] * 1.25, name, color=col, fontsize=6, ha="center", va="center",
                fontweight="bold")
    ax.set_xlim(-1.3, 1.3); ax.set_ylim(-1.3, 1.3); ax.set_aspect("equal"); ax.axis("off")
    if note:
        ax.text(0.5, -0.12, note, transform=ax.transAxes, ha="center", va="top", fontsize=5.5, color=GREY)
    return ax


# --------------------------------------------------------------------------- panels

def head_(fig, x, y, letter, name, note=None):
    """Panel letter + short title (+ grey note), top-left at (x, y) mm."""
    label(fig, x, y, letter)
    sub(fig, x + 5, y + 0.8, name, note)


def p_renders(fig, d, x, y):
    """3-D render from the U-Chrom web browser (``build_render_cd.py``; pane capture)."""
    head_(fig, x, y, "a", "U-Chrom reconstruction", "Stevens 2017 Cell 1, 100 kb; by chromosome")
    img = plt.imread(HERE / "renders" / "cell1_uchrom_crop.png")
    ax = ax_at(fig, x + 6, y + 10, 40, 40 * img.shape[0] / img.shape[1])
    ax.imshow(img); ax.axis("off")
    triad(fig, x + 0, y + 44, 11)


def p_nd_scatter(fig, d, x, y):
    head_(fig, x, y, "b", "NucDynamics vs published", "Stevens 2017 Cell 1, 100 kb")
    ax = ax_at(fig, x + 12, y + 11, 30, 30)
    xs, ys = d["nd_scatter"]
    ax.hexbin(xs, ys, gridsize=28, cmap=LinearSegmentedColormap.from_list("b", ["#ffffff", INDIGO]),
              mincnt=1, lw=0, bins="log")
    lim = float(np.percentile(np.r_[xs, ys], 99.5))
    ax.plot([0, lim], [0, lim], color=GREY, lw=0.6, ls="--")
    ax.set_xlim(0, lim); ax.set_ylim(0, lim)
    ax.set_xlabel("published distance (radii)"); ax.set_ylabel("U-Chrom distance (radii)")
    ax.text(0.04, 0.96, f"r = {np.corrcoef(xs, ys)[0, 1]:.3f}", transform=ax.transAxes, fontsize=6, va="top")


def p_nd_precision(fig, d, x, y):
    head_(fig, x, y, "c", "Ensemble precision", "8 cells, 10 models each; metric of ED Table 2")
    bx = ax_at(fig, x + 12, y + 11, 36, 30)
    cells = np.arange(1, 9)
    bx.scatter(cells, d["nd_prec_pub"], s=12, color=PAPER, label="published", zorder=3)
    bx.scatter(cells, d["nd_prec_orig"], s=14, facecolor="none", edgecolor="#6b7079", lw=0.7,
               label="original code", zorder=3)
    bx.scatter(cells, d["nd_prec_ours"], s=12, color=OURS, marker="D", label="U-Chrom", zorder=3)
    bx.set_yscale("log"); bx.set_xticks(cells, [str(c) for c in cells])
    bx.set_yticks([0.5, 1, 2, 5], ["0.5", "1", "2", "5"]); bx.minorticks_off()
    bx.set_xlabel("cell"); bx.set_ylabel("RMSD to ensemble mean (radii)")
    bx.legend(frameon=False, fontsize=5.5, ncol=3, loc="upper left", bbox_to_anchor=(-0.25, -0.22),
              handletextpad=0.1, columnspacing=0.8)


def p_nd_speed(fig, d, x, y):
    head_(fig, x, y, "d", "NucDynamics speed", "Cell 1, 10 models, full schedule")
    t = d["nd_time"]
    tx = ax_at(fig, x + 14, y + 11, 34, 30)
    for k_, (v, col) in enumerate(zip(t["t"], ["#6b7079", OURS, OURS])):
        tx.bar(k_, v, 0.65, color=col)
        tx.text(k_, v * 1.3, f"{v:.0f}" if v >= 10 else f"{v:.1f}", ha="center", fontsize=5.5)
    tx.set_yscale("log"); tx.set_ylim(top=max(t["t"]) * 5)
    tx.set_xticks(range(3), [f"{a}\n{b}" for a, b in zip(t["labels"], t["hw"])], fontsize=5.5)
    tx.set_xlim(-0.6, 2.6)
    tx.set_ylabel("wall time (min)")


def p_mds_r(fig, d, x, y):
    head_(fig, x, y, "e", "MDS vs miniMDS", "Rao 2014 IMR90 chr21")
    m = d["mds"]
    ax = ax_at(fig, x + 12, y + 11, 24, 30)
    xx = np.arange(2)
    ax.bar(xx - 0.18, m["seed_r"], 0.34, color=PAPER, label="miniMDS, seed vs seed")
    ax.bar(xx + 0.18, m["ours_r"], 0.34, color=OURS, label="U-Chrom vs miniMDS")
    ax.set_xticks(xx, m["res"]); ax.set_ylim(0.9, 1.0); ax.set_ylabel("distance-matrix r")
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(-0.45, -0.18), fontsize=5.5, handlelength=1)


def p_mds_time(fig, d, x, y):
    head_(fig, x, y, "f", "MDS runtime", "same input as e")
    m = d["mds"]
    xx = np.arange(2)
    tx = ax_at(fig, x + 12, y + 11, 22, 30)
    tx.bar(xx - 0.18, m["t_orig"], 0.34, color=PAPER, label="miniMDS")
    tx.bar(xx + 0.18, m["t_ours"], 0.34, color=OURS, label="U-Chrom")
    tx.set_yscale("log"); tx.set_xticks(xx, m["res"]); tx.set_ylabel("runtime (s)")
    tx.legend(frameon=False, loc="upper left", bbox_to_anchor=(-0.3, -0.18), fontsize=5.5, handlelength=1)


def p_gemfish(fig, d, x, y):
    head_(fig, x, y, "g", "GEM-FISH vs the paper", "Wang 2016 chr21")
    j21 = d["joint"]["chr21"]
    vals = {"GEM (paper)": d["gemfish_paper"]["GEM (paper)"], "U-Chrom, Hi-C only": j21["U-Chrom, Hi-C only"],
            "GEM-FISH (paper)": d["gemfish_paper"]["GEM-FISH (paper)"],
            "U-Chrom, Hi-C + FISH": j21["U-Chrom, Hi-C + FISH"]}
    ax = ax_at(fig, x + 12, y + 11, 42, 30)
    w = 0.19
    for k_, ((key, v), col) in enumerate(zip(vals.items(), [PAPER, "#a9b8d6", "#6b7079", OURS])):
        ax.bar(np.arange(2) + (k_ - 1.5) * w, v, w, color=col, label=key)
    ax.set_xticks(range(2), ["training cells", "held-out cells"]); ax.set_ylabel("relative error vs FISH")
    ax.legend(frameon=False, fontsize=5.5, ncol=2, loc="upper left", bbox_to_anchor=(-0.1, -0.16),
              handlelength=1, columnspacing=0.8)


def p_frac_curve(fig, d, x, y):
    head_(fig, x, y, "h", "FISH fraction vs error", "GEM-FISH, chr20–22")
    f = d["frac_curve"]
    ax = ax_at(fig, x + 14, y + 11, 30, 30)
    for ch, col in (("chr20", PURPLE), ("chr21", INDIGO), ("chr22", TEAL)):
        ax.plot(f["frac"] * 100, f[ch], color=col, marker="o", ms=2.5)
        ax.text(102, f[ch][-1] + {"chr20": 0.004, "chr21": -0.004, "chr22": 0.001}[ch], ch, fontsize=6,
                color=col, va="center")
    ax.set_xlabel("FISH constraints used (%)"); ax.set_ylabel("held-out relative error")
    mock_frame(fig, x + 1, y + 8, 49, 46)


def p_heldout(fig, d, x, y):
    head_(fig, x, y, "i", "Held-out FISH error", "held-out 10 % of cells, 3 splits")
    keys = ["U-Chrom, Hi-C only", "U-Chrom, Hi-C + FISH", "GEM-FISH (paper model)", "HIPPS, Hi-C only"]
    ax = ax_at(fig, x + 12, y + 11, 44, 30)
    chroms = ["chr20", "chr21", "chr22"]
    w = 0.2
    for k_, (key, col) in enumerate(zip(keys, ["#a9b8d6", OURS, "#6b7079", OTHER])):
        ax.bar(np.arange(3) + (k_ - 1.5) * w, [d["joint"][c][key][1] for c in chroms], w, color=col, label=key)
    ax.set_xticks(range(3), chroms); ax.set_ylabel("held-out relative error")
    ax.legend(frameon=False, fontsize=5.5, ncol=1, loc="upper left", bbox_to_anchor=(-0.25, -0.16),
              handlelength=1)


def main() -> None:
    d = load_results()
    fig = plt.figure(figsize=(W * MM, H * MM))
    p_renders(fig, d, 0, 2)
    p_nd_scatter(fig, d, 54, 2)
    p_nd_precision(fig, d, 108, 2)
    p_nd_speed(fig, d, 0, 64)
    p_mds_r(fig, d, 58, 64)
    p_mds_time(fig, d, 110, 64)
    p_gemfish(fig, d, 0, 124)
    p_frac_curve(fig, d, 62, 124)
    p_heldout(fig, d, 114, 124)
    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"fig3.{ext}", dpi=300)
    print(HERE / "fig3.pdf")


if __name__ == "__main__":
    main()
