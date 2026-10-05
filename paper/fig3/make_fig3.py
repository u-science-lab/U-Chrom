"""Figure 3 — EMber (U-Chrom) for single-cell reconstruction, and fast IGM for populations.

Real results are read from ``results/``.

  a  EMber diploid at 5 kb on the deepest scMicro-C GM12878 cell (Wu 2025): U-Chrom web-browser pane captures
     (whole nucleus by chromosome; chr1 homologs; a 3 Mb zoom at 5 kb and, exploratory, 2 kb); numbers in
     ``results/highres/summary.json`` / Supplementary ``make_figS_fig3_highres.py``
  b  time for one model vs resolution: EMber (U-Chrom; GPU, CPU 16 / 1 threads), original NucDynamics,
     hickit, Si-C (same input, one CPU model / one H100; runs over the 48 h cap drawn as censored)
  c  held-out contact prediction (8 cells x 3 folds) per genomic separation
  d  imaging-truth simulations (Su 2020 chr21, Takei 2021 1 Mb): distance agreement
  e  IGM: U-Chrom (native) vs original populations (WTC11 demo, S = 200 / 1,000)
  f  IGM speed: original (64 cores) vs U-Chrom (1 GPU)
  g  population size: seed-to-seed agreement and fit to input of trans contacts vs S (200-5,000)

Supplementary figures: ``make_figS_fig3_*.py`` (``make_figS_fig3_all.py`` builds the set).

    python paper/fig3/make_fig3.py      # -> fig3.pdf / .png
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
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
OURS2 = "#7f9bd0"                        # U-Chrom, second backend (CPU)
ORIG = "#6b7079"                         # original code
OTHER = "#c9a227"                        # external baseline (HIPPS / DIMES)
NEW, NEW_LABEL = "#d1495b", "EMber (U-Chrom)"  # the new single-cell method (U-Chrom EMber; engine protocol "robust")
# methods of the single-cell benchmark: key -> (label, colour)
SC_METHODS = {"robust": (NEW_LABEL, NEW), "nucdyn_gpu": ("U-Chrom GPU", OURS), "nucdyn_cpu": ("U-Chrom CPU", OURS2),
              "orig": ("NucDynamics", ORIG), "sic": ("Si-C", PURPLE), "hickit": ("hickit (Dip-C)", TEAL),
              "pop_mean": ("population mean", OTHER), "random_polymer": ("random polymer", LGREY)}


# --------------------------------------------------------------------------- data

def _j(path: Path):
    return json.loads(path.read_text())


def _mean_scores(rows, key=lambda s: s["model"]):
    acc = defaultdict(list)
    for s in rows:
        acc[key(s)].append((s["re_train"], s["re_heldout"]))
    return {k: np.mean(v, axis=0) for k, v in acc.items()}


def load_core() -> dict:
    d = {}
    # a1 NucDynamics: native engine (Sherlock, full schedule, 10 models) vs GEO models
    sc = _j(RES / "a_nucdyn_score_all.json")["cells"]
    # ensemble precision as in Stevens et al. 2017 ED Table 2: RMSD of each model to the superposed
    # ensemble mean (mirror allowed); for the GEO models this reproduces ED Table 2 (0.41 ... 1.75)
    d["nd_prec_pub"] = [c["published"]["rmsd_to_mean_mirror_mean"] for c in sc]
    d["nd_prec_orig"] = [c["orig_master_full"]["rmsd_to_mean_mirror_mean"] for c in sc]
    d["nd_prec_ours"] = [c["native_gpu_full"]["rmsd_to_mean_mirror_mean"] for c in sc]
    rb = {c["cell"]: c["robust"]["rmsd_to_mean_mirror_mean"] for c in _j(RES / "robust" / "score_all.json")["cells"]}
    d["nd_prec_new"] = [rb[k] for k in range(1, 9)]
    p = np.load(RES / "fig3_panels.npz")
    d["nd_scatter"] = (p["nd_pub_d"], p["nd_ours_d"])
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
    return d


BANDS = [("2-4", "0.2–0.4"), ("4-16", "0.4–1.6"), ("16-64", "1.6–6.4"), ("64-256", "6.4–26"), ("256-inf", "> 26")]


def load_screcon(d: dict) -> None:
    """Single-cell benchmark tables (``benchmarks/screcon/aggregate.py`` on Sherlock)."""
    h = pd.concat([pd.read_csv(RES / "screcon" / "heldout.csv"),
                   pd.read_csv(RES / "robust" / "heldout.csv").drop(columns="set")], ignore_index=True)
    med = h[h.score == "median"]
    band = med[med.subset == "cis_band"]
    d["ho_band"] = band.groupby(["method", "band"]).roc_auc.agg(["mean", "min", "max"])
    d["ho_trans"] = med[med.subset == "trans"].groupby("method").roc_auc.mean()
    d["ho_cis"] = med[med.subset == "cis"].groupby("method").roc_auc.mean()
    d["ho_n"] = med[["cell", "fold"]].drop_duplicates().shape[0]
    s = pd.concat([pd.read_csv(RES / "screcon" / "sim.csv"),
                   pd.read_csv(RES / "robust" / "sim.csv").drop(columns="set")], ignore_index=True)
    keys = ["truth", "depth_per_mb", "rc_rel", "eps", "seed"]
    out = {}
    for ds, g in s.groupby("dataset"):
        meth = g[g.kind == "method"]
        full = [m for m in meth.method.unique() if meth[meth.method == m].shape[0] == meth.groupby("method").size().max()]
        # matched cases: every method that ran on this dataset has a result
        ran = list(meth.method.unique())
        ok = meth.groupby(keys).method.nunique()
        ok = ok[ok == len(ran)].index
        gg = g.set_index(keys).loc[g.set_index(keys).index.isin(ok)].reset_index()
        out[ds] = {"n_cases": len(ok), "ran": ran, "complete": full,
                   "spearman_cis": gg.groupby("method").med_dist_spearman_cis.agg(["mean", "std"]),
                   "rmsd_rel": gg.groupby("method").med_rmsd_rel.agg(["mean", "std"]),
                   "by_depth": gg.groupby(["depth_per_mb", "method"]).med_dist_spearman_cis.mean().unstack()}
    d["sim"] = out


def load_igm(d: dict) -> None:
    """IGM demo (WTC11 2 Mb): native vs original populations and wall times."""
    D = RES / "igm_demo"
    cmp_ = {S: _j(D / f"compare_S{S}.json") for S in (200, 1000)}
    pairs = {}
    for S, c in cmp_.items():
        for r in c["pairs"]:
            pairs.setdefault((S, r["kind"]), []).append(r)
    d["igm_pairs"] = pairs
    d["igm_fit"] = {S: c["populations"] for S, c in cmp_.items()}
    # population-size sweep: native seeds 1-3 at every S (+ original at 200 / 1,000)
    sweep = {}
    for S in (200, 500, 1000, 2000, 5000):
        c = _j(D / f"compare_S{S}.json")
        sweep[S] = {"seed": [r["pearson_contact_inter"] for r in c["pairs"] if r["kind"] == "ours"],
                    "vs_orig": [r["pearson_contact_inter"] for r in c["pairs"] if r["kind"] == "igm-ours"],
                    "fit": [p["fit"]["pearson_inter_restrained"] for k, p in c["populations"].items()
                            if k.startswith("ours")],
                    "minutes": [_j(p)["seconds_wall"] / 60 for p in sorted(D.glob(f"ours_gpu_S{S}_s*/summary.json"))]}
    d["igm_sweep"] = sweep
    t_ours = {S: [_j(p)["seconds_wall"] / 60 for p in sorted(D.glob(f"ours_gpu_S{S}_s*/summary.json"))]
              for S in (200, 1000)}
    t_orig = {S: [_j(p)["seconds_wall"] / 60 for p in sorted(D.glob(f"orig_S{S}_s*/timing.json"))]
              for S in (200, 1000)}
    d["igm_time"] = {"ours": t_ours, "orig": t_orig,
                     "orig_cores": _j(next(D.glob("orig_S200_s*/timing.json")))["cores"]}


def load_consensus(d: dict) -> None:
    """Consensus vs Su 2020 imaging: preliminary laptop scoring (300 imaged cells)."""
    rows = {}
    for res, tag in (("1 Mb", "1mb"), ("250 kb", "250kb")):
        m = _j(RES / "consensus" / f"laptop_su300__imr90_genome_{tag}_score.json")["models"]
        for k, v in m.items():
            dist = v.get("distance", {})
            if "cis" in dist:
                rows[(res, k)] = (dist["cis"]["spearman"], dist.get("trans", {}).get("spearman", np.nan))
    d["cons"] = rows
    d["cons_runs"] = {p.stem: _j(p) for p in sorted((RES / "consensus").glob("imr90*.json"))}


def load_speed(d: dict) -> None:
    """One-model wall time per method x resolution (``benchmarks/fig3/speed_one_model.py``)."""
    sp = _j(RES / "speed_one_model.json")
    rb = _j(RES / "robust" / "speed_one_model.json")["table"]
    sp["rows"] = [r for r in sp["rows"] if not r["method"].startswith("robust")] + [
        {"method": r["method"], "threads": r["threads"], "res": r["res"], "status": "ok",
         "median_wall_seconds": r["median_seconds"]} for r in rb]
    d["speed1"] = sp


def load_results() -> dict:
    d = load_core()
    load_speed(d)
    load_screcon(d)
    load_igm(d)
    load_highres(d)
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


def row_title(fig, y, s):
    fig.text(0.5 / W, 1 - y / H, s, fontsize=6.5, color=GREY, va="top", style="italic")


# row 1 — single-cell reconstruction: faithful and fast

def p_renders(fig, d, x, y):
    """3-D render from the U-Chrom web browser (``build_render_cd.py``; pane capture)."""
    head_(fig, x, y, "a", "U-Chrom reconstruction", "Stevens 2017 Cell 1, 100 kb")
    img = plt.imread(HERE / "renders" / "cell1_uchrom_crop.png")
    ax = ax_at(fig, x + 5, y + 9, 34, 34 * img.shape[0] / img.shape[1])
    ax.imshow(img); ax.axis("off")
    triad(fig, x - 1, y + 41, 10)


def p_nd_scatter(fig, d, x, y):
    head_(fig, x, y, "b", "Agreement with published", "Cell 1, pairwise distances")
    ax = ax_at(fig, x + 10, y + 11, 28, 28)
    xs, ys = d["nd_scatter"]
    ax.hexbin(xs, ys, gridsize=26, cmap=LinearSegmentedColormap.from_list("b", ["#ffffff", INDIGO]),
              mincnt=1, lw=0, bins="log")
    lim = float(np.percentile(np.r_[xs, ys], 99.5))
    ax.plot([0, lim], [0, lim], color=GREY, lw=0.6, ls="--")
    ax.set_xlim(0, lim); ax.set_ylim(0, lim)
    ax.set_xlabel("published (radii)"); ax.set_ylabel("U-Chrom (radii)")
    ax.text(0.04, 0.96, f"r = {np.corrcoef(xs, ys)[0, 1]:.3f}", transform=ax.transAxes, fontsize=6, va="top")


def p_nd_precision(fig, d, x, y):
    head_(fig, x, y, "c", "Ensemble precision", "8 cells × 10 models")
    bx = ax_at(fig, x + 10, y + 11, 30, 28)
    cells = np.arange(1, 9)
    bx.scatter(cells, d["nd_prec_pub"], s=10, color=PAPER, label="published", zorder=3)
    bx.scatter(cells, d["nd_prec_orig"], s=12, facecolor="none", edgecolor=ORIG, lw=0.7,
               label="original code", zorder=3)
    bx.scatter(cells, d["nd_prec_ours"], s=10, color=OURS, marker="D", label="U-Chrom", zorder=3)
    bx.scatter(cells + 0.22, d["nd_prec_new"], s=10, color=NEW, marker="^", label=NEW_LABEL, zorder=3)
    bx.set_yscale("log"); bx.set_xticks(cells, [str(c) for c in cells])
    bx.set_yticks([0.5, 1, 2, 5], ["0.5", "1", "2", "5"]); bx.minorticks_off()
    bx.set_xlabel("cell"); bx.set_ylabel("RMSD to mean (radii)")
    bx.legend(frameon=False, fontsize=5.3, ncol=3, loc="upper left", bbox_to_anchor=(-0.42, -0.24),
              handletextpad=0.05, columnspacing=0.5)


HIGHRES = HERE / "renders" / "highres"
HAP_PAT, HAP_MAT = "#d1495b", "#2e6fbf"          # = capture_highres.PAT / MAT


def load_highres(d: dict) -> None:
    """High-resolution diploid demonstration (``benchmarks/screcon/highres.py summary``; Sherlock)."""
    p = RES / "highres" / "summary.json"
    d["highres"] = _j(p) if p.exists() else None


def p_highres(fig, d, x, y):
    """EMber at 5 kb on the deepest scMicro-C cell: U-Chrom web-browser pane captures
    (``build_render_scmicroc.py`` + ``capture_highres.py``)."""
    hr = d.get("highres")
    cell = hr["cells"][HIGHRES_CELL] if hr else None
    run = next((r for r in cell["runs"] if r["set"] == "ladder" and r["res"] == 5000 and r["seed"] == 1), None) \
        if cell else None
    note = "GM12878 scMicro-C (Wu 2025), deepest cell"
    if run:
        note = (f"GM12878 scMicro-C (Wu 2025), deepest cell: {run['n_contacts_input'] / 1e6:.2f} M contacts, "
                f"{run['particles_grid'] / 1e6:.2f} M particles (2 × 23 chains); {run['n_models']} models in "
                f"{run['wall_seconds'] / 60:.1f} min on one H100 ({run['gpu']['peak_mib'] / 1024:.1f} GB)")
    head_(fig, x, y, "a", "EMber (U-Chrom): a diploid human genome at 5 kb", note)
    sc = (cell or {}).get("scores", {})
    r_seed = ((sc.get("res5000") or {}).get("a_vs_b") or {}).get("per_copy_r")
    r_hk = ((sc.get("ref_res5000") or {}).get("a_within") or {}).get("per_copy_r")
    if r_seed is not None and r_hk is not None:
        fig.text((x + 5) / W, 1 - (y + 7.4) / H,
                 f"one model shown; low run-to-run agreement on this data (seeds: r = {r_seed:.2f} per copy chain; "
                 f"the authors' hickit runs: {r_hk:.2f}); Supplementary Fig. S8",
                 fontsize=5.5, color=NEW, va="top", style="italic")
    s = 39
    for k, (name, cap) in enumerate((("cell035_genome_crop.png", "coloured by chromosome"),
                                     ("cell035_homologs_chr1_crop.png", None))):
        ax = ax_at(fig, x + 4 + k * (s + 2), y + 11, s, s)
        ax.imshow(plt.imread(HIGHRES / name)); ax.axis("off")
        if cap:
            ax.text(0.5, -0.01, cap, transform=ax.transAxes, ha="center", va="top", fontsize=5.5, color=GREY)
    ax = fig.axes[-1]
    for xx, lab, col in ((0.2, "chr1 copies:", GREY), (0.52, "paternal", HAP_PAT), (0.8, "maternal", HAP_MAT)):
        ax.text(xx, -0.01, lab, transform=ax.transAxes, ha="center", va="top", fontsize=5.5, color=col,
                fontweight="normal" if col == GREY else "bold")
    triad(fig, x - 1, y + 41, 9)
    zooms = [(f, t) for f, t in (("cell035_zoom_crop.png", "5 kb"), ("cell035_2kb_zoom_crop.png", "2 kb*"),
                                 ("cell035_1kb_zoom_crop.png", "1 kb*"))
             if (HIGHRES / f).exists()]
    zx = x + 4 + 2 * (s + 2) + 2
    zw = (W - 2 - zx) / max(len(zooms), 1) - 1.5
    for k, (f, t) in enumerate(zooms):
        img = plt.imread(HIGHRES / f)
        ax = ax_at(fig, zx + k * (zw + 1.5), y + 16, zw, zw)
        ax.imshow(img); ax.axis("off")
        ax.set_title(t, fontsize=6, color=INK, pad=1)
    fig.text((zx + (W - 2 - zx) / 2) / W, 1 - (y + 18 + zw) / H,
             "one model each, superposed on the 5 kb model\n* exploratory runs (5 models)",
             ha="center", va="top", fontsize=5.5, color=GREY)
    fig.text((zx + (W - 2 - zx) / 2) / W, 1 - (y + 10.5) / H, "chr1:53–56 Mb, paternal copy; rainbow along the region",
             ha="center", va="top", fontsize=5.5, color=GREY)


HIGHRES_CELL = "GSM5764669_cell_035"


SPEED_STYLE = {   # (method, threads) -> label, colour, line style, marker
    ("orig", 1): ("NucDynamics", ORIG, "-", "s"),
    ("sic", 1): ("Si-C", PURPLE, "-", "^"),
    ("hickit", 1): ("hickit", TEAL, "-", "v"),
    ("robust_gpu", 0): ("EMber (U-Chrom), GPU", NEW, "-", "D"),
    ("robust_cpu", 16): ("EMber (U-Chrom), CPU 16 thr.", NEW, "-", "o"),
    ("robust_cpu", 1): ("EMber (U-Chrom), CPU 1 thr.", NEW, (0, (2, 1)), "o"),
}


def p_nd_speed(fig, d, x, y):
    """Wall time of ONE model vs final resolution; censored runs (job cap) as open markers + arrow."""
    sp = d["speed1"]
    cap = sp["cap_hours"] * 3600
    head_(fig, x, y, "b", "Time for one model", "Cell 1; CPU: EPYC 9754, GPU: H100")
    ax = ax_at(fig, x + 12, y + 11, 28.5, 28)
    rows = sp["rows"]
    robust_done = any_failed = False
    for (m, t), (lab, col, ls, mk) in SPEED_STYLE.items():
        cfg = sorted([r for r in rows if r["method"] == m and r["threads"] == t], key=lambda r: -r["res"])
        ok = [r for r in cfg if r["status"] == "ok"]
        cen = [r for r in cfg if r["status"].startswith("censored")]
        bad = [r for r in cfg if r["status"] == "failed"]
        if m.startswith("robust"):
            robust_done |= bool(ok or cen)
        for r in bad:                                  # failed run (e.g. out of memory): cross above the cap
            ax.plot(r["res"], cap * 2.2, marker="x", ms=2.6, mew=0.7, color=col, ls="none", zorder=4)
            any_failed = True
        if not ok and not cen:
            continue
        ax.plot([r["res"] for r in ok], [r["median_wall_seconds"] for r in ok], color=col, ls=ls, lw=0.8,
                marker=mk, ms=2.2, mew=0, zorder=3)
        if ok and cen:                                 # dotted link from the last finished point to the cap
            last = ok[-1]
            ax.plot([last["res"], cen[0]["res"]], [last["median_wall_seconds"], cap], color=col, ls=":", lw=0.6)
        for r in cen:
            ax.plot(r["res"], cap, marker=mk, ms=2.6, mfc="white", mec=col, mew=0.6, zorder=4, ls="none")
            ax.annotate("", xy=(r["res"], cap * 4.5), xytext=(r["res"], cap * 1.25),
                        arrowprops=dict(arrowstyle="-|>", lw=0.5, color=col, mutation_scale=4))
    ax.axhline(cap, color=LGREY, lw=0.5, ls="--", zorder=0)
    ax.text(5.5e5, cap * 0.62, f"{sp['cap_hours']:.0f} h cap", fontsize=4.8, color=GREY, va="top")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlim(7e5, 7e2)
    res_ticks = [5e5, 1e5, 1e4, 1e3]
    ax.set_xticks(res_ticks, ["500k", "100k", "10k", "1k"])
    ax.set_xticks([5e4, 2e4], minor=True)
    ax.set_ylim(1, cap * 8)
    ax.set_yticks([1, 60, 3600, 86400], ["1 s", "1 min", "1 h", "1 d"])
    ax.set_xlabel("final resolution (bp)", labelpad=1)
    ax.set_ylabel("wall time, one model", labelpad=1)
    hs = [mpl.lines.Line2D([], [], color=c, ls=ls, marker=mk, ms=2.2, mew=0, lw=0.8, label=lab)
          for (m, t), (lab, c, ls, mk) in SPEED_STYLE.items()]
    hs.append(mpl.lines.Line2D([], [], color=GREY, marker="o", ms=2.6, mfc="white", mew=0.6, ls="none",
                               label="> cap (censored)"))
    if any_failed:
        hs.append(mpl.lines.Line2D([], [], color=GREY, marker="x", ms=2.6, mew=0.7, ls="none", label="failed"))
    ax.legend(handles=hs, frameon=False, fontsize=4.8, ncol=1, loc="upper left", bbox_to_anchor=(-0.3, -0.22),
              handlelength=1.6, handletextpad=0.3, columnspacing=0.6, labelspacing=0.25)
    if not robust_done:
        mock_frame(fig, x + 1.5, y + 8, 40.5, 51, "robust: runs pending")


# row 2 — one benchmark for every method

def p_heldout_contacts(fig, d, x, y):
    head_(fig, x, y, "c", "Held-out contacts",
          f"8 cells × 3 folds; matched-separation negatives")
    ax = ax_at(fig, x + 12, y + 11, 42, 28)
    b = d["ho_band"]
    xx = np.arange(len(BANDS))
    order = ["random_polymer", "hickit", "sic", "orig", "robust"]
    for m in order:
        lab, col = SC_METHODS[m]
        mean = [b.loc[(m, k), "mean"] for k, _ in BANDS]
        ls = (0, (2, 1)) if m == "nucdyn_cpu" else "-"
        ax.plot(xx, mean, color=col, marker="o" if m != "nucdyn_cpu" else None, ms=2.2, lw=0.9, ls=ls,
                label=lab, zorder=4 if m == "robust" else (3 if m.startswith("nucdyn") else 2))
    ax.set_xticks(xx, [b_ for _, b_ in BANDS], fontsize=5.5)
    ax.set_xlabel("genomic separation (Mb)"); ax.set_ylabel("ROC-AUC (held-out cis)")
    ax.set_ylim(0.45, 1.0); ax.axhline(0.5, color=LGREY, lw=0.5, zorder=0)
    tr = d["ho_trans"]
    ax.text(0.98, 0.14, "trans AUC\n" + "\n".join(f"{SC_METHODS[m][0].split(' (')[0]}  {tr[m]:.3f}"
                                                 for m in ("robust", "orig", "sic", "hickit")),
            transform=ax.transAxes, ha="right", va="bottom", fontsize=4.8, color=GREY, linespacing=1.15)


def p_sim(fig, d, x, y):
    head_(fig, x, y, "d", "Imaging truth (simulated Hi-C)", "median model vs imaged distances")
    ax = ax_at(fig, x + 12, y + 11, 42, 28)
    order = ["robust", "orig", "sic", "hickit", "pop_mean", "random_polymer"]
    dsets = [("su2020_chr21", "Su 2020\nchr21, 50 kb"), ("takei2021_1mb", "Takei 2021\ngenome, 1 Mb")]
    w = 0.13
    for i_, (ds, _) in enumerate(dsets):
        sc = d["sim"][ds]["spearman_cis"]
        for k_, m in enumerate(order):
            xpos = i_ + (k_ - (len(order) - 1) / 2) * w
            if m not in sc.index:
                ax.text(xpos, 0.03, "n/a", rotation=90, fontsize=4.5, ha="center", va="bottom", color=GREY)
                continue
            ax.bar(xpos, sc.loc[m, "mean"], w * 0.92, color=SC_METHODS[m][1],
                   label=SC_METHODS[m][0] if i_ == 1 else None)
    ax.set_xticks(range(2), [l for _, l in dsets], fontsize=5.5)
    ax.set_ylabel("Spearman, cis distances"); ax.set_ylim(0, 0.95)
    n_su, n_tk = d["sim"]["su2020_chr21"]["n_cases"], d["sim"]["takei2021_1mb"]["n_cases"]
    ax.text(1.0, 1.0, f"{n_su} / {n_tk} matched\nsimulations", transform=ax.transAxes, fontsize=4.8,
            color=GREY, ha="right", va="top")


def sc_legend(fig, x, y):
    """Shared legend of the single-cell methods (panels c, d), top-left at (x, y) mm."""
    order = ["robust", "orig", "sic", "hickit", "pop_mean", "random_polymer"]
    hs = [mpl.patches.Patch(color=SC_METHODS[m][1], label=SC_METHODS[m][0]) for m in order]
    fig.legend(handles=hs, loc="upper left", bbox_to_anchor=(x / W, 1 - y / H), ncol=3, frameon=False,
               fontsize=5.3, handlelength=1, handleheight=0.7, columnspacing=0.8)


# row 3 — population reconstruction

IGM_KINDS = [("ours", "native vs native", OURS2), ("igm", "original vs original", ORIG),
             ("igm-ours", "native vs original", OURS)]


def p_igm_equiv(fig, d, x, y):
    head_(fig, x, y, "e", "IGM: native vs original", "WTC11 2 Mb; population agreement")
    ax = ax_at(fig, x + 10, y + 11, 30, 28)
    feats = [("pearson_contact_intra", "intra\ncontacts"), ("pearson_contact_inter", "inter\ncontacts"),
             ("pearson_radial", "radial\nposition")]
    P = d["igm_pairs"]
    for fi, (key, _) in enumerate(feats):
        for ki, (kind, lab, col) in enumerate(IGM_KINDS):
            v = [r[key] for r in P.get((200, kind), [])]
            xs = np.full(len(v), fi + (ki - 1) * 0.2)
            ax.scatter(xs, v, s=9, color=col, label=lab if fi == 0 else None, zorder=3, lw=0)
        v = [r[key] for r in P.get((1000, "igm-ours"), [])]
        ax.scatter([fi + 0.4] * len(v), v, s=16, marker="*", color=OURS, zorder=3, lw=0,
                   label="native vs original, S = 1,000" if fi == 0 else None)
    ax.set_xticks(range(3), [l for _, l in feats], fontsize=5.5); ax.set_xlim(-0.5, 2.6)
    ax.set_ylabel("Pearson r"); ax.set_ylim(0.5, 1.02)
    ax.text(0.02, 0.03, "dots: S = 200", transform=ax.transAxes, fontsize=5, color=GREY)
    ax.legend(frameon=False, fontsize=5.0, loc="upper left", bbox_to_anchor=(-0.38, -0.24), ncol=2,
              handletextpad=0.1, columnspacing=0.5)


def p_igm_speed(fig, d, x, y):
    head_(fig, x, y, "f", "IGM speed", "same input and schedule")
    t = d["igm_time"]
    ax = ax_at(fig, x + 10, y + 11, 28, 28)
    for si, S in enumerate((200, 1000)):
        o, n = np.mean(t["orig"][S]), np.mean(t["ours"][S])
        ax.bar(si - 0.18, o, 0.34, color=ORIG, label=f"original, {t['orig_cores']} CPU cores" if si == 0 else None)
        ax.bar(si + 0.18, n, 0.34, color=OURS, label="U-Chrom, 1 GPU" if si == 0 else None)
        ax.text(si - 0.18, o + 2, f"{o:.0f}", ha="center", fontsize=5.5)
        ax.text(si + 0.18, n + 2, f"{n:.0f}" if n >= 10 else f"{n:.1f}", ha="center", fontsize=5.5)
    ax.set_xticks(range(2), ["S = 200", "S = 1,000"]); ax.set_ylabel("wall time (min)")
    ax.legend(frameon=False, fontsize=5.2, loc="upper left", bbox_to_anchor=(-0.3, -0.16), handlelength=1)


def p_popsize(fig, d, x, y):
    head_(fig, x, y, "g", "How many structures?", "WTC11 2 Mb, 3 seeds; grey: minutes on 1 GPU")
    ax = ax_at(fig, x + 10, y + 11, 34, 28)
    sw = d["igm_sweep"]
    Ss = sorted(sw)
    r200 = np.mean(sw[200]["seed"])
    c = 200 * (1 / r200 - 1)            # sampling-noise model r(S) = 1 / (1 + c / S), fitted at S = 200 only
    grid = np.geomspace(150, 6500, 100)
    ax.plot(grid, 1 / (1 + c / grid), color=LGREY, lw=0.9, ls="--", label="sampling noise (fit at S = 200)")
    m = [np.mean(sw[S]["seed"]) for S in Ss]
    ax.plot(Ss, m, color=OURS, marker="o", ms=2.8, lw=0.9, label="seed vs seed (native)")
    vo = [(S, v) for S in Ss for v in sw[S]["vs_orig"]]
    ax.scatter(*zip(*vo), s=16, marker="*", color=INK, zorder=4, lw=0, label="native vs original")
    f = [np.mean(sw[S]["fit"]) for S in Ss]
    ax.plot(Ss, f, color=TEAL, marker="s", ms=2.5, lw=0.9, label="fit to input Hi-C")
    for S in Ss:
        ax.text(S, 0.405, f"{np.mean(sw[S]['minutes']):.0f}", ha="center", va="bottom", fontsize=4.8, color=GREY)
    ax.set_xscale("log"); ax.set_xticks(Ss, ["200", "500", "1k", "2k", "5k"])
    ax.minorticks_off(); ax.set_ylim(0.4, 1.0); ax.set_xlim(150, 6500)
    ax.set_xlabel("structures in the population (S)"); ax.set_ylabel("Pearson r, trans contacts")
    ax.legend(frameon=False, fontsize=4.8, loc="lower right", handlelength=1.4)


def main() -> None:
    d = load_results()
    fig = plt.figure(figsize=(W * MM, H * MM))
    row_title(fig, 0.5, "single-cell reconstruction at high resolution (EMber, homolog-resolved)")
    p_highres(fig, d, 0, 4)
    dy = 56
    row_title(fig, 0.5 + dy, "single-cell reconstruction: EMber vs existing methods, one benchmark")
    p_nd_speed(fig, d, 0, 4 + dy)
    p_heldout_contacts(fig, d, 56, 4 + dy)
    p_sim(fig, d, 114, 4 + dy)
    sc_legend(fig, 64, 52 + dy)
    row_title(fig, 72.5 + dy, "population reconstruction (IGM)")
    p_igm_equiv(fig, d, 0, 76 + dy)
    p_igm_speed(fig, d, 58, 76 + dy)
    p_popsize(fig, d, 114, 76 + dy)
    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"fig3.{ext}", dpi=300)
    print(HERE / "fig3.pdf")


if __name__ == "__main__":
    main()
