"""Supplementary figure — the original NucDynamics' repulsion-list overflow explains its divergent ensembles.

In tjs23/nuc_dynamics (2017 master) a neighbour-list build that finds more pairs than the list's
capacity replaces the list by zeros, which switches repulsion off until the next rebuild
(``benchmarks/fig3/nucdyn_spec.md`` §7).  The U-Chrom engine does not do this by default; with
``emulate_rep_list_overflow=True`` it reproduces the behaviour.  All runs: Stevens 2017 cells 1-8,
100 kb, full schedule, 10 models, CPU (``results/a_nucdyn_score_emul.json``).

  a  ensemble precision (RMSD to the ensemble mean, as ED Table 2) per cell
  b  agreement with the published models (median distance-matrix r) per cell

    python paper/fig3/make_figS_fig3_overflow.py      # -> figS_fig3_overflow.pdf / .png
"""

from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np

import make_fig3 as F
from make_fig3 import HERE, MM, OURS, PAPER, RES, ax_at, label, sub

W, H = 170.0, 62.0
F.W, F.H = W, H
SERIES = (("published", "published (GEO)", dict(s=14, color=PAPER)),
          ("orig_master_full", "original code", dict(s=18, facecolor="none", edgecolor="#6b7079", lw=0.8)),
          ("native_cpu_emul", "U-Chrom, overflow emulated", dict(s=16, marker="s", facecolor="none",
                                                                 edgecolor=OURS, lw=0.8)),
          ("native_cpu_full", "U-Chrom (default)", dict(s=14, marker="D", color=OURS)))


def main() -> None:
    cells = json.loads((RES / "a_nucdyn_score_emul.json").read_text())["cells"]
    pub = {c["cell"]: c for c in json.loads((RES / "a_nucdyn_score_all.json").read_text())["cells"]}
    fig = plt.figure(figsize=(W * MM, H * MM))
    x = np.arange(1, 9)
    for k, (key, ylab, log, letter, name) in enumerate((
            ("rmsd_to_mean_mirror_mean", "RMSD to ensemble mean (radii)", True, "a", "Ensemble precision"),
            ("vs_published_dist_r_median", "distance-matrix r vs published", False, "b",
             "Agreement with the published models"))):
        x0 = k * 86
        label(fig, x0, 2, letter)
        sub(fig, x0 + 5, 2.8, name, "Stevens 2017, 100 kb, 10 models per cell, CPU")
        ax = ax_at(fig, x0 + 14, 13, 66, 32)
        for i, (run, lab, style) in enumerate(SERIES):
            if run == "published":
                if key != "rmsd_to_mean_mirror_mean":
                    continue
                y = [pub[c["cell"]]["published"][key] for c in cells]
            else:
                y = [c[run][key] for c in cells]
            ax.scatter(x + (i - 1.5) * 0.12, y, label=lab, zorder=3, **style)
        if log:
            ax.set_yscale("log")
            ax.set_yticks([0.5, 1, 2, 5], ["0.5", "1", "2", "5"]); ax.minorticks_off()
        ax.set_xticks(x); ax.set_xlabel("cell"); ax.set_ylabel(ylab)
        if k == 0:
            ax.legend(frameon=False, fontsize=5.5, ncol=4, loc="upper left", bbox_to_anchor=(-0.18, -0.25),
                      handletextpad=0.2, columnspacing=1.0)
    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"figS_fig3_overflow.{ext}", dpi=300)
    print(HERE / "figS_fig3_overflow.pdf")


if __name__ == "__main__":
    main()
