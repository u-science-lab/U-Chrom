"""Supplementary figure — EMber deep: homolog-resolved reconstruction of deep, sparsely phased
single-cell data (scMicro-C GM12878, Wu et al. 2025), behind Fig. 3a.

EMber deep = the frozen diploid EMber plus hard phasing by the neighbourhood prior (>= 0.75), the
unphased contacts re-admitted at 200 kb and kept only where the structure phases them (tag
``ember-deep-frozen``; ``benchmarks/screcon/PREREG.md`` §11, ``diploid_devlog.md`` §6,
``DEEP_TEST_RESULTS.md``).  Numbers: ``results/highres/deep.json``.

  a  resolution ladder of the deepest cell (035): particles, contacts used, wall time (one GPU),
     run-to-run and authors'-hickit agreement (per-copy distance r)
  b  development cells: run-to-run r at 20 kb, frozen diploid EMber vs EMber deep
  c  the one-shot test on 7 held-back cells: C1 (run-to-run r at 20 kb) and C2 (held-out cis
     ROC-AUC, EMber deep − NucDynamics-diploid)
  notes: accepted costs (phase coverage, held-out per cell)

    python paper/fig3/make_figS_fig3_highres.py      # -> figS_fig3_highres.pdf / .png
"""

from __future__ import annotations

import json
import textwrap

import matplotlib.pyplot as plt
import numpy as np

import make_fig3 as F
from make_fig3 import GREY, HERE, INK, LGREY, MM, NEW, RES, TEAL, ax_at, head_

W, H = 170.0, 112.0
F.W, F.H = W, H


def tag(res):
    return f"{res / 1000:g} kb"


def fmt(v, f="{:.2f}"):
    return "–" if v is None else f.format(v)


def table(fig, x, y, w, header, rows, widths, size=5.6, dy=3.4):
    xs = x + np.r_[0, np.cumsum(widths)[:-1]]
    for xx, h in zip(xs, header):
        fig.text(xx / W, 1 - y / H, h, fontsize=size, color=GREY, va="top", linespacing=1.1)
    y0 = y + 2.3 + dy * max(h.count("\n") for h in header)
    fig.add_artist(plt.Line2D([x / W, (x + w) / W], [1 - y0 / H] * 2, lw=0.4, color=LGREY))
    for i, row in enumerate(rows):
        for xx, c in zip(xs, row):
            fig.text(xx / W, 1 - (y0 + 1 + i * dy) / H, c, fontsize=size, color=INK, va="top")
    return y0 + 1 + len(rows) * dy


def short(cell):
    return cell.split("_cell_")[-1]


def main() -> None:
    D = json.loads((RES / "highres" / "deep.json").read_text())
    fig = plt.figure(figsize=(W * MM, H * MM))
    lad = D["ladder"]
    n = lad[0]["n_contacts"] if lad else 0
    head_(fig, 0, 2, "a", "EMber deep, resolution ladder (deepest cell)",
          f"GM12878 scMicro-C cell 035 (GSM5764669), {n / 1e6:.2f} M contacts; tag ember-deep-frozen; one {F.gpu_short(lad[0].get('gpu')) if lad else 'GPU'}; "
          "r: distance r of random particle pairs")
    rows = [[tag(r["res"]) + ("*" if r["res"] < 5000 else ""),
             f"{r['particles_grid'] / 1e6:.2f} / {r['particles_simulated'] / 1e6:.2f}",
             f"{r['contacts_last_stage'] / 1e6:.2f} ({r['coverage'] * 100:.0f} %)", f"{r['n_models']}",
             f"{r['wall_seconds'] / 60:.1f}", f"{fmt(r.get('seeds_r'))} / {fmt(r.get('seeds_whole'))}",
             fmt(r.get("vs_hickit")), fmt(r.get("hickit_runs"))] for r in lad]
    yy = table(fig, 5, 11, 160, ["final\nresolution", "particles (M)\ngrid / simulated", "contacts used (M)\n(% of input)",
                                 "models", "wall time\n(min)", "seed 1 vs 2, r\nper copy / whole",
                                 "vs authors'\nhickit, r", "authors' hickit\nruns vs each other"],
               rows, [15, 25, 25, 11, 17, 25, 20, 22])
    fig.text(5 / W, 1 - (yy + 1) / H, "* exploratory.  r per copy chain: median over the 46 copy chains.  Contacts used: committed to a copy pair by the prior or, "
             "after re-admission at 200 kb, by the structure; the others are left out.", fontsize=5, color=GREY, va="top")

    y2 = yy + 9
    head_(fig, 0, y2, "b", "Development cells", "run-to-run r at 20 kb")
    ax = ax_at(fig, 11, y2 + 11, 34, 30)
    dev = D["dev_seeds_20k"]
    cells = list(dev)
    xx = np.arange(len(cells))
    ax.bar(xx - 0.2, [dev[c].get("frozen", np.nan) for c in cells], 0.38, color=LGREY, label="frozen diploid EMber")
    ax.bar(xx + 0.2, [dev[c].get("deep", np.nan) for c in cells], 0.38, color=NEW, label="EMber deep")
    ax.set_xticks(xx, [short(c) for c in cells]); ax.set_xlabel("cell")
    ax.set_ylim(0, 1.05); ax.set_ylabel("Pearson r, per copy chain")
    ax.set_ylim(0, 1.3); ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.legend(frameon=False, fontsize=5, loc="upper left", ncol=2, handlelength=1, columnspacing=0.6)

    t = D.get("test") or {}
    head_(fig, 56, y2, "c", "Test: 7 held-back cells",
          "C1: r at 20 kb (median ≥ 0.90, each ≥ 0.85); C2: held-out cis AUC − NucDynamics (mean ≥ −0.01)")
    if t.get("cells"):
        tc = t["cells"]
        ax = ax_at(fig, 67, y2 + 11, 42, 30)
        xx = np.arange(len(tc))
        ax.bar(xx, [c.get("seeds_20k") or np.nan for c in tc], 0.6, color=NEW)
        ax.axhline(0.90, color=GREY, lw=0.6, ls="--"); ax.axhline(0.85, color=LGREY, lw=0.6, ls=":")
        ax.set_xticks(xx, [short(c["cell"]) for c in tc], fontsize=5.5); ax.set_ylim(0, 1.05)
        ax.set_ylabel("r at 20 kb (seeds)"); ax.set_xlabel("cell")
        bx = ax_at(fig, 122, y2 + 11, 42, 30)
        bx.bar(xx, [c.get("c2_delta") or np.nan for c in tc], 0.6, color=TEAL)
        bx.axhline(0, color=INK, lw=0.5); bx.axhline(-0.01, color=GREY, lw=0.6, ls="--")
        bx.set_xticks(xx, [short(c["cell"]) for c in tc], fontsize=5.5)
        bx.set_ylabel("Δ held-out cis AUC"); bx.set_xlabel("cell")
        res = (f"C1 {'met' if t.get('C1_met') else 'not met'}: median {t['C1_median']:.3f}, min {t['C1_min']:.3f}.  "
               f"C2 {'met' if t.get('C2_met') else 'not met'}: mean Δ {t['C2_mean_delta']:+.4f}.") \
            if t.get("complete") else "test incomplete"
        fig.text(67 / W, 1 - (y2 + 7.4) / H, res, fontsize=5.6, color=INK, va="top", fontweight="bold")
        cov = [c.get("phase_coverage_20k") for c in tc if c.get("phase_coverage_20k") is not None]
        npos = [c.get("deep_strict_n_pos") for c in tc if c.get("deep_strict_n_pos") is not None]
    else:
        cov, npos = [], []
    notes = ["Accepted costs (PREREG §11): fewer contacts carry a phase — on the Dip-C development cells the "
             "masked ends that receive a phase fall from 0.94 to 0.73 and the correct fraction over all masked ends "
             "from 0.83 to 0.71; on scMicro-C only the contacts committed to a copy pair are used"
             + (f" ({min(cov) * 100:.0f}-{max(cov) * 100:.0f} % of the input on the test cells)" if cov else "")
             + ".  The held-out criterion is met on the mean; per cell it varies in both directions"
             + (f" (strict positives per cell: {min(npos)}-{max(npos)}, so per-cell AUCs are noisy)" if npos else "")
             + ".  Agreement with the authors' structures is descriptive: they are hickit's own output."]
    yy = y2 + 50
    for n_ in notes:
        for line in textwrap.wrap(n_, 150):
            fig.text(2 / W, 1 - yy / H, line, fontsize=5.4, color=INK, va="top")
            yy += 2.6
    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"figS_fig3_highres.{ext}", dpi=300)
    print(HERE / "figS_fig3_highres.pdf")


if __name__ == "__main__":
    main()
