"""Tidy tables from the score JSONs of ``score.py``.

Writes to ``--out``:

* ``long.csv`` - one row per (score file, method, metric path, value): every scalar in the JSON;
* ``headline.csv`` - one row per (score file, method) with the headline metrics
  (``bulk_metrics.HEADLINE``);
* ``gain.csv`` - per score file, deconvolution method and headline metric: the value, the best
  pairwise-only baseline (``hipps`` / ``contact_gaussian``), the oracle (``dimes_oracle``), the
  floor (``random_polymer``), the ceiling (``truth_half_A``) and
  ``gain_over_pairwise = (M_pw - M) / (M_pw - M_ceiling)`` (losses; for the C2ST AUC the loss
  is |AUC - 0.5|); ``gain_over_oracle`` likewise with the oracle;
* ``twin.csv`` - identifiable fractions of ``score.py twin`` outputs (``--twin``).

Usage::

    python benchmarks/bulk/aggregate.py --scores RUNS/bulk/scores --twin RUNS/bulk/twin --out RUNS/bulk/tables
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bulk_metrics import HEADLINE, get_path  # noqa: E402

PAIRWISE = ("hipps", "contact_gaussian")
REFERENCE = ("hipps", "contact_gaussian", "dimes_oracle", "consensus", "random_polymer", "truth_half_A")


def flatten(d, prefix=""):
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            yield from flatten(v, key)
        elif isinstance(v, (int, float)) and not isinstance(v, bool) and v is not None:
            yield key, float(v)


def loss(v, kind):
    if v is None:
        return np.nan
    return abs(v - 0.5) if kind == "auc" else float(v)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scores", nargs="+", required=True, help="score JSON files or directories")
    ap.add_argument("--twin", nargs="*", default=[])
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    files = []
    for s in args.scores:
        p = Path(s)
        files += sorted(p.rglob("*.json")) if p.is_dir() else [p]
    long, head, gain = [], [], []
    for f in files:
        d = json.loads(f.read_text())
        if "methods" not in d:
            continue
        ds = d.get("truth_meta", {}).get("dataset")
        for m, res in d["methods"].items():
            base = {"file": f.name, "dataset": ds, "input": Path(d.get("input") or "").name, "method": m}
            for k, v in flatten({k: v for k, v in res.items() if k not in ("meta",)}):
                long.append({**base, "metric": k, "value": v})
            head.append({**base, **{name: get_path(res, path) for path, (name, _) in HEADLINE.items()}})
        for m, res in d["methods"].items():
            if m in REFERENCE:
                continue
            for path, (name, kind) in HEADLINE.items():
                v = loss(get_path(res, path), kind)
                ref = {r: loss(get_path(d["methods"][r], path), kind) for r in REFERENCE if r in d["methods"]}
                pw = np.nanmin([ref.get(r, np.nan) for r in PAIRWISE]) if any(r in ref for r in PAIRWISE) else np.nan
                ceil = ref.get("truth_half_A", np.nan)
                orc = ref.get("dimes_oracle", np.nan)
                row = {"file": f.name, "dataset": ds, "method": m, "metric": name, "loss": v, "pairwise_best": pw,
                       "oracle": orc, "floor": ref.get("random_polymer", np.nan), "ceiling": ceil,
                       "consensus": ref.get("consensus", np.nan)}
                with np.errstate(invalid="ignore", divide="ignore"):
                    row["gain_over_pairwise"] = (pw - v) / (pw - ceil) if np.isfinite(pw - ceil) and pw != ceil else np.nan
                    row["gain_over_oracle"] = (orc - v) / (orc - ceil) if np.isfinite(orc - ceil) and orc != ceil else np.nan
                gain.append(row)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(long).to_csv(out / "long.csv", index=False)
    pd.DataFrame(head).to_csv(out / "headline.csv", index=False)
    pd.DataFrame(gain).to_csv(out / "gain.csv", index=False)
    tw = []
    for t in args.twin:
        p = Path(t)
        for f in (sorted(p.rglob("*.json")) if p.is_dir() else [p]):
            d = json.loads(f.read_text())
            for k, v in d.get("identifiable", {}).items():
                tw.append({"file": f.name, "metric": k, **v})
    if tw:
        pd.DataFrame(tw).to_csv(out / "twin.csv", index=False)
    print(f"{len(files)} score files -> {out} ({len(long)} long rows, {len(head)} methods, {len(gain)} gain rows)")


if __name__ == "__main__":
    main()
