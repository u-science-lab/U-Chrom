"""Collect the score JSONs of the benchmark into tidy tables (CSV + JSON) for figures.

    python benchmarks/screcon/aggregate.py --heldout RUNS/heldout/scores --sim RUNS/sim/scores \\
        --real RUNS/real/scores --out paper/screcon/results

Writes
* ``heldout.csv``: one row per (cell, fold, method, score type, subset[, band]) with
  ROC-AUC, PR-AUC, CIs, n_pos / n_neg, coverage;
  file names ``cell<c>_fold<f>.json`` (from ``heldout.py score``);
* ``sim.csv``: one row per (dataset, truth, depth, rc_rel, eps, seed, method) with the
  median-over-models and ensemble-mean metrics; methods and baselines alike
  (``kind`` = method | baseline); file names ``<dataset>/<table name>.json``;
* ``real.csv``: one row per (run tag, method) with precision, violations and vs-reference;
* ``summary.json``: method-level means / medians of the headline metrics.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

import numpy as np


def _write(rows, path: Path) -> None:
    if not rows:
        return
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def heldout_rows(d: Path):
    rows = []
    for f in sorted(d.rglob("*.json")):
        m = re.search(r"cell(\d+)_fold(\d+)", f.name)
        if not m:
            continue
        j = json.loads(f.read_text())
        for meth, r in j.get("methods", {}).items():
            for stype in ("median", "frac"):
                if stype not in r:
                    continue
                subsets = [(k, None, r[stype][k]) for k in ("all", "cis", "trans") if k in r[stype]]
                subsets += [("cis_band", b, v) for b, v in r[stype].get("cis_bands", {}).items()]
                for sub, band, v in subsets:
                    rows.append({"cell": int(m.group(1)), "fold": int(m.group(2)), "method": meth, "score": stype,
                                 "subset": sub, "band": band, "roc_auc": v.get("roc_auc"), "pr_auc": v.get("pr_auc"),
                                 "roc_auc_lo": (v.get("roc_auc_ci95") or [None, None])[0],
                                 "roc_auc_hi": (v.get("roc_auc_ci95") or [None, None])[1],
                                 "pr_auc_lo": (v.get("pr_auc_ci95") or [None, None])[0],
                                 "pr_auc_hi": (v.get("pr_auc_ci95") or [None, None])[1],
                                 "pr_auc_chance": v.get("pr_auc_chance"), "n_pos": v.get("n_pos"),
                                 "n_neg": v.get("n_neg"), "coverage_pos": r.get("coverage_pos"),
                                 "ps_baseline_cis_auc": r.get("ps_baseline_cis_auc")})
    return rows


NAME = re.compile(r"(?P<truth>truth_\d+)_d(?P<depth>[\d.]+)_rc(?P<rc>[\d.]+)_e(?P<eps>[\d.]+)_s(?P<seed>\d+)")


def sim_rows(d: Path):
    rows = []
    for f in sorted(d.rglob("*.json")):
        m = NAME.search(f.stem)
        if not m:
            continue
        j = json.loads(f.read_text())
        base = {"dataset": f.parent.name, "truth": m["truth"], "depth_per_mb": float(m["depth"]),
                "rc_rel": float(m["rc"]), "eps": float(m["eps"]), "seed": int(m["seed"])}
        for kind in ("methods", "baselines"):
            for meth, r in j.get(kind, {}).items():
                row = {**base, "kind": kind[:-1], "method": meth, "n_models": r.get("n_models"),
                       "n_loci_scored": r.get("n_loci_scored"), "coverage": r.get("coverage")}
                row.update({f"med_{k}": v for k, v in r.get("median_over_models", {}).items()})
                row.update({f"best_{k}": v for k, v in r.get("best_model", {}).items()})
                row.update({f"ens_{k}": v for k, v in r.get("ensemble_mean", {}).items() if not isinstance(v, bool)})
                row.update({f"dm_{k}": v for k, v in r.get("distance_matrix", {}).items()})
                rows.append(row)
    return rows


def real_rows(d: Path):
    rows = []
    for f in sorted(d.rglob("*.json")):
        j = json.loads(f.read_text())
        items = list(j.get("methods", {}).items())
        if "reference_self" in j:
            items.append(("reference", j["reference_self"]))
        for meth, r in items:
            row = {"source": d.name, "tag": f.stem, "method": meth, "n_models": r.get("n_models"), "n_particles": r.get("n_particles")}
            row.update({f"prec_{k}": v for k, v in r.get("precision", {}).items() if not isinstance(v, bool)})
            row.update({f"viol_{k}": v for k, v in r.get("violations", {}).items()})
            row.update({f"ref_{k}": v for k, v in r.get("vs_reference", {}).items()})
            rows.append(row)
    return rows


def summarise(rows, keys, group=("method",), filt=None):
    out = {}
    for r in rows:
        if filt and not filt(r):
            continue
        g = " | ".join(str(r.get(k)) for k in group)
        for k in keys:
            v = r.get(k)
            if isinstance(v, (int, float)) and v == v:
                out.setdefault(g, {}).setdefault(k, []).append(v)
    return {g: {k: {"mean": float(np.mean(v)), "median": float(np.median(v)), "n": len(v)} for k, v in d.items()}
            for g, d in out.items()}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--heldout", type=Path)
    ap.add_argument("--sim", type=Path)
    ap.add_argument("--real", type=Path, nargs="+", help="score_real.py outputs (full tables and held-out folds)")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    summary = {}
    if args.heldout:
        rows = heldout_rows(args.heldout)
        _write(rows, args.out / "heldout.csv")
        summary["heldout"] = summarise(rows, ["roc_auc", "pr_auc"], ("method", "score", "subset"),
                                       lambda r: r["subset"] != "cis_band")
    if args.sim:
        rows = sim_rows(args.sim)
        _write(rows, args.out / "sim.csv")
        summary["sim"] = summarise(rows, ["med_rmsd_rel", "med_dist_spearman_whole", "med_dist_spearman_cis",
                                          "ens_dist_spearman_whole"], ("dataset", "method"))
    if args.real:
        rows = [r for d in args.real for r in real_rows(d)]
        _write(rows, args.out / "real.csv")
        summary["real"] = summarise(rows, ["prec_rmsd_to_mean_per_unit", "viol_nd_pct_viol_gt4",
                                           "viol_sic_pct_viol_gt2units", "ref_dist_r_median"], ("method",))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1)[:4000])


if __name__ == "__main__":
    main()
