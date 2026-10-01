"""Supplementary figure — population and Hi-C + FISH reconstruction in detail.

  a  IGM (WTC11 2 Mb demo): fit of each population to the input Hi-C, native vs original
  b  consensus reconstruction, IMR90: run-to-run agreement (median distance-matrix r between
     the 16 runs) for whole-genome runs and single-chromosome (chr21) runs, and the variants
     (Lorentzian restraints, fitted / imaging-calibrated alpha, no trans restraints, mean-refined)
  c  consensus runtime vs particles, GPU (H100) and CPU (16 threads), 16 runs
  d  MDS vs miniMDS agreement (Rao 2014 IMR90 chr21)
  e  MDS runtime, same input
  f  GEM-FISH vs the paper (Wang 2016 chr21): training and held-out cells

Inputs: ``results/igm_demo/compare_S*.json``, ``results/consensus/imr90*.json`` (Sherlock
consensus runs), ``feasibility/a_mds_vs_minimds_imr90_chr21.json``, ``results/c_gemfish_*``.

    python paper/fig3/make_figS_fig3_population.py      # -> figS_fig3_population.pdf / .png
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import make_fig3 as F
from make_fig3 import (GREY, HERE, INK, MM, ORIG, OURS, OURS2, PAPER, TEAL, ax_at, label, load_results, sub)

W, H = 170.0, 128.0
F.W, F.H = W, H


def head_(fig, x, y, letter, name, note=None):
    label(fig, x, y, letter)
    sub(fig, x + 5, y + 0.8, name, note)


def p_igm_fit(fig, d, x, y):
    head_(fig, x, y, "a", "IGM: fit to the input", "Pearson, restrained pairs")
    ax = ax_at(fig, x + 12, y + 11, 36, 32)
    rows = []
    for S in (200, 1000):
        for name, pop in sorted(d["igm_fit"][S].items()):
            code, run = name.split(":")
            rows.append((S, code, run, pop["fit"]))
    for k, key in enumerate(("pearson_intra_restrained", "pearson_inter_restrained")):
        for j, (S, code, run, f) in enumerate(rows):
            xpos = k + (j - (len(rows) - 1) / 2) * 0.11
            col = (OURS if S == 1000 else OURS2) if code == "ours" else (INK if S == 1000 else ORIG)
            ax.bar(xpos, f[key], 0.1, color=col)
    ax.set_xticks(range(2), ["intra", "inter"]); ax.set_ylim(0.5, 1.0); ax.set_ylabel("Pearson r vs input")
    hs = [plt.Rectangle((0, 0), 1, 1, color=c) for c in (OURS2, ORIG, OURS, INK)]
    ax.legend(hs, ["native, S = 200", "original, S = 200", "native, S = 1,000", "original, S = 1,000"],
              frameon=False, fontsize=5.2, loc="upper left", bbox_to_anchor=(-0.3, -0.12), ncol=2,
              handlelength=1, columnspacing=0.6)


def p_cons_repro(fig, d, x, y):
    head_(fig, x, y, "b", "Consensus: run-to-run agreement", "IMR90, 16 runs each")
    runs = d["cons_runs"]
    order = [("imr90_1mb_s1", "genome 1 Mb, seed 1"), ("imr90_1mb_s2", "genome 1 Mb, seed 2"),
             ("imr90_250kb_s1", "genome 250 kb, seed 1"), ("imr90_250kb_s2", "genome 250 kb, seed 2"),
             ("imr90_250kb_s3", "genome 250 kb, seed 3"), ("imr90_250kb_lor", "250 kb, Lorentzian"),
             ("imr90_250kb_afit", "250 kb, alpha fitted"), ("imr90_250kb_acal", "250 kb, alpha from imaging"),
             ("imr90_250kb_notrans", "250 kb, no trans"), ("imr90_100kb_s1", "genome 100 kb"),
             ("imr90_50kb_s1", "genome 50 kb (8 runs)"), ("imr90chr21_50kb_s1", "chr21 alone 50 kb, seed 1"),
             ("imr90chr21_50kb_s2", "chr21 alone 50 kb, seed 2")]
    order = [(k, n) for k, n in order if k in runs]
    ax = ax_at(fig, x + 34, y + 11, 22, 46)
    yy = np.arange(len(order))
    vals = [runs[k]["precision"]["distance_r_median"] for k, _ in order]
    ax.barh(yy, vals, 0.7, color=[TEAL if "chr21" in k else OURS for k, _ in order])
    ax.set_yticks(yy, [n for _, n in order], fontsize=5.2); ax.invert_yaxis()
    ax.set_xlim(0, 1); ax.set_xlabel("median r between runs")


def p_cons_time(fig, d, x, y):
    head_(fig, x, y, "c", "Consensus: runtime", "16 runs, whole genome")
    runs = d["cons_runs"]
    ax = ax_at(fig, x + 12, y + 11, 34, 32)
    for dev, col, mk in (("gpu", OURS, "D"), ("cpu", ORIG, "o")):
        pts = sorted((r["n_beads"], r["seconds_engine"] / 60) for k, r in runs.items()
                     if r["device"] == dev and "chr21" not in k and r["n_runs"] == 16 and not r.get("overrides"))
        if pts:
            ax.plot(*zip(*pts), color=col, marker=mk, ms=3, lw=0.8,
                    label="1 GPU (H100)" if dev == "gpu" else "16 CPU threads")
    ax.set_xscale("log"); ax.set_yscale("log"); ax.minorticks_off()
    ax.set_xticks([2863, 11289, 28070, 55921], ["2.9k\n1 Mb", "11k\n250 kb", "28k\n100 kb", "56k\n50 kb"],
                  fontsize=5.2)
    ax.set_yticks([0.1, 1, 10, 100], ["0.1", "1", "10", "100"])
    ax.set_xlabel("particles"); ax.set_ylabel("engine time (min)")
    ax.legend(frameon=False, fontsize=5.3, loc="upper left")


def p_mds_r(fig, d, x, y):
    head_(fig, x, y, "d", "MDS vs miniMDS", "Rao 2014 IMR90 chr21")
    m = d["mds"]
    ax = ax_at(fig, x + 12, y + 11, 26, 30)
    xx = np.arange(2)
    ax.bar(xx - 0.18, m["seed_r"], 0.34, color=PAPER, label="miniMDS, seed vs seed")
    ax.bar(xx + 0.18, m["ours_r"], 0.34, color=OURS, label="U-Chrom vs miniMDS")
    ax.set_xticks(xx, m["res"]); ax.set_ylim(0.9, 1.0); ax.set_ylabel("distance-matrix r")
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(-0.4, -0.16), fontsize=5.3, handlelength=1)


def p_mds_time(fig, d, x, y):
    head_(fig, x, y, "e", "MDS runtime", "same input as d")
    m = d["mds"]
    xx = np.arange(2)
    tx = ax_at(fig, x + 12, y + 11, 26, 30)
    tx.bar(xx - 0.18, m["t_orig"], 0.34, color=PAPER, label="miniMDS")
    tx.bar(xx + 0.18, m["t_ours"], 0.34, color=OURS, label="U-Chrom")
    tx.set_yscale("log"); tx.set_xticks(xx, m["res"]); tx.set_ylabel("runtime (s)")
    tx.legend(frameon=False, loc="upper left", bbox_to_anchor=(-0.3, -0.16), fontsize=5.3, handlelength=1)


def p_gemfish(fig, d, x, y):
    head_(fig, x, y, "f", "GEM-FISH vs the paper", "Wang 2016 chr21")
    j21 = d["joint"]["chr21"]
    vals = {"GEM (paper)": d["gemfish_paper"]["GEM (paper)"], "U-Chrom, Hi-C only": j21["U-Chrom, Hi-C only"],
            "GEM-FISH (paper)": d["gemfish_paper"]["GEM-FISH (paper)"],
            "U-Chrom, Hi-C + FISH": j21["U-Chrom, Hi-C + FISH"]}
    ax = ax_at(fig, x + 12, y + 11, 40, 30)
    w = 0.19
    for k_, ((key, v), col) in enumerate(zip(vals.items(), [PAPER, OURS2, ORIG, OURS])):
        ax.bar(np.arange(2) + (k_ - 1.5) * w, v, w, color=col, label=key)
    ax.set_xticks(range(2), ["training cells", "held-out cells"]); ax.set_ylabel("relative error vs FISH")
    ax.legend(frameon=False, fontsize=5.3, ncol=2, loc="upper left", bbox_to_anchor=(-0.2, -0.16),
              handlelength=1, columnspacing=0.8)


def main() -> None:
    d = load_results()
    fig = plt.figure(figsize=(W * MM, H * MM))
    p_igm_fit(fig, d, 0, 2)
    p_cons_repro(fig, d, 56, 2)
    p_cons_time(fig, d, 118, 2)
    p_mds_r(fig, d, 0, 70)
    p_mds_time(fig, d, 56, 70)
    p_gemfish(fig, d, 112, 70)
    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"figS_fig3_population.{ext}", dpi=300)
    print(HERE / "figS_fig3_population.pdf")


if __name__ == "__main__":
    main()
