"""Supplementary figure — the single-cell reconstruction benchmark in detail.

Tables from ``benchmarks/screcon/aggregate.py`` (``results/screcon/{heldout,sim}.csv``).
Held-out test: Stevens 2017 cells 1-8, 3 folds, held-out contacts vs negatives matched in
genomic separation (cis) or drawn from shuffled trans pairs; scores from the 10-model
ensemble (median distance, or fraction of models in contact).  Simulations: contacts drawn
from imaged single-cell structures (Su 2020 IMR90 chr21, 50 kb; Takei 2021 mESC, 1 Mb, whole
genome) at three depths, two contact radii and three noise levels, five structures each; scored
against the true structure (median over the ensemble's models).

  a  held-out AUC per cell and fold: U-Chrom GPU vs each other method
  b  held-out AUC per separation band with the contact-fraction score
  c  simulations: Spearman of cis distances per depth, Su 2020 chr21
  d  the same for Takei 2021 (matched cases)
  e  scale-free RMSD to the true structure
  f  runs completed per method (Si-C: no 50 kb setup for Su 2020 chr21; 16 Takei runs over 12 h)

    python paper/fig3/make_figS_fig3_benchmark.py      # -> figS_fig3_benchmark.pdf / .png
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import make_fig3 as F
from make_fig3 import BANDS, GREY, HERE, INK, LGREY, MM, RES, SC_METHODS, ax_at, label, sub

W, H = 170.0, 126.0
F.W, F.H = W, H
METHODS = dict(SC_METHODS, pop_ps=("P(s) polymer", "#e6c46a"))
CMP = ["orig", "sic", "hickit"]


def head_(fig, x, y, letter, name, note=None):
    label(fig, x, y, letter)
    sub(fig, x + 5, y + 0.8, name, note)


def main() -> None:
    h = pd.read_csv(RES / "screcon" / "heldout.csv")
    s = pd.read_csv(RES / "screcon" / "sim.csv")
    fig = plt.figure(figsize=(W * MM, H * MM))

    head_(fig, 0, 2, "a", "Held-out AUC per cell", "cis, median-distance score; 8 cells × 3 folds")
    cis = h[(h.score == "median") & (h.subset == "cis")].pivot_table(index=["cell", "fold"], columns="method",
                                                                     values="roc_auc")
    ax = ax_at(fig, 12, 12, 34, 34)
    for m in CMP:
        ax.scatter(cis["nucdyn_gpu"], cis[m], s=7, color=METHODS[m][1], label=METHODS[m][0], lw=0)
    lo, hi = float(cis[["nucdyn_gpu"] + CMP].min().min()) - 0.01, float(cis[["nucdyn_gpu"] + CMP].max().max()) + 0.01
    ax.plot([lo, hi], [lo, hi], color=GREY, lw=0.6, ls="--")
    ax.set_xlim(lo, hi); ax.set_ylim(lo, hi)
    ax.set_xlabel("U-Chrom GPU"); ax.set_ylabel("other method")
    ax.legend(frameon=False, fontsize=5.3, loc="upper left", handletextpad=0.1)

    head_(fig, 58, 2, "b", "Contact-fraction score", "fraction of the 10 models in contact")
    fr = h[(h.score == "frac") & (h.subset == "cis_band")].groupby(["method", "band"]).roc_auc.mean()
    ax = ax_at(fig, 70, 12, 36, 34)
    for m in ["random_polymer", "hickit", "sic", "orig", "nucdyn_cpu", "nucdyn_gpu"]:
        ax.plot(range(len(BANDS)), [fr.loc[(m, k)] for k, _ in BANDS], color=METHODS[m][1], marker="o", ms=2,
                lw=0.8, ls=(0, (2, 1)) if m == "nucdyn_cpu" else "-")
    ax.set_xticks(range(len(BANDS)), [b for _, b in BANDS], fontsize=5.3)
    ax.set_xlabel("genomic separation (Mb)"); ax.set_ylabel("ROC-AUC"); ax.set_ylim(0.45, 1.0)

    keys = ["truth", "depth_per_mb", "rc_rel", "eps", "seed"]
    order = ["nucdyn_gpu", "nucdyn_cpu", "orig", "sic", "hickit", "pop_mean", "pop_ps", "random_polymer"]
    for i_, (ds, name, x0) in enumerate((("su2020_chr21", "Su 2020 chr21, 50 kb", 116),
                                         ("takei2021_1mb", "Takei 2021 genome, 1 Mb", 0))):
        g = s[s.dataset == ds]
        ran = list(g[g.kind == "method"].method.unique())
        ok = g[g.kind == "method"].groupby(keys).method.nunique()
        ok = ok[ok == len(ran)].index
        g = g.set_index(keys).loc[g.set_index(keys).index.isin(ok)].reset_index()
        by = g.groupby(["depth_per_mb", "method"]).med_dist_spearman_cis.mean().unstack()
        letter, y0 = ("c", 2) if i_ == 0 else ("d", 62)
        head_(fig, x0, y0, letter, name, f"{len(ok)} matched simulations")
        ax = ax_at(fig, x0 + 12, y0 + 10, 36, 34)
        for m in order:
            if m in by:
                ax.plot(range(len(by)), by[m], color=METHODS[m][1], marker="o", ms=2, lw=0.8,
                        ls=(0, (2, 1)) if m == "nucdyn_cpu" else "-", label=METHODS[m][0])
        ax.set_xticks(range(len(by)), [f"{v:g}" for v in by.index])
        ax.set_xlabel("contacts per Mb (simulated depth)"); ax.set_ylabel("Spearman, cis distances")
        ax.set_ylim(0, 0.95)

    head_(fig, 58, 62, "e", "RMSD to the truth", "scale-free, median model; lower is better")
    ax = ax_at(fig, 70, 72, 40, 34)
    w = 0.1
    for i_, ds in enumerate(("su2020_chr21", "takei2021_1mb")):
        g = s[s.dataset == ds].groupby("method").med_rmsd_rel.mean()
        for k_, m in enumerate(order):
            if m in g:
                ax.bar(i_ + (k_ - 3.5) * w, g[m], w * 0.9, color=METHODS[m][1])
    ax.set_xticks(range(2), ["Su 2020 chr21", "Takei 2021"]); ax.set_ylabel("RMSD / truth size")

    head_(fig, 116, 62, "f", "Runs completed", "of 90 simulations per dataset")
    ax = ax_at(fig, 128, 72, 36, 34)
    cnt = s[s.kind == "method"].groupby(["dataset", "method"]).size().unstack(0).reindex(
        ["nucdyn_gpu", "nucdyn_cpu", "orig", "sic", "hickit"]).fillna(0)
    yy = np.arange(len(cnt))
    for j_, (ds, col) in enumerate((("su2020_chr21", "#7f9bd0"), ("takei2021_1mb", INK))):
        ax.barh(yy + (j_ - 0.5) * 0.36, cnt[ds], 0.34, color=col, label=ds.split("_")[0].replace("2020", " 2020")
                .replace("takei2021", "Takei 2021").replace("su", "Su"))
    ax.set_yticks(yy, [METHODS[m][0] for m in cnt.index], fontsize=5.3); ax.invert_yaxis()
    ax.set_xlabel("runs"); ax.set_xlim(0, 95)
    ax.legend(frameon=False, fontsize=5.2, loc="lower right", bbox_to_anchor=(1.02, 1.0), ncol=2, handlelength=1)
    ax.text(1, yy[3] - 0.18, "Su 2020: no 50 kb setup", fontsize=4.8, color=GREY, va="center")

    hs = [plt.Line2D([], [], color=METHODS[m][1], marker="o", ms=2, lw=0.8, label=METHODS[m][0]) for m in order]
    fig.legend(handles=hs, loc="upper left", bbox_to_anchor=(6 / W, 1 - 118 / H), ncol=8, frameon=False,
               fontsize=5.2, handlelength=1.2, columnspacing=0.8)
    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"figS_fig3_benchmark.{ext}", dpi=300)
    print(HERE / "figS_fig3_benchmark.pdf")


if __name__ == "__main__":
    main()
