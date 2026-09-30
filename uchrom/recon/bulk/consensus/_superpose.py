"""Superposition of runs, medoid, per-bead spread (numpy)."""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

import numpy as np


def kabsch(ref: np.ndarray, x: np.ndarray, reflection: bool = True, scale: bool = False,
           w: Optional[np.ndarray] = None) -> Tuple[np.ndarray, float]:
    """Superpose ``x`` onto ``ref`` (N x 3; rotation, optionally reflection and a global
    scale); returns (transformed x, RMSD).  Rows with a NaN in either are ignored for the
    fit and stay NaN."""
    ok = np.isfinite(ref).all(1) & np.isfinite(x).all(1)
    ww = np.ones(ok.sum()) if w is None else np.asarray(w, float)[ok]
    a, b = ref[ok], x[ok]
    ca = (a * ww[:, None]).sum(0) / ww.sum()
    cb = (b * ww[:, None]).sum(0) / ww.sum()
    A, B = a - ca, b - cb
    H = (B * ww[:, None]).T @ A
    U, S, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(U @ Vt))
    if not reflection and d < 0:
        U[:, -1] *= -1
        S = S.copy()
        S[-1] *= -1
    R = U @ Vt
    s = S.sum() / (ww * (B ** 2).sum(1)).sum() if scale else 1.0
    out = (x - cb) @ R * s + ca
    r = np.sqrt((ww * ((out[ok] - a) ** 2).sum(1)).sum() / ww.sum())
    return out, float(r)


def pairwise_rmsd(runs: np.ndarray) -> np.ndarray:
    R = len(runs)
    M = np.zeros((R, R))
    for a in range(R):
        for b in range(a + 1, R):
            M[a, b] = M[b, a] = kabsch(runs[a], runs[b])[1]
    return M


def superpose_to_mean(runs: np.ndarray, ref: np.ndarray, n_iter: int = 3) -> Tuple[np.ndarray, np.ndarray]:
    """Align every run to ``ref``, then iteratively to the mean; returns (aligned runs, mean)."""
    al = np.stack([kabsch(ref, r)[0] for r in runs])
    for _ in range(n_iter):
        mean = al.mean(0)
        al = np.stack([kabsch(mean, r)[0] for r in al])
    return al, al.mean(0)


def spread(aligned: np.ndarray) -> np.ndarray:
    """Per-bead RMS deviation of the aligned runs from their mean."""
    m = aligned.mean(0)
    return np.sqrt(((aligned - m) ** 2).sum(2).mean(0))


def spread_by_group(runs: np.ndarray, groups: np.ndarray) -> np.ndarray:
    """Per-bead spread after superposing each group (chromosome) separately."""
    out = np.full(runs.shape[1], np.nan)
    for g in np.unique(groups):
        k = np.flatnonzero(groups == g)
        if len(k) < 3:
            continue
        sub = runs[:, k]
        al, _ = superpose_to_mean(sub, sub[0])
        out[k] = spread(al)
    return out


def radius_of_gyration(x: np.ndarray) -> float:
    x = x[np.isfinite(x).all(1)]
    return float(np.sqrt(((x - x.mean(0)) ** 2).sum(1).mean()))


def distance_r(a: np.ndarray, b: np.ndarray, n_pairs: int = 200_000, seed: int = 0,
               pairs: Optional[Sequence[np.ndarray]] = None) -> float:
    """Pearson r of the distance matrices of two structures over sampled pairs."""
    n = len(a)
    if pairs is None:
        rng = np.random.default_rng(seed)
        if n * (n - 1) // 2 <= n_pairs:
            i, j = np.triu_indices(n, 1)
        else:
            i = rng.integers(0, n, n_pairs)
            j = rng.integers(0, n, n_pairs)
            k = i != j
            i, j = i[k], j[k]
    else:
        i, j = pairs
    da = np.linalg.norm(a[i] - a[j], axis=1)
    db = np.linalg.norm(b[i] - b[j], axis=1)
    return float(np.corrcoef(da, db)[0, 1])
