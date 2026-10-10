"""SPARK-X, the non-parametric covariance test of spatial variation of Zhu, Sun & Zhou (2021), for many features
at once and with covariates (an implementation of the published method, checked against the authors' R package
``SPARK::sparkx``; ``benchmarks/spatial_variable``).

For a feature y on n cells, the covariates X (an intercept first) and a coordinate kernel S (n x d), with
S_r = (I - H) S the coordinates residualised on X (H the projection on X):

    T = n * y' S_r (S_r' S_r)^-1 S_r' y / y'y,      lambda = y'(I - H) y / y'y,

and under no spatial pattern T ~ lambda * chi2_d (the R package evaluates the same mixture, whose kernel
eigenvalues are all 1, with Davies' method at accuracy 1e-4; here the chi-square tail is exact).  Eleven
kernels are tested: the coordinates themselves (``projection``), and, per axis after centring, five Gaussian
(``gaus1``-``gaus5``: exp(-c^2 / 2 l^2)) and five cosine (``cos1``-``cos5``: cos(2 pi c / l)) transforms with
l the 20 / 40 / 60 / 80 / 100 % quantiles of |c|.  The kernel p-values are combined by the Cauchy combination
(ACAT, Liu & Xie 2020), adjusted over the features by Benjamini-Yekutieli as the package does.

Values may be any per-cell number (counts, scores, ratios); a feature's missing cells (NaN) are left out of its
test (the kernels stay those of all cells, residualised on the cells with a value).

References
----------
Zhu, J., Sun, S. & Zhou, X. (2021) SPARK-X: non-parametric modeling enables scalable and robust detection of
spatial expression patterns for large spatial transcriptomic studies. *Genome Biol.* 22:184.
Liu, Y. & Xie, J. (2020) Cauchy combination test. *J. Am. Stat. Assoc.* 115:393-402.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
from scipy import stats

__all__ = ["KERNELS", "coordinate_kernels", "acat", "by_adjust", "sparkx"]

KERNELS = ("projection",) + tuple(f"gaus{i}" for i in range(1, 6)) + tuple(f"cos{i}" for i in range(1, 6))


def coordinate_kernels(coords: np.ndarray, kernels: Union[str, Sequence[str]] = "mixture"
                       ) -> List[Tuple[str, np.ndarray]]:
    """The coordinate kernels of SPARK-X: ``"mixture"`` (all eleven), ``"single"`` (projection only) or a list
    of names from :data:`KERNELS`."""
    xy = np.asarray(coords, float)
    names = KERNELS if kernels == "mixture" else ("projection",) if kernels == "single" else tuple(kernels)
    bad = [k for k in names if k not in KERNELS]
    if bad:
        raise ValueError(f"unknown kernels {bad}; known: {KERNELS}")
    c = xy - xy.mean(axis=0)
    ell = np.quantile(np.abs(c), [0.2, 0.4, 0.6, 0.8, 1.0], axis=0)        # R quantile type 7
    out = []
    for k in names:
        if k == "projection":
            out.append((k, xy))
        elif k.startswith("gaus"):
            out.append((k, np.exp(-c ** 2 / (2 * ell[int(k[4:]) - 1] ** 2))))
        else:
            out.append((k, np.cos(2 * np.pi * c / ell[int(k[3:]) - 1])))
    return out


def acat(p: np.ndarray, weights: Optional[np.ndarray] = None) -> np.ndarray:
    """Cauchy combination of the p-values in each row of ``p`` (n_features x n_tests), as ``SPARK::ACAT``:
    a row with a 0 gives 0, else a row with a 1 gives 1; p < 1e-16 use the approximation tan((0.5-p) pi) ~
    1 / (p pi); a statistic above 1e15 gives 1 / (stat pi).  Rows with NaN give NaN."""
    p = np.atleast_2d(np.asarray(p, float))
    w = np.full(p.shape[1], 1.0 / p.shape[1]) if weights is None else np.asarray(weights, float) / np.sum(weights)
    out = np.full(p.shape[0], np.nan)
    ok = np.isfinite(p).all(axis=1)
    if (p[ok] < 0).any() or (p[ok] > 1).any():
        raise ValueError("p-values must be between 0 and 1")
    small = p < 1e-16
    with np.errstate(divide="ignore", invalid="ignore"):
        terms = np.where(small, w / p / np.pi, w * np.tan((0.5 - p) * np.pi))
    t = terms.sum(axis=1)
    res = np.where(t > 1e15, 1.0 / t / np.pi, stats.cauchy.sf(t))
    zero = (p == 0).any(axis=1)
    one = (p == 1).any(axis=1)
    res = np.where(one, 1.0, res)
    res = np.where(zero, 0.0, res)
    out[ok] = res[ok]
    return out


def by_adjust(p: np.ndarray) -> np.ndarray:
    """Benjamini-Yekutieli adjusted p-values, as R's ``p.adjust(method="BY")`` (NaN kept, not counted)."""
    p = np.asarray(p, float)
    out = np.full_like(p, np.nan)
    ok = np.isfinite(p)
    q = p[ok]
    n = len(q)
    if n:
        c = np.sum(1.0 / np.arange(1, n + 1))
        order = np.argsort(-q, kind="stable")
        i = np.arange(n, 0, -1)
        adj = np.minimum(1.0, np.minimum.accumulate(c * n / i * q[order]))
        res = np.empty(n)
        res[order] = adj
        out[ok] = res
    return out


def _basis(m: np.ndarray, tol: float = 1e-10) -> np.ndarray:
    """An orthonormal basis of the column space of ``m`` (rank-deficient columns dropped)."""
    if m.shape[1] == 0:
        return m
    u, s, _ = np.linalg.svd(m, full_matrices=False)
    keep = s > tol * max(s[0], 1e-300) * max(m.shape)
    return u[:, keep]


def _block(Y: np.ndarray, kernels, X: np.ndarray):
    """Statistics, p-values and degrees of freedom per kernel for the columns of a complete block ``Y``."""
    n = Y.shape[0]
    Q = _basis(X)
    yy = (Y ** 2).sum(axis=0)
    hy = Q.T @ Y
    lam = 1.0 - (hy ** 2).sum(axis=0) / yy
    stat = np.full((Y.shape[1], len(kernels)), np.nan)
    pval = np.full_like(stat, np.nan)
    df = np.zeros(len(kernels), int)
    for j, (_, S) in enumerate(kernels):
        Sr = S - Q @ (Q.T @ S)
        U = _basis(Sr)
        df[j] = U.shape[1]
        if df[j] == 0:
            continue
        with np.errstate(divide="ignore", invalid="ignore"):
            t = n * ((U.T @ Y) ** 2).sum(axis=0) / yy
            stat[:, j] = t
            pval[:, j] = stats.chi2.sf(t / lam, df[j])
    bad = ~(yy > 0) | ~(lam > 1e-12)                 # all zero / no variation left after the covariates
    stat[bad] = np.nan
    pval[bad] = np.nan
    return stat, pval, df


def sparkx(values, coords: np.ndarray, *, covariates: Optional[np.ndarray] = None, intercept: bool = True,
           kernels: Union[str, Sequence[str]] = "mixture", min_cells: int = 10) -> pd.DataFrame:
    """SPARK-X on arrays.

    Parameters
    ----------
    values
        n_cells x n_features (DataFrame: its columns name the features; NaN = missing).
    coords
        n_cells x d positions.
    covariates
        n_cells x c covariates the test is adjusted for (cell-type composition, depth, …).
    intercept
        Add an intercept to the covariates (the package's test without covariates is the test with an
        intercept only; give ``covariates`` an intercept column and ``intercept=False`` to reproduce the
        package's covariate path exactly).
    kernels
        ``"mixture"``, ``"single"`` or kernel names (:func:`coordinate_kernels`).

    Returns
    -------
    DataFrame
        One row per feature: ``n``, ``stat_<kernel>``, ``pval_<kernel>``, ``pval`` (combined) and ``padj``
        (Benjamini-Yekutieli); ``.attrs["df"]`` holds the degrees of freedom of each kernel.
    """
    if isinstance(values, pd.DataFrame):
        names = list(values.columns)
        Y = values.to_numpy(float)
    else:
        Y = np.asarray(values, float)
        Y = Y[:, None] if Y.ndim == 1 else Y
        names = list(range(Y.shape[1]))
    n = Y.shape[0]
    xy = np.asarray(coords, float)
    if xy.shape[0] != n:
        raise ValueError(f"coords has {xy.shape[0]} rows, values {n}")
    cov = np.zeros((n, 0)) if covariates is None else np.asarray(covariates, float).reshape(n, -1)
    X = np.hstack([np.ones((n, 1)), cov]) if intercept else cov
    if X.shape[1] == 0:
        raise ValueError("no covariates and intercept=False: the test needs at least an intercept")
    ker = coordinate_kernels(xy, kernels)
    knames = [k for k, _ in ker]
    stat = np.full((Y.shape[1], len(ker)), np.nan)
    pval = np.full_like(stat, np.nan)
    count = np.zeros(Y.shape[1], int)
    finite = np.isfinite(Y) & np.isfinite(X).all(axis=1)[:, None]
    dfs = {}
    groups = {}
    for j in range(Y.shape[1]):
        groups.setdefault(finite[:, j].tobytes(), []).append(j)
    for key, js in groups.items():
        m = finite[:, js[0]]
        count[js] = int(m.sum())
        if m.sum() < max(min_cells, X.shape[1] + 3):
            continue
        sub = [(k, S[m]) for k, S in ker]
        s, p, df = _block(Y[np.ix_(m, js)], sub, X[m])
        stat[js], pval[js] = s, p
        dfs.update({k: int(d) for k, d in zip(knames, df)})
    comb = acat(pval)
    out = pd.DataFrame({"n": count}, index=pd.Index(names, name="feature"))
    for j, k in enumerate(knames):
        out[f"stat_{k}"] = stat[:, j]
    for j, k in enumerate(knames):
        out[f"pval_{k}"] = pval[:, j]
    out["pval"] = comb
    out["padj"] = by_adjust(comb)
    out.attrs["df"] = dfs
    return out
