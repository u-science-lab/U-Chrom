"""Tidy tables of the consensus benchmark.

    python benchmarks/bulk/consensus/aggregate.py --scores RUNS/consensus/scores \
        --runs RUNS/consensus/models RUNS/consensus/scaling --out RUNS/consensus/tables

* ``long.csv``      one row per (score file, model, subset, metric): dataset, input tag, value;
* ``headline.csv``  per (dataset, input, model): Spearman all / cis / trans / per-chromosome cis,
                    log-log Pearson all, RMSD / Rg (genome, per chromosome), fit to input (cis, trans);
* ``runs.csv``      per run.py summary: cell, resolution, beads, chromosomes, device, threads, runs,
                    seconds (prepare / engine / wall), peak RSS, alpha / nu / gamma, run-to-run precision,
                    restraints and violated fraction of the last stage.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

import _bc  # noqa: F401
from _bc import read_json


def long_rows(path: Path):
    s = read_json(path)
    tag = path.stem
    for model, r in s["models"].items():
        base = {"file": tag, "dataset": s.get("dataset"), "model": model}
        for subset, v in r["distance"].items():
            if isinstance(v, dict) and "spearman" in v:
                for k in ("n", "spearman", "pearson", "pearson_log"):
                    yield {**base, "subset": subset, "metric": k, "value": v[k]}
            elif not isinstance(v, dict):
                yield {**base, "subset": subset, "metric": "value", "value": v}
        for k, v in r.get("rmsd", {}).items():
            yield {**base, "subset": "rmsd", "metric": k, "value": v}
        for sub, v in r.get("fit_input", {}).items():
            for k, x in v.items():
                yield {**base, "subset": f"fit_{sub}", "metric": k, "value": x}


def headline(long: pd.DataFrame) -> pd.DataFrame:
    def g(df, subset, metric):
        v = df[(df.subset == subset) & (df.metric == metric)]["value"]
        return float(v.iloc[0]) if len(v) else np.nan

    rows = []
    for (f, ds, m), df in long.groupby(["file", "dataset", "model"], sort=False):
        rows.append({"file": f, "dataset": ds, "model": m,
                     "spearman_all": g(df, "all", "spearman"), "spearman_cis": g(df, "cis", "spearman"),
                     "spearman_trans": g(df, "trans", "spearman"),
                     "spearman_cis_per_chrom_median": g(df, "cis_per_chrom_spearman_median", "value"),
                     "pearson_log_all": g(df, "all", "pearson_log"), "n_pairs": g(df, "all", "n"),
                     "rmsd_over_rg": g(df, "rmsd", "rmsd_over_rg"),
                     "rmsd_over_rg_per_chrom": g(df, "rmsd", "rmsd_over_rg_per_chrom_median"),
                     "fit_cis": g(df, "fit_cis", "neg_spearman"), "fit_trans": g(df, "fit_trans", "neg_spearman")})
    return pd.DataFrame(rows)


def runs_table(dirs) -> pd.DataFrame:
    rows = []
    for d in dirs:
        for p in sorted(Path(d).glob("**/*.json")):
            s = read_json(p)
            if "seconds_engine" not in s:
                continue
            last = s["stages"][-1]
            rows.append({"file": p.stem, "cell": s.get("cell"), "resolution": s["resolution"], "n_beads": s["n_beads"],
                         "n_chroms": s["n_chroms"], "device": s["device"], "gpu": s.get("gpu"), "threads": s["threads"],
                         "n_runs": s["n_runs"], "seed": s["seed"], "overrides": str(s.get("overrides") or ""),
                         "seconds_prepare": s["seconds_prepare"], "seconds_engine": s["seconds_engine"],
                         "seconds_wall": s["seconds_wall"], "peak_rss_gb": s["peak_rss_gb"],
                         "gpu_mem_gb": s.get("gpu_mem_gb"), "alpha": s["alpha"], "nu": s["nu"],
                         "gamma": s["decay_fit"].get("gamma"), "n_restraints_final": last["n_restraints"],
                         "violated_final": last["violated_fraction_mean"],
                         **{f"precision_{k}": v for k, v in s["precision"].items()}})
    return pd.DataFrame(rows)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scores", required=True)
    ap.add_argument("--runs", nargs="*", default=[])
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    long = pd.DataFrame([r for p in sorted(Path(a.scores).glob("*.json")) for r in long_rows(p)])
    long.to_csv(out / "long.csv", index=False)
    h = headline(long) if len(long) else pd.DataFrame()
    h.to_csv(out / "headline.csv", index=False)
    rt = runs_table(a.runs)
    rt.to_csv(out / "runs.csv", index=False)
    with pd.option_context("display.width", 200, "display.max_columns", 30):
        print(h.round(3).to_string(index=False) if len(h) else "(no scores)")
        print(rt.round(3).to_string(index=False) if len(rt) else "(no runs)")


if __name__ == "__main__":
    main()
