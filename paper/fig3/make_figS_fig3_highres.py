"""Supplementary figure — EMber (U-Chrom) diploid at high resolution on scMicro-C GM12878 (Wu et al. 2025).

A demonstration (not part of the pre-registered tests; frozen EMber diploid defaults, nothing tuned) behind
Fig. 3a.  Numbers from ``results/highres/summary.json`` (``benchmarks/screcon/highres.py summary`` on the
Sherlock runs of ``sherlock/highres_run.sbatch`` / ``highres_score.sbatch``):

  a  resolution ladder on the deepest cell (035): particles, contacts per particle, wall time and peak GPU
     memory (10 models, one H100; 2 kb / 1 kb exploratory, 5 models), run-to-run agreement (seed 1 vs 2)
     and agreement with the authors' hickit structures (five hickit runs; descriptive: those are hickit's
     output, not ground truth) — Pearson r of distances over random particle pairs, per copy chain
     (median over chains) and over the whole genome
  b  the agreements vs resolution
  c  controls at 100 kb: EMber with hickit's phase prior (diagnostic, not the frozen method), the NucDynamics
     2017 protocol with diploid ambiguous restraints, our own hickit runs (Dip-C pipeline, 5 models)
  d  wall time and GPU memory vs resolution
  e  the five deepest cells at 5 kb; notes: held-out contacts at 10 kb (10 % of the reads, one fold), diagnosis

    python paper/fig3/make_figS_fig3_highres.py      # -> figS_fig3_highres.pdf / .png
"""

from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np

import make_fig3 as F
from make_fig3 import GREY, HERE, INK, LGREY, MM, NEW, RES, TEAL, ax_at, head_

W, H = 170.0, 156.0
F.W, F.H = W, H
MAIN = "GSM5764669_cell_035"


def tag(res: float) -> str:
    return f"{res / 1000:g} kb"


def runs_of(cell: dict, seed: int = 1) -> list[dict]:
    return sorted([r for r in cell["runs"] if r["seed"] == seed and r["set"] in ("ladder", "explore")],
                  key=lambda r: -r["res"])


def score(cell: dict, res: float, key: str, field: str):
    s = cell["scores"].get(f"res{int(res)}") or {}
    v = s.get(key)
    return v.get(field) if isinstance(v, dict) else None


def ref_score(cell: dict, res: float, field: str):
    s = cell["scores"].get(f"ref_res{int(res)}") or {}
    v = s.get("a_within")
    return v.get(field) if isinstance(v, dict) else None


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


def main() -> None:
    S = json.loads((RES / "highres" / "summary.json").read_text())
    cells = S["cells"]
    C = cells[MAIN]
    fig = plt.figure(figsize=(W * MM, H * MM))
    n = C["runs"][0]["n_contacts_input"]
    head_(fig, 0, 2, "a", "Resolution ladder, deepest cell",
          f"GM12878 scMicro-C cell 035 (GSM5764669), {n / 1e6:.2f} M contacts; EMber diploid, frozen defaults, one H100; "
          "r: Pearson, distances of random particle pairs")
    rows = []
    for r in runs_of(C):
        res = r["res"]
        expl = r["set"] == "explore"
        rows.append([tag(res) + (" *" if expl else ""), f"{r['particles_grid'] / 1e6:.2f} / {r['particles_simulated'] / 1e6:.2f}",
                     f"{r['contacts_per_particle']:.2f}", f"{r['n_models']}",
                     f"{r['wall_seconds'] / 60:.1f}", fmt(r["gpu"]["peak_mib"] / 1024 if r.get("gpu") else None, "{:.1f}"),
                     f"{fmt(score(C, res, 'a_vs_b', 'per_copy_r'))} / {fmt(score(C, res, 'a_vs_b', 'whole_r'))}",
                     f"{fmt(score(C, res, 'a_vs_ref', 'per_copy_r'))} / {fmt(score(C, res, 'a_vs_ref', 'whole_r'))}",
                     f"{fmt(ref_score(C, res, 'per_copy_r'))} / {fmt(ref_score(C, res, 'whole_r'))}"])
    table(fig, 5, 11, 163,
          ["final\nresolution", "particles (M)\ngrid / simulated", "contacts per\nparticle", "models", "wall time\n(min)",
           "peak GPU\nmemory (GB)", "seed 1 vs 2, r\nper copy / whole", "EMber vs hickit, r\nper copy / whole",
           "hickit vs hickit, r\nper copy / whole"],
          rows, [14, 23, 15, 10, 14, 16, 24, 25, 24])
    fig.text(5 / W, 1 - (11 + 7 + 3.4 * (len(rows) + 1)) / H,
             "* exploratory (5 models, seed 1).  Wall time: one process, contacts read to models written.  Simulated "
             "particles: those holding a contact end (adaptive resolution below 25 kb; the others interpolated).\n"
             "Per copy chain: median over the 46 chains.  hickit: the authors' five runs (5 / 10 / 20 kb; at 100 kb "
             "their 20 kb runs on the 100 kb grid), every EMber model vs every run.",
             fontsize=5, color=GREY, va="top")


    # b agreement vs resolution
    y2 = 48
    head_(fig, 0, y2, "b", "Agreement vs resolution", "cell 035; per copy chain (solid), whole genome (dashed)")
    ax = ax_at(fig, 11, y2 + 11, 38, 30)
    lad = sorted({r["res"] for r in C["runs"] if r["set"] == "ladder"}, reverse=True)
    for key, lab, col in (("a_vs_b", "EMber seed 1 vs 2", NEW), ("a_vs_ref", "EMber vs hickit (authors)", TEAL),
                          (None, "hickit vs hickit (authors' runs)", GREY)):
        for field, ls in (("per_copy_r", "-"), ("whole_r", "--")):
            ys = [score(C, r, key, field) if key else ref_score(C, r, field) for r in lad]
            pts = [(r, v) for r, v in zip(lad, ys) if v is not None]
            if pts:
                ax.plot(*zip(*pts), color=col, ls=ls, marker="o", ms=2.2, lw=0.9, label=lab if ls == "-" else None)
    ax.set_xscale("log"); ax.set_xlim(max(lad) * 1.4, min(lad) / 1.4)
    ax.set_xticks(lad, [tag(r) for r in lad]); ax.minorticks_off()
    ax.set_ylabel("Pearson r, distances"); ax.set_xlabel("resolution"); ax.set_ylim(0, 1.02)
    ax.legend(frameon=False, fontsize=4.8, loc="upper left", bbox_to_anchor=(-0.3, -0.24), handlelength=1.5,
              labelspacing=0.2)

    # c controls at 100 kb
    head_(fig, 56, y2, "c", "Controls at 100 kb", "cell 035; models of one run vs another (or vs the authors')")
    ax = ax_at(fig, 68, y2 + 11, 46, 30)
    sc = C["scores"]
    g = lambda k, cmp, f: ((sc.get(k) or {}).get(cmp) or {}).get(f)          # noqa: E731
    bars = [("EMber seeds", g("res100000", "a_vs_b", "per_copy_r"), g("res100000", "a_vs_b", "whole_r"), NEW),
            ("EMber vs authors", g("res100000", "a_vs_ref", "per_copy_r"), g("res100000", "a_vs_ref", "whole_r"), NEW),
            ("EMber, hickit prior *", g("ember_hickitprior_res100000", "a_vs_b", "per_copy_r"),
             g("ember_hickitprior_res100000", "a_vs_b", "whole_r"), "#e8a0a9"),
            ("NucDynamics seeds", g("nucdyn_res100000", "a_vs_b", "per_copy_r"), g("nucdyn_res100000", "a_vs_b", "whole_r"),
             F.ORIG),
            ("our hickit, within run", g("ourhickit_res100000", "a_within", "per_copy_r"),
             g("ourhickit_res100000", "a_within", "whole_r"), TEAL),
            ("our hickit vs authors", g("ourhickit_res100000", "a_vs_ref", "per_copy_r"),
             g("ourhickit_res100000", "a_vs_ref", "whole_r"), TEAL),
            ("authors' hickit runs", g("ref_res100000", "a_within", "per_copy_r"), g("ref_res100000", "a_within", "whole_r"),
             GREY)]
    for k, (lab, pc, wh, col) in enumerate(bars):
        if pc is not None:
            ax.bar(k - 0.19, pc, 0.36, color=col)
        if wh is not None:
            ax.bar(k + 0.19, wh, 0.36, color=col, alpha=0.45)
    ax.set_xticks(range(len(bars)), [b[0] for b in bars], fontsize=4.6, rotation=35, ha="right",
                  rotation_mode="anchor")
    ax.set_ylim(0, 1.02); ax.set_ylabel("Pearson r, distances")
    ax.text(0.02, 0.99, "solid: per copy chain; pale: whole genome\n* diagnostic, not the frozen method; seeds",
            transform=ax.transAxes, ha="left", va="top", fontsize=4.6, color=GREY)
    ax.set_ylim(0, 1.18); ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])

    # d time and memory
    head_(fig, 122, y2, "d", "Time and GPU memory", "cell 035, one H100")
    ax = ax_at(fig, 131, y2 + 11, 28, 30)
    rs = runs_of(C)
    res = [r["res"] for r in rs]
    ax.plot(res, [r["wall_seconds"] / 60 for r in rs], color=NEW, marker="o", ms=2.2, lw=0.9)
    ax.set_xscale("log"); ax.set_xlim(max(res) * 1.4, min(res) / 1.4)
    ax.set_xticks(res, [tag(r).replace(" kb", "k") for r in res], fontsize=4.8); ax.minorticks_off()
    ax.set_ylabel("wall time (min)", color=NEW, labelpad=1); ax.set_ylim(0, None)
    bx = ax.twinx()
    bx.plot(res, [r["gpu"]["peak_mib"] / 1024 if r.get("gpu") else np.nan for r in rs], color=GREY, marker="s", ms=2,
            lw=0.9)
    bx.set_ylabel("peak GPU memory (GB)", color=GREY, labelpad=1); bx.set_ylim(0, None)
    bx.spines["right"].set_visible(True)
    ax.set_xlabel("resolution", labelpad=1)

    # e the five deepest cells at 5 kb
    y3 = 106
    head_(fig, 0, y3, "e", "Five deepest cells, 5 kb", "10 models; seeds 1 and 2; r per copy chain")
    rows = []
    for name, c in sorted(cells.items(), key=lambda kv: -(kv[1]["runs"][0]["n_contacts_input"] if kv[1]["runs"] else 0)):
        r = next((r for r in c["runs"] if r["set"] == "ladder" and r["res"] == 5000 and r["seed"] == 1), None)
        if not r:
            continue
        rows.append([name.split("_", 1)[1].replace("cell_", ""), f"{r['n_contacts_input'] / 1e6:.2f}",
                     f"{r['wall_seconds'] / 60:.1f}", fmt(r["gpu"]["peak_mib"] / 1024 if r.get("gpu") else None, "{:.1f}"),
                     fmt(score(c, 5000, "a_vs_b", "per_copy_r")), fmt(score(c, 5000, "a_vs_ref", "per_copy_r")),
                     fmt(ref_score(c, 5000, "per_copy_r"))])
    table(fig, 5, y3 + 10, 70, ["cell", "contacts\n(M)", "wall\n(min)", "GPU\n(GB)", "EMber\nseeds", "EMber vs\nhickit",
                                "hickit\nruns"], rows, [8, 10, 9, 9, 10, 12, 10], size=5.2)

    # notes: held-out contacts, diagnosis
    import textwrap
    ho = C.get("heldout", {})
    parts = []
    for k, lab in (("heldout_fold1_eval_pairs", "strict"), ("heldout_fold1_eval_pairs_cis", "cis < 2 Mb same homolog")):
        v = ho.get(k)
        if v and v.get("cis"):
            parts.append(f"{lab}: cis ROC-AUC {v['cis']['roc_auc']:.2f}, trans "
                         f"{fmt((v.get('trans') or {}).get('roc_auc'), '{:.2f}')}")
    notes = []
    if parts:
        notes.append("Held-out contacts at 10 kb (cell 035; 10 % of the reads held out, one fold; separation-matched "
                     "never-contacted negatives): " + "; ".join(parts) + ".")
    notes.append("On this data the native engine's diploid formulation (EMber and the NucDynamics 2017 protocol, every "
                 "unphased contact one ambiguous restraint over its candidate copy pairs) does not reproduce between "
                 "runs, at any resolution and separation, while hickit's pipeline (2-D phase imputation, homologs split at "
                 "p >= 0.75, isolated-contact filters -c1 / -c5) does; on Dip-C GM12878 (1 M contacts) EMber reached "
                 "r 0.98 between seeds and 0.90 vs the published hickit structure with the same metric.  EMber's own "
                 "phase prior is not the cause (hickit's prior: same agreement).  Its noise estimate is bistable here "
                 "(eps 0.5 in the 100 kb runs, 1e-4 in the others).  Not tuned (demonstration).")
    yy = y3 + 10
    for n_ in notes:
        for line in textwrap.wrap(n_, 88):
            fig.text(80 / W, 1 - yy / H, line, fontsize=5.3, color=INK, va="top")
            yy += 2.6
        yy += 1.2
    for ext in ("pdf", "png"):
        fig.savefig(HERE / f"figS_fig3_highres.{ext}", dpi=300)
    print(HERE / "figS_fig3_highres.pdf")


if __name__ == "__main__":
    main()
