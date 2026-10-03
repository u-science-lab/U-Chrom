"""Supplementary figure (draft) — single-cell Hi-C structures vs chromatin tracing of the same cell type.

No same-cell pairing exists, so both modalities are summarised over cells and compared feature by
feature (``benchmarks/screcon/matched.py``, branch Nanguage/matched-imaging; table copied from
Sherlock to ``results/matched/summary.csv``).  Grey band: from the best structure-free baseline
(random polymer, P(s)-only) to the imaging ceiling (imaging split in halves, ± sd).

  a  mESC: Nagano 2017 haploid serum cells (NucDynamics native, hickit) vs Takei 2021 Nature;
     open diamond: NucDynamics vs hickit on the same cells
  b  adult mouse cortex: Tan 2021 Dip-C published structures vs Takei 2021 Science
  c  cell-type specificity (cortex): Dip-C excitatory neurons or oligodendrocytes vs imaged
     excitatory neurons

    python paper/fig3/make_figS_fig3_matched.py      # -> figS_fig3_matched.pdf / .png
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import make_fig3 as F
from make_fig3 import GREY, HERE, INK, LGREY, MM, ORIG, OURS, RES, TEAL, ax_at, label, sub

W, H = 170.0, 84.0
F.W, F.H = W, H
FEATS = [(("pair", "median_resid_spearman"), "pair distances\n(detrended)"),
         (("radial", "locus_spearman"), "radial position\nper locus"),
         (("trans", "spearman"), "trans\nproximity"),
         (("variab", "cv_spearman"), "cell-to-cell\nvariability"),
         (("mingle", "chrom_spearman"), "intermingling\nper chromosome")]


def head_(fig, x, y, letter, name, note=None):
    label(fig, x, y, letter)
    sub(fig, x + 5, y + 0.8, name, note)


def rows(d, comparison):
    return d[d.comparison == comparison].set_index(["feature", "metric"])


def panel(fig, d, x, y, w, models, check=None, show_labels=True):
    ax = ax_at(fig, x, y, w, 46)
    yy = np.arange(len(FEATS))
    ref = rows(d, models[0][0])
    for i, (key, _) in enumerate(FEATS):
        r = ref.loc[key]
        base = max(r["random_polymer"], r["ps_only"], 0.0)
        ax.barh(i, r["ceiling"] - base, left=base, height=0.55, color=LGREY, alpha=0.6, lw=0)
        ax.errorbar(r["ceiling"], i, xerr=r["ceiling_sd"], color=GREY, lw=0.6, capsize=1.5)
        for k, (comp, lab, col, mk) in enumerate(models):
            v = rows(d, comp).loc[key, "model"]
            ax.scatter(v, i + (k - (len(models) - 1) / 2) * 0.18, s=14, color=col, marker=mk, zorder=3,
                       label=lab if i == 0 else None, lw=0)
        if check:
            v = rows(d, check).loc[key, "model"]
            ax.scatter(v, i, s=18, marker="D", facecolor="none", edgecolor=INK, lw=0.6, zorder=4,
                       label="NucDynamics vs hickit" if i == 0 else None)
    ax.set_yticks(yy, [n for _, n in FEATS] if show_labels else [""] * len(FEATS), fontsize=5.4)
    ax.invert_yaxis(); ax.set_xlim(-0.1, 1.02); ax.axvline(0, color=LGREY, lw=0.5)
    ax.set_xlabel("Spearman r vs imaging")
    ax.legend(frameon=False, fontsize=5.0, loc="upper left", bbox_to_anchor=(0, -0.2), ncol=1, handletextpad=0.1,
              columnspacing=0.6)
    return ax


def main() -> None:
    d = pd.read_csv(RES / "matched" / "summary.csv")
    fig = plt.figure(figsize=(W * MM, H * MM))
    head_(fig, 0, 2, "a", "mESC", "Nagano 2017 (373 haploid cells) vs Takei 2021")
    panel(fig, d, 22, 11, 36, [("mesc/nagano_serum/nucdyn_gpu", "U-Chrom NucDynamics", OURS, "o"),
                               ("mesc/nagano_serum/hickit", "hickit", TEAL, "s")],
          check="mesc/check/nagano_serum_nucdyn_vs_hickit")
    head_(fig, 62, 2, "b", "Adult mouse cortex", "Tan 2021 Dip-C (510 cells) vs Takei 2021")
    panel(fig, d, 66, 11, 36, [("brain/all/dipc", "Dip-C (published)", ORIG, "o")], show_labels=False)
    head_(fig, 108, 2, "c", "Cell-type specificity", "vs imaged excitatory neurons")
    ax = ax_at(fig, 122, 11, 40, 40)
    m = rows(d, "brain/Excitatory/dipc").loc[("pair", "median_resid_spearman")]
    x = rows(d, "brain/x_Oligodendrocyte_vs_Excitatory/dipc").loc[("pair", "median_resid_spearman")]
    ax.bar([0, 1], [m["model"], x["model"]], 0.6, color=[ORIG, LGREY])
    ax.errorbar([0, 1], [m["ceiling"], x["ceiling"]], yerr=[m["ceiling_sd"], x["ceiling_sd"]], fmt="_", color=GREY,
                ms=10, lw=0.6, capsize=2, label="imaging ceiling")
    ax.set_xticks([0, 1], ["Dip-C excitatory\n(matched)", "Dip-C oligodendro.\n(mismatched)"], fontsize=5.4)
    ax.set_ylabel("Spearman, detrended pair distances"); ax.set_ylim(0, 0.6)
    ax.legend(frameon=False, fontsize=5.2, loc="upper right")
    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"figS_fig3_matched.{ext}", dpi=300)
    print(HERE / "figS_fig3_matched.pdf")


if __name__ == "__main__":
    main()
