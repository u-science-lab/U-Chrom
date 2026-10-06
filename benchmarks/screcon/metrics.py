"""Shared, method-neutral metrics for single-cell genome structures (numpy / scipy only).

Length units differ between methods (NucDynamics: particle radii; Si-C: its own MD
unit; hickit: its own unit), so every metric that needs a length scale uses the
model's own **bead unit** = median distance between consecutive particles of the same
chromosome (:func:`bead_unit`).  Metrics:

* :func:`superpose` / :func:`rmsd` - optimal rigid (Kabsch) or similarity (Umeyama,
  with scale) superposition, mirror image optionally allowed;
* :func:`precision` - ensemble precision as in Stevens et al. 2017 ED Table 2: RMSD of
  each model to the iteratively superposed ensemble mean (native units, and / bead
  unit), and mean pairwise RMSD;
* :func:`dist_matrix_r` - Pearson / Spearman r between distance matrices;
* :func:`violations` - two definitions on the contacts binned onto the particles:
  **NucDynamics-style** (restraint of n contacts has d_upper = 1.2 n^-0.33 bead units;
  violated if d > d_upper + 3 / + 4; ED Table 2's %V>3 / %V>4) and **Si-C-style**
  (contact particle pair farther than 2 bead units; Meng et al. 2021).  Both are
  computed after dividing the model by its bead unit, so they are comparable across
  methods; the NucDynamics-style one is also reported in native units (only
  meaningful for NucDynamics models, whose bead unit is ~1);
* :func:`roc_auc` / :func:`average_precision` / :func:`bootstrap_ci` - ranking metrics.
"""

from __future__ import annotations

import itertools
import warnings

import numpy as np
from scipy import stats

# numpy on macOS / Accelerate raises spurious FP warnings from matmul on finite input
warnings.filterwarnings("ignore", message=r".*encountered in matmul")


# --------------------------------------------------------------------------- geometry

def bead_unit(chrom, X) -> float:
    """Median non-zero distance between consecutive particles of the same chromosome
    (X: (N, 3) or (M, N, 3))."""
    chrom = np.asarray(chrom)
    same = chrom[1:] == chrom[:-1]
    X = np.asarray(X, float)
    d = np.linalg.norm(np.diff(X, axis=-2), axis=-1)[..., same]
    d = d[np.isfinite(d) & (d > 0)]      # zero steps = one bead resampled onto several bins (hickit)
    return float(np.median(d)) if d.size else float("nan")


def superpose(ref: np.ndarray, mob: np.ndarray, scale: bool = False, mirror: bool = False):
    """Superpose ``mob`` on ``ref`` (both (N, 3), NaN rows ignored in the fit).

    Returns (transformed mob (N, 3), rmsd, scale factor, mirrored flag).  With ``scale``
    the similarity transform (Umeyama 1991) minimising the RMSD is used; with ``mirror``
    the best of ``mob`` and its mirror image is returned.
    """
    ref = np.asarray(ref, float)
    mob = np.asarray(mob, float)
    ok = np.isfinite(ref).all(1) & np.isfinite(mob).all(1)
    a, b = ref[ok], mob[ok]
    ca, cb = a.mean(0), b.mean(0)
    a0, b0 = a - ca, b - cb
    best = None
    for s_m in ((1.0, -1.0) if mirror else (1.0,)):
        bb = b0 * s_m
        u, sv, vt = np.linalg.svd(bb.T @ a0)
        d = np.sign(np.linalg.det(u @ vt)) or 1.0
        D = np.diag([1.0, 1.0, d])
        R = u @ D @ vt
        s = float((sv * np.diag(D)).sum() / (bb ** 2).sum()) if scale else 1.0
        fit = s * bb @ R
        r = float(np.sqrt(((fit - a0) ** 2).sum(1).mean()))
        if best is None or r < best[1]:
            full = s * ((mob - cb) * s_m) @ R + ca
            best = (full, r, s, s_m < 0)
    return best


def rmsd(ref, mob, scale=False, mirror=False) -> float:
    return superpose(ref, mob, scale=scale, mirror=mirror)[1]


def superpose_ensemble(X: np.ndarray, n_iter: int = 5, mirror: bool = True) -> np.ndarray:
    """Iteratively superpose models (M, N, 3) on their mean (rotation; mirror images allowed
    relative to model 0 if ``mirror``).  Returns the superposed stack."""
    Y = np.asarray(X, float) - np.nanmean(X, axis=1, keepdims=True)
    if mirror:
        for k in range(1, len(Y)):
            if rmsd(Y[0], -Y[k]) < rmsd(Y[0], Y[k]):
                Y[k] = -Y[k]
    ref = Y[0]
    for _ in range(n_iter):
        for k in range(len(Y)):
            Y[k] = superpose(ref, Y[k])[0]
        ref = np.nanmean(Y, 0)
    return Y


def precision(X: np.ndarray, chrom=None, mirror: bool = True, max_pairs: int = 45) -> dict:
    """Ensemble precision (Stevens 2017 ED Table 2): RMSD of each model to the superposed
    ensemble mean, mean pairwise RMSD; also divided by the bead unit."""
    X = np.asarray(X, float)
    unit = bead_unit(chrom, X) if chrom is not None else float("nan")
    out = {"n_models": int(len(X)), "n_particles": int(X.shape[1]), "bead_unit": unit}
    if len(X) < 2:
        return out
    Y = superpose_ensemble(X, mirror=mirror)
    ref = Y.mean(0)
    to_mean = np.sqrt(((Y - ref) ** 2).sum(2).mean(1))
    pairs = list(itertools.combinations(range(len(X)), 2))[:max_pairs]
    pw = [rmsd(X[a], X[b], mirror=mirror) for a, b in pairs]
    out.update({"rmsd_to_mean": float(to_mean.mean()), "rmsd_pair_mean": float(np.mean(pw)),
                "rmsd_to_mean_per_unit": float(to_mean.mean() / unit) if unit == unit else None,
                "rmsd_pair_mean_per_unit": float(np.mean(pw) / unit) if unit == unit else None,
                "mirror_allowed": mirror})
    return out


def pdist_rows(X: np.ndarray, rows=None) -> np.ndarray:
    """Condensed pairwise distances of X (N, 3) (optionally restricted to ``rows``)."""
    Y = X if rows is None else X[rows]
    iu = np.triu_indices(len(Y), 1)
    return np.linalg.norm(Y[iu[0]] - Y[iu[1]], axis=1)


def dist_matrix_r(D1: np.ndarray, D2: np.ndarray) -> dict:
    """Pearson / Spearman r between two condensed distance vectors (NaNs dropped)."""
    ok = np.isfinite(D1) & np.isfinite(D2)
    if ok.sum() < 3:
        return {"pearson": None, "spearman": None, "n_pairs": int(ok.sum())}
    return {"pearson": float(np.corrcoef(D1[ok], D2[ok])[0, 1]),
            "spearman": float(stats.spearmanr(D1[ok], D2[ok]).statistic),
            "n_pairs": int(ok.sum())}


def cis_mask(chrom) -> np.ndarray:
    """Condensed mask of same-chromosome pairs."""
    chrom = np.asarray(chrom)
    iu = np.triu_indices(len(chrom), 1)
    return chrom[iu[0]] == chrom[iu[1]]


# --------------------------------------------------------------------------- violations

def violations(chrom, X, pairs, counts, unit: float | None = None) -> dict:
    """Restraint violations of models X (M, N, 3) for contact particle ``pairs`` (K, 2) with ``counts``.

    Distances are divided by the ensemble's bead unit (median consecutive-particle
    distance), then: NucDynamics-style %V>3 / %V>4 (d > 1.2 n^-0.33 + 3 / + 4 units) and
    Si-C-style %(d > 2 units).  ``nd_*_native`` repeats the NucDynamics definition in the
    model's own units (the ED Table 2 numbers for NucDynamics models).
    """
    X = np.asarray(X, float)
    if X.ndim == 2:
        X = X[None]
    unit = float(unit or bead_unit(chrom, X))
    pairs = np.asarray(pairs)
    out = {"n_restraints": int(len(pairs)), "bead_unit": unit}
    if not len(pairs):
        return out
    dup = 1.2 * np.asarray(counts, float) ** -0.33
    d = np.linalg.norm(X[:, pairs[:, 0]] - X[:, pairs[:, 1]], axis=2)       # (M, K)
    dn = d / unit
    out.update({
        "nd_pct_viol_gt3": float(100 * np.mean(dn > dup + 3.0)),
        "nd_pct_viol_gt4": float(100 * np.mean(dn > dup + 4.0)),
        "nd_pct_viol_gt3_native": float(100 * np.mean(d > dup + 3.0)),
        "nd_pct_viol_gt4_native": float(100 * np.mean(d > dup + 4.0)),
        "sic_pct_viol_gt2units": float(100 * np.mean(dn > 2.0)),
        "median_contact_dist_units": float(np.median(dn)),
    })
    return out


# --------------------------------------------------------------------------- ranking

def roc_auc(pos_scores, neg_scores) -> float:
    """ROC-AUC = P(score_pos > score_neg) + 0.5 P(tie) (Mann-Whitney), higher score = positive."""
    p = np.asarray(pos_scores, float)
    n = np.asarray(neg_scores, float)
    if not len(p) or not len(n):
        return float("nan")
    allv = np.concatenate([p, n])
    ranks = stats.rankdata(allv)                 # average ranks for ties
    rp = ranks[: len(p)].sum()
    return float((rp - len(p) * (len(p) + 1) / 2) / (len(p) * len(n)))


def average_precision(pos_scores, neg_scores) -> float:
    """PR-AUC as average precision; ties are broken pessimistically (negatives first)."""
    p = np.asarray(pos_scores, float)
    n = np.asarray(neg_scores, float)
    if not len(p):
        return float("nan")
    s = np.concatenate([p, n])
    y = np.concatenate([np.ones(len(p)), np.zeros(len(n))])
    order = np.lexsort((y, -s))                  # by score desc, negatives before positives on ties
    y = y[order]
    tp = np.cumsum(y)
    prec = tp / np.arange(1, len(y) + 1)
    return float((prec * y).sum() / len(p))


def bootstrap_ci(groups_pos, groups_neg, fn, n_boot: int = 1000, seed: int = 0, alpha: float = 0.05):
    """Percentile CI of ``fn(pos, neg)`` resampling *groups* (a positive with its matched
    negatives) with replacement.  ``groups_pos``: list of arrays of positive scores per group,
    ``groups_neg``: list of arrays of negative scores per group."""
    rng = np.random.default_rng(seed)
    G = len(groups_pos)
    if G < 2:
        return [None, None]
    vals = []
    for _ in range(n_boot):
        k = rng.integers(0, G, G)
        vals.append(fn(np.concatenate([groups_pos[i] for i in k]), np.concatenate([groups_neg[i] for i in k])))
    lo, hi = np.nanpercentile(vals, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return [float(lo), float(hi)]
