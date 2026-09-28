"""Compare two ensembles of the same cell model by model (e.g. original vs native engine).

Both inputs are ``cell<n>.npz`` model files (``chrom``, ``pos`` in the 2017
convention, ``coords``).  Particles are matched by chromosome and position.
Reports the ensemble precision of each (RMSD to the superposed mean,
mirror-aware, as ``a_nucdyn_engine_score.py``), the cross-ensemble RMSD
(best of mirror) and distance-matrix r (median over chromosomes) for every
pair of models, next to the within-ensemble values, so a faithful engine
shows cross values within the spread of the within values.

Usage::

    python benchmarks/fig3/a_nucdyn_engine_compare.py A.npz B.npz --labels original native --out x.json
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from a_nucdyn_engine_score import dist_r_matrix, kabsch, match, precision  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--labels", nargs=2, default=["a", "b"])
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    za, zb = np.load(args.a, allow_pickle=True), np.load(args.b, allow_pickle=True)
    ia, ib = match(za["chrom"].astype(str), za["pos"], zb["chrom"].astype(str), zb["pos"])
    A, B = za["coords"][:, ia].astype(float), zb["coords"][:, ib].astype(float)
    chrom = za["chrom"].astype(str)[ia]
    la, lb = args.labels
    res = {"n_matched_particles": int(len(ia)), "n_particles": [int(za["coords"].shape[1]), int(zb["coords"].shape[1])],
           la: precision(A), lb: precision(B)}
    rr = dist_r_matrix([A, B], chrom)
    na = len(A)
    within_a = [v for (x, y), v in rr.items() if y < na]
    within_b = [v for (x, y), v in rr.items() if x >= na]
    cross = [v for (x, y), v in rr.items() if x < na <= y]
    rm_a = [kabsch(A[x], A[y], True) for x, y in itertools.combinations(range(len(A)), 2)]
    rm_b = [kabsch(B[x], B[y], True) for x, y in itertools.combinations(range(len(B)), 2)]
    rm_x = [kabsch(A[x], B[y], True) for x in range(len(A)) for y in range(len(B))]
    res.update({
        f"dist_r_within_{la}": float(np.median(within_a)), f"dist_r_within_{lb}": float(np.median(within_b)),
        f"dist_r_{la}_vs_{lb}": float(np.median(cross)),
        f"rmsd_within_{la}": float(np.mean(rm_a)), f"rmsd_within_{lb}": float(np.mean(rm_b)),
        f"rmsd_{la}_vs_{lb}": float(np.mean(rm_x)),
        f"rmsd_{la}_vs_{lb}_min": float(np.min(rm_x)),
    })
    print(json.dumps(res, indent=1))
    if args.out:
        args.out.write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
