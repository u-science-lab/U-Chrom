"""Supplementary figure — population reconstruction in detail.

  a  IGM (WTC11 2 Mb demo): fit of each population to the input Hi-C, native vs original
  b  MDS vs miniMDS agreement (Rao 2014 IMR90 chr21)
  c  MDS runtime, same input

Inputs: ``results/igm_demo/compare_S*.json``, ``feasibility/a_mds_vs_minimds_imr90_chr21.json``.

    python paper/fig3/make_figS_fig3_population.py      # -> figS_fig3_population.pdf / .png
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import make_fig3 as F
from make_fig3 import (GREY, HERE, INK, MM, ORIG, OURS, OURS2, PAPER, TEAL, ax_at, label, load_results, sub)

W, H = 170.0, 64.0
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


def p_mds_r(fig, d, x, y):
    head_(fig, x, y, "b", "MDS vs miniMDS", "Rao 2014 IMR90 chr21")
    m = d["mds"]
    ax = ax_at(fig, x + 12, y + 11, 26, 30)
    xx = np.arange(2)
    ax.bar(xx - 0.18, m["seed_r"], 0.34, color=PAPER, label="miniMDS, seed vs seed")
    ax.bar(xx + 0.18, m["ours_r"], 0.34, color=OURS, label="U-Chrom vs miniMDS")
    ax.set_xticks(xx, m["res"]); ax.set_ylim(0.9, 1.0); ax.set_ylabel("distance-matrix r")
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(-0.4, -0.16), fontsize=5.3, handlelength=1)


def p_mds_time(fig, d, x, y):
    head_(fig, x, y, "c", "MDS runtime", "same input as b")
    m = d["mds"]
    xx = np.arange(2)
    tx = ax_at(fig, x + 12, y + 11, 26, 30)
    tx.bar(xx - 0.18, m["t_orig"], 0.34, color=PAPER, label="miniMDS")
    tx.bar(xx + 0.18, m["t_ours"], 0.34, color=OURS, label="U-Chrom")
    tx.set_yscale("log"); tx.set_xticks(xx, m["res"]); tx.set_ylabel("runtime (s)")
    tx.legend(frameon=False, loc="upper left", bbox_to_anchor=(-0.3, -0.16), fontsize=5.3, handlelength=1)


def main() -> None:
    d = load_results()
    fig = plt.figure(figsize=(W * MM, H * MM))
    p_igm_fit(fig, d, 0, 2)
    p_mds_r(fig, d, 58, 2)
    p_mds_time(fig, d, 114, 2)
    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"figS_fig3_population.{ext}", dpi=300)
    print(HERE / "figS_fig3_population.pdf")


if __name__ == "__main__":
    main()
