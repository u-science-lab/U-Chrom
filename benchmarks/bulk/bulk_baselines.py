"""Baseline populations of the bulk deconvolution benchmark, all on the truth's loci.

Pairwise-only (same input as the deconvolution, the haploid probability matrix ``f``):

* ``hipps`` - HIPPS (Shi & Thirumalai 2019 Nat Commun 10:3894; 2021 PRX 11:011051):
  ``<r_ij> = Lambda p_ij^(-1/alpha)`` (alpha = 4, p = f / max off-diagonal f, zeros replaced by
  half the smallest positive value), ``<r_ij^2> = (3 pi / 8) <r_ij>^2``, then the
  maximum-entropy (Gaussian) ensemble with these mean squared distances.  The Gaussian is
  obtained by direct inversion (Gram matrix of the squared-distance matrix, projected onto the
  positive semi-definite cone) - the solution HIPPS-DIMES' iterative scaling converges to when
  the map is realisable (``--hipps-dimes`` in ``benchmarks/fig3`` is the external code; not
  needed here).  Lambda = 1 (the global scale is fitted in the metrics).
* ``contact_gaussian`` - the maximum-entropy Gaussian whose per-pair contact probabilities
  equal ``f`` at the contact distance rc: for a Gaussian, |r_ij| is Maxwell distributed and
  P(|r| < rc) = erf(x / sqrt 2) - sqrt(2 / pi) x exp(-x^2 / 2), x = rc / sigma_ij; sigma_ij is
  obtained by inverting this per pair (f clipped to [f_min / 2, 0.999]), <r^2> = 3 sigma^2, and
  the Gaussian is fitted to it with ``n_refine`` rounds of multiplicative correction so that the
  *realised* (post-projection) contact probabilities match f.
* ``dimes_oracle`` - DIMES (Shi & Thirumalai 2023 Nat Commun 14:1150) on the **truth's** mean
  squared distances ("oracle": the best any pairwise-only Gaussian can do with the true second
  moments), diploid: same-copy cis, homolog-crossing cis and trans moments all from the truth.

Diploid layout of the input-based Gaussians: 2L coordinates; cis pairs of one copy get the
haploid value, trans pairs (any copies) the haploid trans value, and the pairs of the *two
copies of one chromosome* (unknown from haploid Hi-C) ``v_i + v_j`` with ``v`` fitted to the
trans values by least squares (trans msd(i, j) ~ v_i + v_j: homologs placed like two independent
chromosomes).  Estimated targets are not jointly Euclidean, so the input-based Gaussians are fitted
by relative least squares on the covariance factor (:func:`fit_factor`); the oracle, whose targets
are exact second moments of a point set, by the plain projection.

Other baselines:

* ``consensus`` - one structure replicated S times with small noise (0.05 x the median
  consecutive distance): SMACOF metric MDS (numpy; classical-MDS start) on
  d_ij = (f_ij + f_min / 2)^(-1/4) (the miniMDS / HIPPS power law), both copies placed at the
  consensus.  ``--consensus uchrom`` uses ``uchrom.recon.bulk.mds.run_mds`` when U-Chrom and
  PyTorch are installed.
* ``random_polymer`` - floor: per chromosome copy an ideal random walk (step variance
  proportional to genomic distance, median step = truth unit) started uniformly inside a sphere
  of the truth's nuclear radius, reflected at the sphere.
* ``truth_half`` - ceiling: the truth split into two random halves (A scored against B).

CLI::

    python benchmarks/bulk/baselines.py --truth T.npz --input bulk.npz --n 1000 --out-dir BASE/ [--rc-nm X]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import optimize, special

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import jdump, load_preprocess  # noqa: E402
from population import Population, map_to_loci, median_consecutive  # noqa: E402


# --------------------------------------------------------------------------- Gaussian ensembles

def gram_from_msd(D2: np.ndarray) -> np.ndarray:
    n = len(D2)
    J = np.eye(n) - 1.0 / n
    return -0.5 * J @ D2 @ J


def psd_factor(G: np.ndarray) -> tuple[np.ndarray, dict]:
    w, v = np.linalg.eigh((G + G.T) / 2)
    neg = w < 0
    info = {"neg_eig_fraction": float(neg.mean()), "neg_eig_mass": float(-w[neg].sum() / np.abs(w).sum())}
    return v * np.sqrt(np.clip(w, 0, None)), info


def fit_factor(D2: np.ndarray, rank: int = 300, max_iter: int = 500, W: np.ndarray | None = None) -> tuple[np.ndarray, dict]:
    """Covariance factor F (n, rank) minimising the *relative* squared error of the realised mean
    squared distances, sum_ij w_ij (|F_i - F_j|^2 - D2_ij)^2 with w = 1 / D2^2 (L-BFGS, start =
    PSD projection).  Estimated pairwise targets are not jointly Euclidean (noise in small
    probabilities -> large absolute errors of large distances); the plain projection lets those
    errors wreck the short-range structure, the relative criterion does not."""
    n = len(D2)
    F0, info = psd_factor(gram_from_msd(D2))
    order = np.argsort((F0 ** 2).sum(0))[::-1][: min(rank, n)]
    F0 = F0[:, order]
    k = F0.shape[1]
    off = ~np.eye(n, dtype=bool)
    if W is None:
        W = np.where(off & (D2 > 0), 1.0 / np.maximum(D2, 1e-12) ** 2, 0.0)
    W = W / W.sum()

    def fun(x):
        F = x.reshape(n, k)
        G = F @ F.T
        s = np.diag(G)
        e = s[:, None] + s[None] - 2 * G - D2
        M = 2 * W * e
        dG = np.diag(M.sum(0) + M.sum(1)) - 2 * M
        return float((W * e * e).sum()), (2 * dG @ F).ravel()

    r = optimize.minimize(fun, F0.ravel(), jac=True, method="L-BFGS-B", options={"maxiter": max_iter})
    F = r.x.reshape(n, k)
    real = realised_msd(F)
    rel = np.abs(real / np.where(D2 > 0, D2, 1) - 1)[off & (D2 > 0)]
    info.update({"fit": "relative least squares (L-BFGS)", "rank": int(k), "iterations": int(r.nit),
                 "rel_err_median": float(np.median(rel)), "rel_err_p90": float(np.quantile(rel, 0.9))})
    return F, info


def sample_gaussian(F: np.ndarray, n: int, seed: int = 0) -> np.ndarray:
    """Coordinates (n, dim, 3) with covariance F F^T / 3 per axis, so that
    E|x_i - x_j|^2 = |F_i - F_j|^2 (= the target mean squared distance)."""
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((n, F.shape[1], 3))
    return np.einsum("dk,nkc->ndc", F, z) / np.sqrt(3.0)


def realised_msd(F: np.ndarray) -> np.ndarray:
    sq = (F ** 2).sum(1)
    return np.maximum(sq[:, None] + sq[None] - 2 * F @ F.T, 0.0)


def maxwell_cdf(rc, sigma):
    x = rc / sigma
    return special.erf(x / np.sqrt(2)) - np.sqrt(2 / np.pi) * x * np.exp(-x ** 2 / 2)


def maxwell_sigma(f: np.ndarray, rc) -> np.ndarray:
    """sigma such that maxwell_cdf(rc, sigma) = f (vectorised by interpolation on x = rc / sigma)."""
    xs = np.logspace(-3, 1.5, 4000)
    cdf = maxwell_cdf(xs, 1.0)
    x = np.interp(f, cdf, xs)
    return np.asarray(rc, float) / x


def diploid_msd(hap: np.ndarray, chrom: np.ndarray, homolog: np.ndarray | None = None) -> np.ndarray:
    """(L, L) haploid mean squared distances -> (2L, 2L) diploid (copy 0 loci, then copy 1).
    ``homolog`` (L, L): cross-copy cis values (default: the chromosome's mean trans value)."""
    L = len(chrom)
    same = chrom[:, None] == chrom[None]
    if homolog is None:
        if (~same).any():
            # independent placement: trans msd(i, j) ~ v_i + v_j (v = spread around the centre);
            # least squares over the trans pairs, then homolog pairs get v_i + v_j
            N = (~same).astype(float)
            m = np.where(~same & np.isfinite(hap), hap, 0.0)
            A = np.diag(N.sum(1)) + N
            v = np.linalg.lstsq(A, m.sum(1), rcond=None)[0]
            homolog = np.maximum(v[:, None] + v[None], 0.0)
        else:
            homolog = np.full((L, L), 4.0 * float(np.nanmax(hap)))
    cross = np.where(same, homolog, hap)
    D2 = np.block([[hap, cross], [cross.T, hap]])
    np.fill_diagonal(D2, 0.0)
    return D2


def gaussian_population(D2: np.ndarray, chrom, start, end, n: int, copies: int, seed: int = 0,
                        meta: dict | None = None, fit: str = "relative") -> Population:
    """Gaussian ensemble with mean squared distances ~ D2: ``fit="relative"`` (:func:`fit_factor`)
    or ``"projection"`` (PSD projection of the Gram matrix; exact for a Euclidean D2)."""
    F, info = fit_factor(D2) if fit == "relative" else psd_factor(gram_from_msd(D2))
    X = sample_gaussian(F, n, seed).astype(np.float32)
    L = len(chrom)
    X = X.reshape(n, copies, L, 3)
    return Population(chrom, start, end, X, meta=dict(meta or {}, **info))


def hipps(f: np.ndarray, chrom, start, end, n: int, copies: int = 2, alpha: float = 4.0, seed: int = 0) -> Population:
    p = f.copy()
    np.fill_diagonal(p, np.nan)
    pos = p[np.isfinite(p) & (p > 0)]
    p = np.where(np.isfinite(p) & (p > 0), p, pos.min() / 2) / np.nanmax(pos)
    r = p ** (-1.0 / alpha)
    hap = 3 * np.pi / 8 * r ** 2
    np.fill_diagonal(hap, 0.0)
    D2 = diploid_msd(hap, chrom) if copies == 2 else hap
    return gaussian_population(D2, chrom, start, end, n, copies, seed,
                               {"baseline": "hipps", "alpha": alpha, "pairwise_only": True})


def contact_gaussian(f: np.ndarray, rc, chrom, start, end, n: int, copies: int = 2, n_refine: int = 2,
                     seed: int = 0) -> Population:
    L = len(chrom)
    rc = np.broadcast_to(np.asarray(rc, float), (L, L))
    pos = f[(f > 0) & ~np.eye(L, dtype=bool)]
    tgt = np.clip(np.where(f > 0, f, pos.min() / 2), pos.min() / 2, 0.999)
    hap = 3 * maxwell_sigma(tgt, rc) ** 2
    np.fill_diagonal(hap, 0.0)
    rc2 = np.block([[rc, rc], [rc, rc]]) if copies == 2 else rc
    tgt2 = np.block([[tgt, tgt], [tgt, tgt]]) if copies == 2 else tgt
    D2 = diploid_msd(hap, chrom) if copies == 2 else hap
    target = D2.copy()
    same2 = np.tile(chrom[:, None] == chrom[None], (copies, copies))
    free = (same2 & ~np.kron(np.eye(copies, dtype=bool), np.ones((L, L), bool))) | np.eye(len(D2), dtype=bool)
    hist = []
    for it in range(n_refine + 1):
        F, info = fit_factor(D2)
        real = realised_msd(F)
        got = maxwell_cdf(rc2, np.sqrt(np.maximum(real, 1e-12) / 3))
        hist.append(float(np.abs(got - tgt2)[~free].mean()))
        if it == n_refine:
            break
        upd = np.where(free | (real <= 0), 1.0, target / np.maximum(real, 1e-12))
        D2 = D2 * np.clip(upd, 0.5, 2.0)
        np.fill_diagonal(D2, 0.0)
    X = sample_gaussian(F, n, seed).astype(np.float32).reshape(n, copies, L, 3)
    return Population(chrom, start, end, X, meta={"baseline": "contact_gaussian", "pairwise_only": True,
                                                  "refine_mae": hist, **info})


def dimes_oracle(T: Population, n: int, seed: int = 0) -> Population:
    """Gaussian with the truth's (label-invariant) diploid mean squared distances."""
    S, P, L, _ = T.coords.shape
    X = T.coords.astype(np.float64)
    same = T.chrom[:, None] == T.chrom[None]
    s_same = np.zeros((L, L)); n_same = np.zeros((L, L))
    s_x = np.zeros((L, L)); n_x = np.zeros((L, L))
    for s in range(S):
        for a in range(P):
            for b in range(P):
                d2 = ((X[s, a][:, None] - X[s, b][None]) ** 2).sum(-1)
                ok = np.isfinite(d2)
                d2 = np.where(ok, d2, 0.0)
                if a == b:
                    s_same += d2; n_same += ok
                else:
                    s_x += d2; n_x += ok
    with np.errstate(invalid="ignore", divide="ignore"):
        m_same = s_same / n_same
        m_x = s_x / n_x
        m_all = (s_same + s_x) / (n_same + n_x)
    hap = np.where(same, m_same, m_all)            # cis: same copy; trans: all combinations
    hap = np.where(np.isfinite(hap), hap, np.nanmean(hap))
    np.fill_diagonal(hap, 0.0)
    if P == 1:
        return gaussian_population(hap, T.chrom, T.start, T.end, n, 1, seed, {"baseline": "dimes_oracle", "oracle": True},
                                   fit="projection")
    homo = np.where(np.isfinite(m_x), m_x, np.nanmean(m_x))
    D2 = diploid_msd(hap, T.chrom, homolog=homo)
    return gaussian_population(D2, T.chrom, T.start, T.end, n, 2, seed, {"baseline": "dimes_oracle", "oracle": True},
                               fit="projection")


# --------------------------------------------------------------------------- consensus structure

def smacof(D: np.ndarray, n_iter: int = 300, seed: int = 0, W: np.ndarray | None = None) -> np.ndarray:
    n = len(D)
    J = np.eye(n) - 1.0 / n
    B = -0.5 * J @ (D ** 2) @ J
    w, v = np.linalg.eigh(B)
    X = v[:, -3:] * np.sqrt(np.maximum(w[-3:], 1e-12))
    W = np.ones_like(D) if W is None else W
    np.fill_diagonal(W, 0)
    V = -W.copy()
    np.fill_diagonal(V, W.sum(1))
    Vp = np.linalg.pinv(V)
    for _ in range(n_iter):
        d = np.sqrt(((X[:, None] - X[None]) ** 2).sum(-1))
        with np.errstate(divide="ignore", invalid="ignore"):
            Bm = np.where(d > 0, -W * D / d, 0.0)
        np.fill_diagonal(Bm, 0)
        np.fill_diagonal(Bm, -Bm.sum(1))
        Xn = Vp @ Bm @ X
        if np.abs(Xn - X).max() < 1e-7 * np.abs(X).max():
            X = Xn
            break
        X = Xn
    return X


def consensus(f: np.ndarray, chrom, start, end, n: int, copies: int = 2, noise_rel: float = 0.05, seed: int = 0,
              engine: str = "numpy") -> Population:
    L = len(chrom)
    pos = f[(f > 0) & ~np.eye(L, dtype=bool)]
    D = (np.where(f > 0, f, 0) + pos.min() / 2) ** (-0.25)
    np.fill_diagonal(D, 0.0)
    if engine == "uchrom":
        import torch
        from uchrom.recon.bulk.mds import run_mds
        Y, keep = run_mds(torch.as_tensor(np.where(np.eye(L, dtype=bool), 0, f)), alpha=4.0)
        X0 = np.full((L, 3), np.nan)
        X0[keep] = Y
    else:
        X0 = smacof(D, seed=seed)
    same = chrom[1:] == chrom[:-1]
    unit = float(np.nanmedian(np.linalg.norm(np.diff(X0, axis=0), axis=1)[same]))
    rng = np.random.default_rng(seed)
    X = X0[None, None] + rng.normal(scale=noise_rel * unit, size=(n, copies, L, 3))
    return Population(chrom, start, end, X.astype(np.float32),
                      meta={"baseline": "consensus", "engine": engine, "noise_rel": noise_rel})


# --------------------------------------------------------------------------- floor / ceiling

def random_polymer(T: Population, n: int, seed: int = 0, radius: float | None = None) -> Population:
    rng = np.random.default_rng(seed)
    from forward import nuclear_radius
    R = radius or T.meta.get("nuclear_radius_nm") or nuclear_radius(T)
    unit = median_consecutive(T)
    mid = (T.start + T.end) / 2.0
    same = T.chrom[1:] == T.chrom[:-1]
    gaps = np.diff(mid)[same]
    g0 = np.median(gaps)
    P = T.n_copies
    X = np.full((n, P, T.n_loci, 3), np.nan, np.float32)
    present = np.isfinite(T.coords[..., 0]).any(0)      # (P, L): copies that exist
    for s in range(n):
        for c in np.unique(T.chrom):
            k = np.flatnonzero(T.chrom == c)
            steps_sd = unit / np.sqrt(3) * np.sqrt(np.r_[0, np.diff(mid[k])] / g0)
            for p in range(P):
                if not present[p, k].any():
                    continue
                u = rng.normal(size=3)
                x = u / np.linalg.norm(u) * R * 0.7 * rng.random() ** (1 / 3)
                pts = []
                for a in range(len(k)):
                    x = x + rng.normal(scale=steps_sd[a], size=3)
                    nx = np.linalg.norm(x)
                    if nx > R:
                        x = x * (2 * R / nx - 1)
                    pts.append(x.copy())
                X[s, p, k] = pts
    return Population(T.chrom, T.start, T.end, X, meta={"baseline": "random_polymer", "radius_nm": R})


def truth_halves(T: Population, seed: int = 0) -> tuple[Population, Population]:
    perm = np.random.default_rng(seed).permutation(T.n_structures)
    h = T.n_structures // 2
    A, B = T.subset(np.sort(perm[:h])), T.subset(np.sort(perm[h:]))
    A.meta = dict(T.meta, baseline="truth_half", half="A")
    B.meta = dict(T.meta, baseline="truth_half", half="B")
    return A, B


# --------------------------------------------------------------------------- input on the truth loci

def input_on_loci(pm, T: Population) -> tuple[np.ndarray, np.ndarray]:
    """Dense haploid probability matrix of a ``ProbabilityMatrix`` restricted to the bins that
    contain the truth loci -> (L, L) with NaN rows for loci without a bin; and the bin index."""
    b = pm.bins
    idx = map_to_loci(b.chrom.astype(str).to_numpy(), b.start.to_numpy(), b.end.to_numpy(), T.chrom, T.start, T.end)
    M = pm.probabilities.toarray()
    f = np.full((T.n_loci, T.n_loci), np.nan)
    ok = idx >= 0
    f[np.ix_(ok, ok)] = M[np.ix_(idx[ok], idx[ok])]
    return f, idx


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--truth", required=True)
    ap.add_argument("--input", required=True, help="probability matrix .npz (forward.py / preprocess)")
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--rc-nm", type=float, help="contact distance for contact_gaussian (default: input provenance)")
    ap.add_argument("--rc-from", help="probability-matrix .npz whose provenance gives rc (real inputs)")
    ap.add_argument("--only", nargs="*", default=["hipps", "contact_gaussian", "dimes_oracle", "consensus",
                                                  "random_polymer", "truth_half"])
    ap.add_argument("--consensus-engine", default="numpy", choices=["numpy", "uchrom"])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)
    pp = load_preprocess()
    T = Population.load(args.truth)
    pm = pp.ProbabilityMatrix.load(args.input)
    f, _ = input_on_loci(pm, T)
    f = np.where(np.isfinite(f), f, 0.0)
    rc = args.rc_nm or pm.provenance.get("rc_nm_median") or pm.provenance.get("simulation", {}).get("rc_nm_median")
    if rc is None and args.rc_from:
        rc = pp.ProbabilityMatrix.load(args.rc_from).provenance.get("rc_nm_median")
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    P = T.n_copies
    made = {}
    if "hipps" in args.only:
        made["hipps"] = hipps(f, T.chrom, T.start, T.end, args.n, P, seed=args.seed)
    if "contact_gaussian" in args.only and rc:
        made["contact_gaussian"] = contact_gaussian(f, rc, T.chrom, T.start, T.end, args.n, P, seed=args.seed)
    if "dimes_oracle" in args.only:
        made["dimes_oracle"] = dimes_oracle(T, args.n, args.seed)
    if "consensus" in args.only:
        made["consensus"] = consensus(f, T.chrom, T.start, T.end, args.n, P, seed=args.seed, engine=args.consensus_engine)
    if "random_polymer" in args.only:
        made["random_polymer"] = random_polymer(T, min(args.n, T.n_structures), args.seed)
    if "truth_half" in args.only:
        A, B = truth_halves(T, args.seed)
        made["truth_half_A"], made["truth_half_B"] = A, B
    for name, pop in made.items():
        pop.meta.setdefault("input", str(args.input))
        pop.save(out / f"{name}.npz")
        print(name, pop.coords.shape, jdump({k: v for k, v in pop.meta.items()
                                             if k in ("neg_eig_fraction", "neg_eig_mass", "refine_mae")}).replace("\n", ""),
              flush=True)


if __name__ == "__main__":
    main()
