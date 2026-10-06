"""Score reconstructed populations against a truth population (``bulk_metrics.score_population``).

Subcommands
-----------
``score``  every ``--pop LABEL=PATH`` vs the truth (``--truth``), on the truth's loci::

               python benchmarks/bulk/score.py score --truth SIM/su/truth.npz --input SIM/su/bulk_step_inf.npz \\
                   --pop igm=RUNS/su/igm_s1000_seed1.chromdata.zarr --pop-dir SIM/su/baselines \\
                   --out SCORES/su_step_inf.json

           ``PATH``: a Population ``.npz``, the engine's raw ``.npz`` (coords, bead_bin, bead_copy,
           chrom / start / end) or a ChromData store written by
           ``uchrom.recon.bulk.deconv.deconvolve(method="igm")`` (cells = structures; needs U-Chrom).
           ``--pop-dir`` adds every ``*.npz`` / ``*.chromdata.zarr`` / ``*.cdz`` of a directory
           (baselines, deconvolution outputs); ``truth_half_A`` is
           scored against ``truth_half_B`` (the ceiling), everything else against the full truth.
           ``--rc-nm`` / the input's provenance / ``--rc-from`` give the contact distance of the fit
           (in truth nm);
           model coordinates are rescaled by one global factor inside the metrics.

``twin``   identifiability: ``--t1 --t2`` truths (truth and twin) and ``--r1 --r2`` their
           reconstructions; higher-order distances between the two truths and between the two
           reconstructions (``twins.py``).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import jdump, load_preprocess  # noqa: E402
from bulk_baselines import input_on_loci  # noqa: E402
from bulk_metrics import (FeatureSpace, c2st, cluster_metrics, contact_metrics, all_pairs, sample_triplets,  # noqa: E402
                     score_population, stratified_pairs, structure_features, triplet_metrics)
from population import Population, load_any  # noqa: E402


def _loci(T: Population):
    import pandas as pd
    return pd.DataFrame({"chrom": T.chrom, "start": T.start, "end": T.end})


def cmd_score(args) -> None:
    T = Population.load(args.truth)
    pm = load_preprocess().ProbabilityMatrix.load(args.input) if args.input else None
    prob = None
    rc = args.rc_nm
    if pm is not None:
        prob, _ = input_on_loci(pm, T)
        rc = rc or pm.provenance.get("rc_nm_median") or pm.provenance.get("simulation", {}).get("rc_nm_median")
    if rc is None and args.rc_from:
        rc = load_preprocess().ProbabilityMatrix.load(args.rc_from).provenance.get("rc_nm_median")
    if rc is None:
        raise SystemExit("contact distance unknown: pass --rc-nm or an --input with provenance")
    pops = dict(p.split("=", 1) for p in (args.pop or []))
    for d in args.pop_dir or []:
        for pat in ("*.npz", "*.chromdata.zarr", "*.cdz"):
            for f in sorted(Path(d).glob(pat)):
                name = f.name.split(".")[0]
                if name != "truth_half_B":
                    pops.setdefault(name, str(f))
    out = {"truth": str(args.truth), "input": args.input, "rc_nm": rc, "truth_meta": {k: v for k, v in T.meta.items()
                                                                                      if k != "cell_ids"},
           "methods": {}}
    kw = dict(prob=prob, sigma=args.sigma, max_pairs=args.max_pairs, ks_pairs=args.ks_pairs, n_triplets=args.n_triplets,
              max_query=args.max_query, k_candidates=args.k_candidates, seed=args.seed, skip=tuple(args.skip or ()))
    for label, path in pops.items():
        t0 = time.time()
        R = load_any(path, _loci(T))
        ref = T
        if label == "truth_half_A":
            ref = Population.load(Path(path).with_name("truth_half_B.npz"))
        res = score_population(R, ref, rc=rc, **kw)
        res.update({"path": str(path), "seconds": time.time() - t0,
                    "meta": {k: v for k, v in R.meta.items() if k not in ("cell_ids",)}})
        out["methods"][label] = res
        print(label, f"{time.time() - t0:.0f}s", flush=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(jdump(out))


def cmd_twin(args) -> None:
    """Higher-order distances between T1 / T2 and between R1 / R2 (same loci)."""
    T1, T2 = Population.load(args.t1), Population.load(args.t2)
    loci = _loci(T1)
    R1, R2 = load_any(args.r1, loci), load_any(args.r2, loci)
    rc = args.rc_nm
    res = {"t1": args.t1, "t2": args.t2, "r1": args.r1, "r2": args.r2, "rc_nm": rc}
    trip = sample_triplets(T1, args.n_triplets, args.seed)
    fi, fj = stratified_pairs(T1, 2000, args.seed)
    i, j = all_pairs(T1, args.max_pairs or 50000, args.seed)

    def dist(A, B):
        from bulk_metrics import global_scale
        s = global_scale(A, B, i, j)
        A = A.scaled(s)
        FA, FB = structure_features(A, fi, fj), structure_features(B, fi, fj)
        fs = FeatureSpace(FB)
        return {"scale": s, "pairwise": contact_metrics(A, B, i, j, rc, radii_rel=(1.0, 2.0)),
                "triplet": triplet_metrics(A, B, trip, rc), "cluster": cluster_metrics(fs(FA), fs(FB), seed=args.seed),
                "c2st": c2st(fs.standardise(FA), fs.standardise(FB), seed=args.seed)}
    res["truths"] = dist(T2, T1)
    res["reconstructions"] = dist(R2, R1)
    frac = {}
    for key, path in (("p3_mae", ("triplet", "p3_mae")), ("coop_mae", ("triplet", "coop_mae")),
                      ("cluster_tv", ("cluster", "tv")), ("c2st_auc_minus_half", ("c2st", "auc"))):
        a = res["truths"].get(path[0], {}).get(path[1])
        b = res["reconstructions"].get(path[0], {}).get(path[1])
        if a is None or b is None:
            continue
        if key.startswith("c2st"):
            a, b = abs(a - 0.5), abs(b - 0.5)
        frac[key] = {"truths": a, "reconstructions": b, "identifiable_fraction": b / a if a else None}
    res["identifiable"] = frac
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(jdump(res))
    print(jdump(frac), flush=True)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score")
    s.add_argument("--truth", required=True)
    s.add_argument("--input", help="probability matrix .npz the reconstructions were fitted to")
    s.add_argument("--pop", action="append", help="LABEL=PATH")
    s.add_argument("--pop-dir", action="append")
    s.add_argument("--rc-nm", type=float)
    s.add_argument("--rc-from", help="probability-matrix .npz whose provenance gives rc (real inputs: the simulated input on the same bins)")
    s.add_argument("--sigma", type=float, default=0.01)
    s.add_argument("--max-pairs", type=int)
    s.add_argument("--ks-pairs", type=int, default=20000)
    s.add_argument("--n-triplets", type=int, default=20000)
    s.add_argument("--max-query", type=int, default=500)
    s.add_argument("--k-candidates", type=int, default=20)
    s.add_argument("--skip", nargs="*")
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_score)
    t = sub.add_parser("twin")
    for k in ("--t1", "--t2", "--r1", "--r2"):
        t.add_argument(k, required=True)
    t.add_argument("--rc-nm", type=float, required=True)
    t.add_argument("--n-triplets", type=int, default=20000)
    t.add_argument("--max-pairs", type=int)
    t.add_argument("--seed", type=int, default=0)
    t.add_argument("--out", required=True)
    t.set_defaults(fn=cmd_twin)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
