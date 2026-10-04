"""Supplementary figure (DRAFT, development set) — EMber (U-Chrom) on diploid, partially phased data.

Diploid extension of EMber (one chain per chromosome copy; the copy pair of a contact with an
unphased end is a latent variable of EMber's mixture model; candidates kept as one ambiguous
restraint).  Development units only (benchmarks/screcon/PREREG.md §6, diploid addition): imaging-
truth simulations, truth cells 1-2 of Su 2020 genome-scale and Takei 2021 1 Mb, and Dip-C GM12878
(Tan et al. 2018) cells 1-3.  The held-back test units replace these numbers once the diploid
parameters are frozen.  Tables: ``results/diploid/{sim_rows,real_rows}.csv``
(``benchmarks/screcon/diploid_aggregate.py``).

  a  per-copy structure vs truth (Spearman of within-copy distances), by dataset
  b  within-copy vs whole-genome agreement: the trade-off between EMber and hickit
  c  robustness: per-copy Spearman vs false-contact rate, phased fraction and depth
  d  Dip-C GM12878, 100 kb: agreement with the published Dip-C structures (within copy / whole
     genome) and phase accuracy on masked phased ends

    python paper/fig3/make_figS_fig3_diploid.py      # -> figS_fig3_diploid.pdf / .png
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import make_fig3 as F
from make_fig3 import GREY, HERE, INK, LGREY, MM, NEW, ORIG, RES, TEAL, ax_at, label, sub

W, H = 170.0, 118.0
F.W, F.H = W, H
METH = [("ember_nosplit", "EMber (U-Chrom)", NEW, "o"), ("nucdyn", "NucDynamics", ORIG, "s"),
        ("hickit", "hickit (Dip-C)", TEAL, "^")]
DS = [("su2020_genome", "Su 2020\ngenome, IMR90"), ("takei2021_1mb", "Takei 2021\n1 Mb, mESC")]


def head_(fig, x, y, letter, name, note=None):
    label(fig, x, y, letter)
    sub(fig, x + 5, y + 0.8, name, note)


def main() -> None:
    s = pd.read_csv(RES / "diploid" / "sim_rows.csv")
    r = pd.read_csv(RES / "diploid" / "real_rows.csv")
    fig = plt.figure(figsize=(W * MM, H * MM))
    fig.text(W / W, 1 - 1 / H, "DRAFT — development set (diploid parameters not frozen)", ha="right", va="top",
             fontsize=6, color=GREY, style="italic")

    head_(fig, 0, 4, "a", "Per-copy structure", "simulated diploid scHi-C from imaged cells")
    ax = ax_at(fig, 12, 15, 34, 30)
    for i, (ds, dl) in enumerate(DS):
        for k, (m, lab, col, mk) in enumerate(METH):
            v = s[(s.dataset == ds) & (s.method == m)].spearman_cis
            xs = i + (k - 1) * 0.24
            ax.bar(xs, v.mean(), 0.22, color=col, label=lab if i == 0 else None)
            ax.errorbar(xs, v.mean(), yerr=v.std(), color=INK, lw=0.5, capsize=1)
    ax.set_xticks(range(2), [d for _, d in DS], fontsize=5.5); ax.set_ylim(0, 1)
    ax.set_ylabel("Spearman, within-copy distances")
    ax.legend(frameon=False, fontsize=5.2, loc="upper left", bbox_to_anchor=(-0.3, -0.22), ncol=3, handlelength=1,
              columnspacing=0.6)

    head_(fig, 58, 4, "b", "Within copy vs whole genome", "dots: tables; large: mean")
    ax = ax_at(fig, 70, 15, 30, 30)
    for m, lab, col, mk in METH:
        g = s[s.method == m]
        ax.scatter(g.spearman_cis, g.spearman_whole, s=4, color=col, alpha=0.35, lw=0, marker=mk)
        ax.scatter(g.spearman_cis.mean(), g.spearman_whole.mean(), s=28, color=col, edgecolor="white", lw=0.6,
                   marker=mk, zorder=3)
    ax.plot([0, 1], [0, 1], color=LGREY, lw=0.5, ls="--")
    ax.set_xlim(0.3, 1); ax.set_ylim(0.2, 1)
    ax.set_xlabel("Spearman, within copy"); ax.set_ylabel("Spearman, whole genome")

    head_(fig, 112, 4, "c", "Robustness", "per-copy Spearman, mean over tables")
    for j, (col_, xl, ticks) in enumerate((("eps", "false contacts", None), ("phased", "phased ends", None),
                                           ("depth", "reads / Mb", None))):
        ax = ax_at(fig, 120 + j * 17, 15, 14, 30)
        for m, lab, c, mk in METH:
            g = s[s.method == m].groupby(col_).spearman_cis.mean()
            ax.plot(range(len(g)), g.values, color=c, marker=mk, ms=2.4, lw=0.8)
        lv = sorted(s[col_].unique())
        ax.set_xticks(range(len(lv)), [f"{v:g}" for v in lv], fontsize=5)
        ax.set_xlim(-0.4, len(lv) - 0.6); ax.set_ylim(0.6, 1.0); ax.set_xlabel(xl, fontsize=5.5, labelpad=1)
        if j:
            ax.set_yticklabels([])
        else:
            ax.set_ylabel("Spearman, within copy")

    head_(fig, 0, 66, "d", "Dip-C GM12878, 100 kb", "cells 1-3; vs published Dip-C structures")
    full = r[r.kind == "full"].copy()
    full["m"] = full.method.str.replace(r"_s\d$", "", regex=True)
    rm = full.groupby(["cell", "m"])[["dipc_r_cis", "dipc_r_whole"]].mean()
    cells = sorted(full.cell.unique())
    for j, (col_, nm) in enumerate((("dipc_r_cis", "within copy"), ("dipc_r_whole", "whole genome"))):
        ax = ax_at(fig, 12 + j * 34, 77, 26, 28)
        for k, (m, lab, c, mk) in enumerate(METH[:2]):
            v = [rm.loc[(cl, m), col_] if (cl, m) in rm.index else np.nan for cl in cells]
            ax.bar(np.arange(len(cells)) + (k - 0.5) * 0.36, v, 0.34, color=c)
        ax.set_xticks(range(len(cells)), [c.replace("cell0", "") for c in cells]); ax.set_xlabel("cell", labelpad=1)
        ax.set_ylim(0.8, 1.0); ax.set_title(nm, fontsize=6, pad=1)
        if j == 0:
            ax.set_ylabel("distance-matrix r vs Dip-C")
    mask = r[r.kind == "mask"]
    ax = ax_at(fig, 84, 77, 26, 28)
    for k, (m, lab, c, mk) in enumerate(METH):
        v = [mask[(mask.cell == cl) & (mask.method == m)].phase_acc_all.mean() for cl in cells]
        ax.bar(np.arange(len(cells)) + (k - 1) * 0.26, v, 0.24, color=c)
    ax.set_xticks(range(len(cells)), [c.replace("cell0", "") for c in cells]); ax.set_xlabel("cell", labelpad=1)
    ax.set_ylim(0.6, 0.9); ax.set_title("phase of masked ends", fontsize=6, pad=1); ax.set_ylabel("accuracy")
    fig.text(116 / W, 1 - 80 / H, "Wall time, cell 1, 10 models\n(one RTX 2080 Ti):\nEMber (U-Chrom) ~110 s\n"
             "NucDynamics ~1,055 s\n\nheld-out contacts and\ncell 2-3 timings: pending",
             fontsize=5.5, color=GREY, va="top", linespacing=1.3)
    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"figS_fig3_diploid.{ext}", dpi=300)
    print(HERE / "figS_fig3_diploid.pdf")


if __name__ == "__main__":
    main()
