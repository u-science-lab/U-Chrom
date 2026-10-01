"""Twin truths: a second truth population with (nearly) the same pairwise contact map as the
real one but different higher-order statistics (design.md section 7(b), identifiability).

Two constructions, both documented with how well they match:

* ``gaussian`` - the maximum-entropy Gaussian ensemble whose per-pair contact probabilities at
  the fit's contact distance rc equal the truth's (``bulk_baselines.contact_gaussian`` applied to the
  truth's exact IGM-pooled contact matrix, refined so that the realised probabilities match).
  Pairwise contact frequencies at rc are matched (up to the positive-semi-definite projection,
  reported as ``pair_match``); every higher-order statistic is Gaussian (no clusters, no
  cooperative multi-way contacts beyond what the pairwise covariance implies).
* ``chrom_shuffle`` - new cells assembled from chromosomes of *different* truth cells: every
  truth cell is centred on its own centroid; for each new cell and each chromosome a donor cell
  is drawn uniformly (with replacement) and both of its copies of that chromosome are copied
  unchanged.  Every **intra-chromosomal** statistic of any order (pairwise, three-body, cis
  clusters) is exactly preserved in distribution, and so is each chromosome's radial position;
  what is destroyed is the coupling between chromosomes within a cell (which chromosomes are
  near each other, cell-level states).  Trans pairwise contact frequencies change (placement
  of independent chromosomes); their deviation is reported (``pair_match``), so this twin tests
  whether a reconstruction's *trans* higher-order structure is data-driven.

Test protocol (``score.py twin``): run the same pipeline (forward model -> deconvolution) on
T1 = truth and T2 = twin; for each higher-order metric M (three-body, cluster proportions,
C2ST between the two populations) compute ``d_T = M(T1, T2)`` and ``d_R = M(R1, R2)``;
``identifiable_fraction = d_R / d_T`` (1: the reconstructions differ as much as the truths do;
0: the statistic is prior-driven).  Pairwise statistics are reported alongside to show that the
two inputs are indeed (nearly) equal.

CLI::

    python benchmarks/bulk/twins.py --truth T.npz --kind gaussian --input bulk_exact.npz --out twin_gauss.npz
    python benchmarks/bulk/twins.py --truth T.npz --kind chrom_shuffle --out twin_shuffle.npz
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import jdump, load_preprocess  # noqa: E402
from bulk_baselines import contact_gaussian, input_on_loci  # noqa: E402
from bulk_metrics import all_pairs, contact_frequency  # noqa: E402
from population import Population  # noqa: E402


def chrom_shuffle(T: Population, n: int | None = None, seed: int = 0) -> Population:
    rng = np.random.default_rng(seed)
    S = T.n_structures
    n = n or S
    X = T.coords.astype(np.float64)
    cen = np.nanmean(X.reshape(S, -1, 3), axis=1)
    Xc = (X - cen[:, None, None]).astype(np.float32)
    out = np.full((n, T.n_copies, T.n_loci, 3), np.nan, np.float32)
    lam = None if T.lamina is None else np.full((n, T.n_copies, T.n_loci), np.nan, np.float32)
    donors = {}
    for c in np.unique(T.chrom):
        m = T.chrom == c
        d = rng.integers(0, S, n)
        donors[c] = d
        out[:, :, m] = Xc[d][:, :, m]
        if lam is not None:
            lam[:, :, m] = T.lamina[d][:, :, m]
    return Population(T.chrom, T.start, T.end, out, lam,
                      meta=dict({k: v for k, v in T.meta.items() if k != "cell_ids"}, twin="chrom_shuffle", seed=seed))


def gaussian_twin(T: Population, f: np.ndarray, rc, n: int | None = None, seed: int = 0) -> Population:
    pop = contact_gaussian(np.where(np.isfinite(f), f, 0.0), rc, T.chrom, T.start, T.end, n or T.n_structures,
                           T.n_copies, seed=seed)
    pop.meta.update(twin="gaussian", seed=seed)
    return pop


def pair_match(T: Population, W: Population, rc, max_pairs: int = 50000, seed: int = 0) -> dict:
    """How equal the pairwise contact maps of the truth and its twin are (at rc and 2 rc)."""
    i, j = all_pairs(T, max_pairs, seed)
    cis = T.chrom[i] == T.chrom[j]
    rc = np.asarray(rc, float)
    r = rc if rc.ndim == 0 else rc[i, j]
    out = {}
    for rr in (1.0, 2.0):
        a, b = contact_frequency(T, i, j, r * rr), contact_frequency(W, i, j, r * rr)
        res = {"mae": float(np.mean(np.abs(a - b))), "mean_T": float(a.mean())}
        for name, s in (("cis", cis), ("trans", ~cis)):
            if s.any():
                res[f"mae_{name}"] = float(np.mean(np.abs(a[s] - b[s])))
                res[f"pearson_{name}"] = float(np.corrcoef(a[s], b[s])[0, 1]) if a[s].std() > 0 and b[s].std() > 0 else None
        out[f"r{rr:g}rc"] = res
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--truth", required=True)
    ap.add_argument("--kind", required=True, choices=["gaussian", "chrom_shuffle"])
    ap.add_argument("--input", help="exact probability matrix of the truth (forward.py --depth inf); gaussian only")
    ap.add_argument("--rc-nm", type=float)
    ap.add_argument("--n", type=int)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    T = Population.load(args.truth)
    rc = args.rc_nm
    if args.kind == "gaussian":
        pm = load_preprocess().ProbabilityMatrix.load(args.input)
        f, _ = input_on_loci(pm, T)
        rc = rc or pm.provenance["rc_nm_median"]
        W = gaussian_twin(T, f, rc, args.n, args.seed)
    else:
        W = chrom_shuffle(T, args.n, args.seed)
    if rc:
        W.meta["pair_match"] = pair_match(T, W, rc)
    W.save(args.out)
    print(jdump(W.meta.get("pair_match", {})), flush=True)


if __name__ == "__main__":
    main()
