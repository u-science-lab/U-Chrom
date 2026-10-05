"""Aggregate few-cell deconvolution scores (``mix_score.py`` JSON, one per pool) into tables.

    python benchmarks/screcon/mix_aggregate.py --scores RUNS/*/*.score.json --out TABLE.tsv [--vs igm naive]

Rows: one per (pool, method) with M2, M2_cis, M1 (all / strata), the closest-structure M1 and wall
time; the summary prints means per (dataset, k, method) and, for every method against each
``--vs`` comparator, the paired difference of M2 and M1 with a 95 % percentile bootstrap over
pools (simulated pools grouped by pool across their conditions).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd


def load(paths) -> pd.DataFrame:
    rows = []
    for p in paths:
        r = json.loads(Path(p).read_text())
        meta = r.get("meta") or {}
        name = Path(r["pool"]).name.replace(".txt.gz", "")
        parts = Path(r["pool"]).parts
        dataset = meta.get("dataset") or next((x for x in ("takei2021_1mb", "su2020_genome", "nagano", "stevens") if x in parts), "?")
        m = re.match(r"k(\d+)_p(\d+)", name)
        unit = f"{dataset}:{m.group(0)}" if m else name
        for lab, v in r["methods"].items():
            if "missing" in v:
                continue
            m1 = v.get("M1") or {}
            mc = v.get("M1_closest") or {}
            rows.append({"dataset": dataset, "pool": name, "unit": unit, "k": r["k"], "kind": r["kind"],
                         "depth": meta.get("depth"), "eps": meta.get("eps"), "method": lab,
                         "M2": v.get("M2"), "M2_cis": v.get("M2_cis"), "M1": m1.get("all"),
                         "M1_trans": m1.get("trans"), "M1_gt20": m1.get("cis_gt20mb"), "M1_2_20": m1.get("cis_2_20mb"),
                         "M1_lt2": m1.get("cis_lt2mb"), "M1_signal": m1.get("signal"), "M1_closest": mc.get("all"),
                         "wall": v.get("wall_seconds")})
    return pd.DataFrame(rows)


def paired(d: pd.DataFrame, a: str, b: str, col: str, n_boot: int = 2000, seed: int = 0):
    x = d[d.method == a].set_index("pool")[[col, "unit"]]
    y = d[d.method == b].set_index("pool")[[col]]
    j = x.join(y, rsuffix="_b", how="inner").dropna()
    if j.empty:
        return None
    j["diff"] = j[col] - j[col + "_b"]
    per_unit = j.groupby("unit")["diff"].mean()
    rng = np.random.default_rng(seed)
    v = per_unit.to_numpy()
    boots = [rng.choice(v, len(v)).mean() for _ in range(n_boot)]
    return float(v.mean()), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5)), len(v)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scores", nargs="+", required=True)
    ap.add_argument("--vs", nargs="*", default=["naive", "igm"])
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    d = load(args.scores)
    if args.out:
        d.to_csv(args.out, sep="\t", index=False)
    pd.set_option("display.width", 200)
    print(d.groupby(["dataset", "k", "method"])[["M2", "M1", "M1_trans", "M1_closest"]].mean().round(3).to_string())
    for ds, g in d.groupby("dataset"):
        for m in sorted(set(g.method)):
            for b in args.vs:
                if m == b or b not in set(g.method):
                    continue
                for col in ("M2", "M1"):
                    r = paired(g, m, b, col)
                    if r:
                        print(f"{ds:14s} {m:14s} - {b:6s} {col}: {r[0]:+.3f} [{r[1]:+.3f}, {r[2]:+.3f}] (n = {r[3]})")


if __name__ == "__main__":
    main()
