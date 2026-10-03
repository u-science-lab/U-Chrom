"""Fig. 3 tables of the frozen `robust` method -> paper/fig3/results/robust/.

* ``heldout.csv``  : same columns as ``paper/fig3/results/screcon/heldout.csv``, method ``robust``, plus
  ``set`` (dev: cells 1-4, the development runs of the frozen parameter set "c2"; test: cells 5-8, the
  frozen-build test runs);
* ``sim.csv``      : same columns as ``screcon/sim.csv`` (method ``robust``, + ``set``: truth 1-2 dev,
  truth 3-5 test);
* ``speed_one_model.json`` : one-model speed records (``speed_one_model.py`` record format, methods
  ``robust_cpu`` / ``robust_gpu``) and their per-(method, threads, resolution) medians;
* ``score_all.json`` is copied as is from ``robust_fig3_score.sbatch`` (ED Table 2 metrics, cells 1-8).

    python benchmarks/screcon/robust_fig3_tables.py --heldout-dev D --heldout-test T --sim-dev D --sim-test T \\
        --speed-records R [R ...] --score-json S --out paper/fig3/results/robust
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aggregate import heldout_rows, sim_rows  # noqa: E402


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--heldout-dev", type=Path, required=True)
    ap.add_argument("--heldout-test", type=Path, required=True)
    ap.add_argument("--sim-dev", type=Path, required=True)
    ap.add_argument("--sim-test", type=Path, required=True)
    ap.add_argument("--speed-records", type=Path, nargs="*", default=[])
    ap.add_argument("--score-json", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    rows = []
    for d, s, cells in ((a.heldout_dev, "dev", {1, 2, 3, 4}), (a.heldout_test, "test", {5, 6, 7, 8})):
        for r in heldout_rows(d):
            if r["method"] == "robust" and r["cell"] in cells:
                rows.append({**r, "set": s})
    h = pd.DataFrame(rows).sort_values(["cell", "fold", "score", "subset", "band"], na_position="first")
    h.to_csv(a.out / "heldout.csv", index=False)
    rows = []
    for d, s, truths in ((a.sim_dev, "dev", {"truth_1", "truth_2"}), (a.sim_test, "test", {"truth_3", "truth_4", "truth_5"})):
        for r in sim_rows(d):
            if r["kind"] == "method" and r["method"] == "robust" and r["truth"] in truths:
                rows.append({**r, "set": s})
    sdf = pd.DataFrame(rows).sort_values(["dataset", "truth", "depth_per_mb", "rc_rel", "eps"])
    sdf.to_csv(a.out / "sim.csv", index=False)
    recs = []
    for d in a.speed_records:
        for f in sorted(d.glob("*.json")):
            r = json.loads(f.read_text())
            if r.get("status") == "ok":
                recs.append(r)
    groups: dict = {}
    for r in recs:
        groups.setdefault((r["method"], int(r["threads"]), int(r["res"])), []).append(float(r["wall_seconds"]))
    table = [{"method": m, "threads": t, "res": res, "n_runs": len(v), "median_seconds": statistics.median(v)}
             for (m, t, res), v in sorted(groups.items())]
    (a.out / "speed_one_model.json").write_text(json.dumps({"records": recs, "table": table}, indent=1, default=str))
    if a.score_json:
        shutil.copy(a.score_json, a.out / "score_all.json")
    print(f"heldout {len(h)} rows, sim {len(sdf)} rows, speed {len(recs)} records -> {a.out}")


if __name__ == "__main__":
    main()
