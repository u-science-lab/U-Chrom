"""Tables of the diploid benchmarks (stdout markdown + csv).

``sim``   ``diploid_sim.py score`` JSONs -> one row per (table, method): dataset, truth, depth, rc,
          eps, phased, median-over-models Spearman cis / whole, homolog Spearman, swap fraction,
          phase accuracy; summary = mean per method over all tables and per stratum, and paired
          differences vs ``--ref`` (default ``nucdyn``) with a bootstrap CI over truth cells.
``real``  ``dip_real.sbatch`` score JSONs (full / mask / heldout) -> per cell and method.

    python benchmarks/screcon/diploid_aggregate.py sim --scores RUNS/diploid/sim/scores --out TABLES/sim
    python benchmarks/screcon/diploid_aggregate.py real --root RUNS/diploid/real/res100000 --out TABLES/real
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

COND = re.compile(r"^(truth_\d+)_d([\d.]+)_rc([\d.]+)_e([\d.]+)_p([\d.]+)_s(\d+)$")


def sim_rows(root: Path) -> pd.DataFrame:
    rows = []
    for f in sorted(root.glob("*/*.json")):
        d = json.loads(f.read_text())
        m = COND.match(f.stem)
        if not m:
            continue
        t, depth, rc, eps, ph, seed = m.groups()
        for meth, r in d["methods"].items():
            mo = r["median_over_models"]
            rows.append({"dataset": f.parent.name, "table": f.stem, "truth": t, "depth": float(depth), "rc": float(rc),
                         "eps": float(eps), "phased": float(ph), "method": meth,
                         "spearman_cis": mo.get("dist_spearman_cis"), "spearman_whole": mo.get("dist_spearman_whole"),
                         "homolog_spearman": r.get("homolog_spearman"), "swap_frac": r.get("swap_frac"),
                         "phase_acc": r.get("phase_acc_all"), "phase_acc_trans": r.get("phase_acc_trans"),
                         "phase_acc_cis_ge10mb": r.get("phase_acc_cis_ge10mb"),
                         "phase_acc_cis_lt10mb": r.get("phase_acc_cis_lt10mb")})
    return pd.DataFrame(rows)


def paired(df: pd.DataFrame, metric: str, ref: str, n_boot: int = 2000, seed: int = 0) -> pd.DataFrame:
    w = df.pivot_table(index=["dataset", "table", "truth"], columns="method", values=metric)
    out = []
    rng = np.random.default_rng(seed)
    for meth in w.columns:
        if meth == ref:
            continue
        d = (w[meth] - w[ref]).dropna()
        if d.empty:
            continue
        units = d.groupby(level=["dataset", "truth"]).mean()        # truth cells are the units
        bs = [rng.choice(units.values, len(units)).mean() for _ in range(n_boot)]
        out.append({"metric": metric, "method": meth, "vs": ref, "mean_diff": float(d.mean()),
                    "ci_lo": float(np.percentile(bs, 2.5)), "ci_hi": float(np.percentile(bs, 97.5)),
                    "n_tables": int(len(d)), "n_truths": int(len(units))})
    return pd.DataFrame(out)


def cmd_sim(args) -> None:
    df = sim_rows(Path(args.scores))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "sim_rows.csv", index=False)
    metrics = ["spearman_cis", "spearman_whole", "homolog_spearman", "swap_frac", "phase_acc"]
    summ = df.groupby(["dataset", "method"])[metrics].mean().round(3)
    print(summ.to_markdown())
    for strat in ("eps", "phased", "depth", "rc"):
        s = df.groupby([strat, "method"])[["spearman_cis", "spearman_whole", "phase_acc"]].mean().round(3)
        print(f"\nby {strat}\n" + s.to_markdown())
    pr = pd.concat([paired(df, m, args.ref) for m in metrics if m in df])
    print("\n" + pr.round(4).to_markdown(index=False))
    summ.to_csv(out / "sim_summary.csv")
    pr.to_csv(out / "sim_paired.csv", index=False)


def cmd_real(args) -> None:
    rows = []
    for cdir in sorted(Path(args.root).glob("cell*")):
        s = cdir / "scores"
        f = s / "full.json"
        if f.exists():
            d = json.loads(f.read_text())
            for meth, r in d["methods"].items():
                row = {"cell": cdir.name, "kind": "full", "method": meth,
                       "precision_units": r["precision"].get("rmsd_to_mean_per_unit")}
                for rn, v in r["vs"].items():
                    row[f"{rn}_r_cis"] = v["dist_r_median"]
                    row[f"{rn}_r_whole"] = v["whole_r"]
                rows.append(row)
            for k, v in d["refs_vs_refs"].items():
                if "~" in k:
                    rows.append({"cell": cdir.name, "kind": "full", "method": f"published:{k}", "dipc_r_cis": v["dist_r_median"]})
                else:
                    rows.append({"cell": cdir.name, "kind": "full", "method": f"published:{k}",
                                 "precision_units": v.get("rmsd_to_mean_per_unit")})
        f = s / "mask.json"
        if f.exists():
            d = json.loads(f.read_text())
            for meth, r in d["methods"].items():
                ph = r.get("phase_holdback", {})
                rows.append({"cell": cdir.name, "kind": "mask", "method": meth, **{f"phase_{k}": v for k, v in ph.items()}})
        for ev in ("eval_pairs", "eval_pairs_cis"):
            for f in sorted(s.glob(f"heldout_fold*_{ev}.json")):
                d = json.loads(f.read_text())
                for meth, r in d["methods"].items():
                    rows.append({"cell": cdir.name, "kind": f"heldout:{ev}", "fold": f.stem.split("_")[1], "method": meth,
                                 "auc_cis": r["median"]["cis"]["roc_auc"], "auc_trans": r["median"]["trans"]["roc_auc"],
                                 "auc_all": r["median"]["all"]["roc_auc"], "n_pos": r["median"]["all"]["n_pos"]})
    df = pd.DataFrame(rows)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "real_rows.csv", index=False)
    for kind, g in df.groupby("kind"):
        g = g.dropna(axis=1, how="all")
        num = [c for c in g.columns if c not in ("cell", "kind", "method", "fold") and pd.api.types.is_numeric_dtype(g[c])]
        print(f"\n## {kind}\n" + g.groupby("method")[num].mean().round(3).to_markdown())


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sim")
    s.add_argument("--scores", required=True)
    s.add_argument("--ref", default="nucdyn")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_sim)
    r = sub.add_parser("real")
    r.add_argument("--root", required=True)
    r.add_argument("--out", required=True)
    r.set_defaults(fn=cmd_real)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
