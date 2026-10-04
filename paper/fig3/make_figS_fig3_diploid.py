"""Supplementary figure (DRAFT, development set) — EMber (U-Chrom) on diploid, partially phased data.

Diploid EMber: one chain per chromosome copy; the copy pair of a contact with an unphased end is a
latent variable of EMber's mixture model (candidates kept as one ambiguous restraint), with a
native 2-D neighbourhood phase prior.  Development units only (benchmarks/screcon/PREREG.md §6,
diploid addition): imaging-truth simulations, truth cells 1-2 of Su 2020 genome-scale and Takei
2021 1 Mb (1 Mb particles; 96 tables), and Dip-C GM12878 (Tan et al. 2018) cells 1-3 (100 kb,
10 models).  The pre-registered one-shot test on the held-back units replaces these numbers.
Tables: ``results/diploid/{sim_rows,real_rows}.csv`` (``benchmarks/screcon/diploid_aggregate.py``);
wall times from ``benchmarks/screcon/diploid_devlog.md``.

  a  simulation: per-copy structure vs truth (Spearman of within-copy distances)
  b  simulation: within-copy vs whole-genome agreement
  c  simulation: per-copy Spearman vs false-contact rate, phased fraction and depth
  d  simulation: phase accuracy vs phased fraction
  e  Dip-C GM12878: agreement with the published Dip-C structures (within copy / whole genome)
  f  Dip-C GM12878: held-out contacts (strict: both ends phased), ROC-AUC
  g  Dip-C GM12878: phase accuracy on masked phased ends
  h  wall time: structure (10 models, 100 kb, one RTX 2080 Ti) and phase imputation

    python paper/fig3/make_figS_fig3_diploid.py      # -> figS_fig3_diploid.pdf / .png
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import make_fig3 as F
from make_fig3 import GREY, HERE, INK, LGREY, MM, NEW, ORIG, RES, TEAL, ax_at, label, sub

W, H = 170.0, 120.0
F.W, F.H = W, H
METH = [("ember_nbr", "EMber (U-Chrom)", NEW, "o"), ("nucdyn", "NucDynamics", ORIG, "s"),
        ("hickit", "hickit (Dip-C)", TEAL, "^")]
DS = [("su2020_genome", "Su 2020\ngenome, IMR90"), ("takei2021_1mb", "Takei 2021\n1 Mb, mESC")]


def head_(fig, x, y, letter, name, note=None):
    label(fig, x, y, letter)
    sub(fig, x + 5, y + 0.8, name, note)


def cell_bars(ax, df, col, meths, cells):
    n = len(meths)
    for k, (m, lab, c, mk) in enumerate(meths):
        v = [df[(df.cell == cl) & (df.m == m)][col].mean() for cl in cells]
        ax.bar(np.arange(len(cells)) + (k - (n - 1) / 2) * 0.8 / n, v, 0.8 / n * 0.92, color=c)
    ax.set_xticks(range(len(cells)), [c.replace("cell0", "") for c in cells]); ax.set_xlabel("cell", labelpad=1)


def main() -> None:
    s = pd.read_csv(RES / "diploid" / "sim_rows.csv")
    r = pd.read_csv(RES / "diploid" / "real_rows.csv")
    r["m"] = r.method.str.replace(r"_s\d$", "", regex=True)
    cells = sorted(c for c in r.cell.unique())
    fig = plt.figure(figsize=(W * MM, H * MM))
    fig.text(1, 1 - 0.5 / H, "DRAFT — development set (diploid parameters frozen after this; test pending)", ha="right",
             va="top", fontsize=6, color=GREY, style="italic")
    fig.text(0.5 / W, 1 - 0.5 / H, "simulated diploid scHi-C from imaged cells", fontsize=6.5, color=GREY,
             va="top", style="italic")

    head_(fig, 0, 4, "a", "Per-copy structure", "96 tables, truth cells 1-2")
    ax = ax_at(fig, 11, 14, 30, 28)
    for i, (ds, dl) in enumerate(DS):
        for k, (m, lab, col, mk) in enumerate(METH):
            v = s[(s.dataset == ds) & (s.method == m)].spearman_cis
            xs = i + (k - 1) * 0.26
            ax.bar(xs, v.mean(), 0.24, color=col, label=lab if i == 0 else None)
            ax.errorbar(xs, v.mean(), yerr=v.std(), color=INK, lw=0.5, capsize=1)
    ax.set_xticks(range(2), [d for _, d in DS], fontsize=5.3); ax.set_ylim(0, 1)
    ax.set_ylabel("Spearman, within copy")

    head_(fig, 44, 4, "b", "Within copy vs genome", "dots: tables; large: mean")
    ax = ax_at(fig, 55, 14, 28, 28)
    for m, lab, col, mk in METH:
        g = s[s.method == m]
        ax.scatter(g.spearman_cis, g.spearman_whole, s=3.5, color=col, alpha=0.35, lw=0, marker=mk)
        ax.scatter(g.spearman_cis.mean(), g.spearman_whole.mean(), s=26, color=col, edgecolor="white", lw=0.6,
                   marker=mk, zorder=3)
    ax.plot([0, 1], [0, 1], color=LGREY, lw=0.5, ls="--")
    ax.set_xlim(0.3, 1); ax.set_ylim(0.2, 1)
    ax.set_xlabel("within copy"); ax.set_ylabel("whole genome")

    head_(fig, 88, 4, "c", "Robustness", "within copy, mean over tables")
    for j, (col_, xl) in enumerate((("eps", "false contacts"), ("phased", "phased ends"), ("depth", "reads / Mb"))):
        ax = ax_at(fig, 96 + j * 13, 14, 10.5, 28)
        for m, lab, c, mk in METH:
            g = s[s.method == m].groupby(col_).spearman_cis.mean()
            ax.plot(range(len(g)), g.values, color=c, marker=mk, ms=2.2, lw=0.8)
        lv = sorted(s[col_].unique())
        ax.set_xticks(range(len(lv)), [f"{v:g}" for v in lv], fontsize=4.8)
        ax.set_xlim(-0.4, len(lv) - 0.6); ax.set_ylim(0.6, 1.0); ax.set_xlabel(xl, fontsize=5.2, labelpad=1)
        if j:
            ax.set_yticklabels([])
        else:
            ax.set_ylabel("Spearman, within copy")

    head_(fig, 136, 4, "d", "Phase accuracy", "unphased signal ends")
    ax = ax_at(fig, 146, 14, 22, 28)
    for m, lab, c, mk in METH:
        g = s[s.method == m].groupby("phased").phase_acc.mean()
        ax.plot(range(len(g)), g.values, color=c, marker=mk, ms=2.4, lw=0.8)
    lv = sorted(s.phased.unique())
    ax.set_xticks(range(len(lv)), [f"{v:g}" for v in lv]); ax.set_xlabel("phased ends", labelpad=1)
    ax.set_ylim(0.7, 1.0); ax.set_ylabel("accuracy")

    hs = [mpl_patch(c, lab) for _, lab, c, _ in METH]
    fig.legend(handles=hs, loc="upper left", bbox_to_anchor=(11 / W, 1 - 52 / H), ncol=3, frameon=False,
               fontsize=5.5, handlelength=1, columnspacing=1.0)

    fig.text(0.5 / W, 1 - 62.5 / H, "Dip-C GM12878 (Tan 2018), development cells 1-3, 100 kb, 10 models",
             fontsize=6.5, color=GREY, va="top", style="italic")
    full = r[r.kind == "full"]
    head_(fig, 0, 66, "e", "Agreement with published", "distance-matrix r vs Dip-C")
    for j, (col_, nm) in enumerate((("dipc_r_cis", "within copy"), ("dipc_r_whole", "whole genome"))):
        ax = ax_at(fig, 11 + j * 21, 78, 17, 26)
        cell_bars(ax, full, col_, METH[:2], cells)
        ax.set_ylim(0.8, 1.0); ax.set_title(nm, fontsize=5.8, pad=1)
        if j == 0:
            ax.set_ylabel("r vs published")
        else:
            ax.set_yticklabels([])
    head_(fig, 54, 66, "f", "Held-out contacts", "both ends phased; cis")
    ho = r[r.kind == "heldout:eval_pairs"].copy()
    ho = ho.groupby(["cell", "m"], as_index=False).auc_cis.mean()
    ax = ax_at(fig, 64, 78, 24, 26)
    cell_bars(ax, ho, "auc_cis", METH, cells)
    ax.set_ylim(0.7, 1.0); ax.set_ylabel("ROC-AUC")
    head_(fig, 92, 66, "g", "Phase of masked ends", "known phases hidden, then inferred")
    mk_ = r[r.kind == "mask"]
    ax = ax_at(fig, 102, 78, 24, 26)
    cell_bars(ax, mk_, "phase_acc_all", METH, cells)
    ax.set_ylim(0.6, 0.95); ax.set_ylabel("accuracy")
    head_(fig, 130, 66, "h", "Wall time", "Dip-C cell 1; RTX 2080 Ti")
    ax = ax_at(fig, 142, 78, 24, 26)
    t = [("structure", [(NEW, 120), (ORIG, 1055)]), ("phase\nimputation", [(NEW, 3), (TEAL, 38)])]
    for i, (nm, bars) in enumerate(t):
        for k, (c, v) in enumerate(bars):
            ax.bar(i + (k - 0.5) * 0.36, v, 0.34, color=c)
            ax.text(i + (k - 0.5) * 0.36, v * 1.15, f"{v:,}", ha="center", fontsize=5)
    ax.set_yscale("log"); ax.set_ylim(1, 5000); ax.set_xticks(range(2), [n for n, _ in t], fontsize=5.3)
    ax.set_ylabel("seconds")
    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"figS_fig3_diploid.{ext}", dpi=300)
    print(HERE / "figS_fig3_diploid.pdf")


def mpl_patch(c, lab):
    import matplotlib as mpl
    return mpl.patches.Patch(color=c, label=lab)


if __name__ == "__main__":
    main()
