"""Markdown tables (validation, speed) from the Fig. 3a native-engine result JSONs.

Usage::

    python benchmarks/fig3/a_nucdyn_engine_tables.py [--results u-chrom-paper/figures/fig3/results]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def f(x, nd=2):
    return "–" if x is None else f"{x:.{nd}f}"


def validation_tables(v: dict, labels: list[str]) -> str:
    out = []
    out.append("| Cell | ED T2 RMSD unamb. / final | GEO models: RMSD to mean | "
               + " | ".join(f"{lab}: RMSD to mean (pairwise)" for lab in labels)
               + " | " + " | ".join(f"{lab}: vs GEO RMSD / dist r" for lab in labels)
               + " | GEO vs GEO dist r |")
    out.append("|" + "---|" * (3 + 2 * len(labels) + 1))
    for c in v["cells"]:
        e, p = c["ed_table2"], c["published"]
        row = [str(c["cell"]), f"{e['100kb_unambig']['rmsd']:.2f} / {e['100kb_final']['rmsd']:.2f}",
               f(p["rmsd_to_mean_mean"])]
        for lab in labels:
            g = c.get(lab)
            row.append("–" if not g else f"{f(g['rmsd_to_mean_mirror_mean'])} ({f(g['rmsd_pair_mirror_mean'])})")
        for lab in labels:
            g = c.get(lab)
            row.append("–" if not g else f"{f(g['vs_published_rmsd_mirror_mean'])} / {f(g['vs_published_dist_r_median'], 3)}")
        row.append(f(p.get("pub_vs_pub_dist_r_median"), 3))
        out.append("| " + " | ".join(row) + " |")
    out.append("")
    out.append("| Cell | ED T2 %V>3 / %V>4 (unamb.) | GEO models %V>3 / %V>4 | "
               + " | ".join(f"{lab} %V>3 / %V>4" for lab in labels) + " | "
               + " | ".join(f"{lab}: models mirrored vs model 0" for lab in labels) + " |")
    out.append("|" + "---|" * (3 + 2 * len(labels)))
    for c in v["cells"]:
        e, p = c["ed_table2"], c["published"]
        row = [str(c["cell"]), f"{e['100kb_unambig']['pct_v3']:.2f} / {e['100kb_unambig']['pct_v4']:.2f}",
               f"{p['pct_viol_gt3']:.2f} / {p['pct_viol_gt4']:.2f}"]
        for lab in labels:
            g = c.get(lab)
            row.append("–" if not g else f"{g['pct_viol_gt3']:.2f} / {g['pct_viol_gt4']:.2f}")
        for lab in labels:
            g = c.get(lab)
            row.append("–" if not g else str(g["n_models_mirror_of_model0"]))
        out.append("| " + " | ".join(row) + " |")
    return "\n".join(out)


def scaling_tables(sp: dict) -> str:
    out = []
    for key, runs in sp.get("runs", {}).items():
        if key.startswith("models"):
            out.append(f"\n**Ensemble size ({key}; {runs[0].get('temp_steps', 500)} temperature steps per stage, "
                       "totals scaled to the default 500)**\n")
            out.append("| device | models | wall s (scaled) | CPU s (scaled) | wall s per model | models / hour (wall) | peak RSS MB |")
            out.append("|---|---|---|---|---|---|---|")
            for r in runs:
                if "error" in r:
                    continue
                k = 500 / r.get("temp_steps", 500)
                t = r["engine_seconds"] * k
                out.append(f"| {r['device']} | {r['n_models']} | {t:.0f} | {r['cpu_seconds'] * k:.0f} | "
                           f"{t / r['n_models']:.1f} | {3600 * r['n_models'] / t:.0f} | {r['peak_rss_mb']:.0f} |")
        if key.startswith("particles"):
            out.append(f"\n**Final resolution ({key}; 10 models, totals scaled to 500 temperature steps)**\n")
            out.append("| device | final | particles | wall s (scaled) | CPU s (scaled) | peak RSS MB |")
            out.append("|---|---|---|---|---|---|")
            for r in runs:
                if "error" in r:
                    continue
                k = 500 / r.get("temp_steps", 500)
                out.append(f"| {r['device']} | {r['final']} | {r['n_particles']} | {r['engine_seconds'] * k:.0f} | "
                           f"{r['cpu_seconds'] * k:.0f} | {r['peak_rss_mb']:.0f} |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sys.path.insert(0, str(ROOT / "benchmarks"))
    from _paper import results_dir
    ap.add_argument("--results", type=Path, default=results_dir("fig3"))
    ap.add_argument("--validation", default="a_nucdyn_engine_validation.json")
    args = ap.parse_args()
    vp = args.results / args.validation
    if vp.exists():
        v = json.loads(vp.read_text())
        print(validation_tables(v, v["labels"]))
    sp = args.results / "a_nucdyn_engine_speed.json"
    if sp.exists():
        print(scaling_tables(json.loads(sp.read_text())))


if __name__ == "__main__":
    main()
