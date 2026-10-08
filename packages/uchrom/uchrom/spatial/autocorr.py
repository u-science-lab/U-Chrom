"""Global spatial autocorrelation of per-cell values over a neighbour graph: Moran's I and Geary's C, with their
moments under normality and under randomisation (Cliff & Ord 1981) and permutation p-values, many features at
once.

For a feature x on n cells with weights w (``transform="r"``: rows standardised to sum 1), z = x - mean(x),
S0 = sum w_ij, S1 = 1/2 sum (w_ij + w_ji)^2, S2 = sum_i (w_i. + w_.i)^2:

* Moran's I = n / S0 * z'Wz / z'z, E[I] = -1 / (n - 1);
* Geary's C = (n - 1) sum w_ij (x_i - x_j)^2 / (2 S0 z'z), E[C] = 1.

The variances are those of PySAL's ``esda`` (``VI_norm`` / ``VI_rand``, ``VC_norm`` / ``VC_rand``); positive
autocorrelation — a spatially variable feature — is I > E[I], C < 1.  Cells where a feature is missing (NaN) are
left out of that feature: its weights are those of the graph restricted to the cells with a value, transformed
again.

References
----------
Moran, P. A. P. (1950) *Biometrika* 37:17-23.  Geary, R. C. (1954) *The Incorporated Statistician* 5:115-145.
Cliff, A. D. & Ord, J. K. (1981) *Spatial Processes: Models and Applications*. Pion.
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence, Union

import numpy as np
import pandas as pd
import scipy.sparse as sps
from scipy import stats

from .graph import SpatialGraph

__all__ = ["cell_values", "spatial_autocorr", "bh_adjust"]


def cell_values(cd, features: Union[None, str, Sequence[str]] = None, *,
                values: Union[None, pd.DataFrame, pd.Series] = None) -> pd.DataFrame:
    """Per-cell values as a DataFrame indexed by cell id (str), one column per feature.

    ``values`` is used as given (a Series becomes one column); else ``features`` names columns of
    ``cd.cells``, or one key of ``cd.cellm`` (a 2-D array: columns ``"<key>[j]"``).
    """
    if values is not None:
        df = values.to_frame() if isinstance(values, pd.Series) else values.copy()
        df.index = df.index.astype(str)
        return df
    if features is None:
        raise ValueError("give features= or values=")
    ids = pd.Index([str(c) for c in cd._cell_ids_axis()], name="cell_id")
    if isinstance(features, str) and features in cd.cellm:
        arr = np.asarray(cd.cellm[features], dtype=float)
        if arr.ndim == 1:
            arr = arr[:, None]
        if arr.ndim != 2:
            raise ValueError(f"cellm[{features!r}] has {arr.ndim} dimensions; give a 2-D array or values=")
        return pd.DataFrame(arr, index=ids, columns=[f"{features}[{j}]" for j in range(arr.shape[1])])
    names = [features] if isinstance(features, str) else list(features)
    missing = [f for f in names if f not in cd.cells.columns]
    if missing:
        raise KeyError(f"not in cd.cells (nor a cellm key): {missing}")
    df = cd.cells[names].apply(pd.to_numeric, errors="coerce").astype(float)
    df.index = ids
    return df


def bh_adjust(p: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg adjusted p-values (NaN kept)."""
    p = np.asarray(p, float)
    out = np.full_like(p, np.nan)
    ok = np.isfinite(p)
    q = p[ok]
    n = len(q)
    if n:
        order = np.argsort(q)
        ranked = q[order] * n / np.arange(1, n + 1)
        ranked = np.minimum.accumulate(ranked[::-1])[::-1]
        res = np.empty(n)
        res[order] = np.minimum(ranked, 1.0)
        out[ok] = res
    return out


def _moments(w: sps.csr_matrix):
    s0 = float(w.sum())
    wt = (w + w.T).tocsr()
    s1 = 0.5 * float(wt.multiply(wt).sum())
    rs = np.asarray(w.sum(axis=1)).ravel()
    cs = np.asarray(w.sum(axis=0)).ravel()
    s2 = float(((rs + cs) ** 2).sum())
    return s0, s1, s2, rs, cs


def _weights(adj: sps.csr_matrix, transform: str) -> sps.csr_matrix:
    w = adj.astype(float).tocsr()
    if transform == "b":
        return w
    deg = np.asarray(w.sum(axis=1)).ravel()
    inv = np.divide(1.0, deg, out=np.zeros_like(deg), where=deg > 0)
    return (sps.diags(inv) @ w).tocsr()


def _tail(z: np.ndarray, alternative: str, lower_is_positive: bool) -> np.ndarray:
    if alternative == "two-sided":
        return 2 * stats.norm.sf(np.abs(z))
    pos = stats.norm.cdf(z) if lower_is_positive else stats.norm.sf(z)
    return pos if alternative == "greater" else 1 - pos


def _block(Z: np.ndarray, w: sps.csr_matrix, method: str):
    """Statistic, expectation and variances (normality, randomisation) for the columns of a complete block."""
    n = Z.shape[0]
    s0, s1, s2, rs, cs = _moments(w)
    zz = (Z ** 2).sum(axis=0)
    k = (Z ** 4).sum(axis=0) / n / (zz / n) ** 2
    with np.errstate(divide="ignore", invalid="ignore"):
        if method == "moran":
            stat = n / s0 * (Z * (w @ Z)).sum(axis=0) / zz
            e = -1.0 / (n - 1)
            v_norm = (n * n * s1 - n * s2 + 3 * s0 * s0) / ((n * n - 1) * s0 * s0) - e * e
            a = n * ((n * n - 3 * n + 3) * s1 - n * s2 + 3 * s0 * s0)
            b = k * ((n * n - n) * s1 - 2 * n * s2 + 6 * s0 * s0)
            v_rand = (a - b) / ((n - 1) * (n - 2) * (n - 3) * s0 * s0) - e * e
        else:
            num = ((Z ** 2) * (rs + cs)[:, None]).sum(axis=0) - 2 * (Z * (w @ Z)).sum(axis=0)
            stat = (n - 1) * num / (2 * s0 * zz)
            e = 1.0
            v_norm = ((2 * s1 + s2) * (n - 1) - 4 * s0 * s0) / (2 * (n + 1) * s0 * s0)
            a = (n - 1) * s1 * (n * n - 3 * n + 3 - (n - 1) * k)
            b = 0.25 * ((n - 1) * s2 * (n * n + 3 * n - 6 - (n * n - n + 2) * k))
            c = s0 * s0 * (n * n - 3 - (n - 1) ** 2 * k)
            v_rand = (a - b + c) / (n * (n - 2) * (n - 3) * s0 * s0)
    v_norm = np.full(Z.shape[1], v_norm, float)
    stat = np.where(zz > 0, stat, np.nan)
    return stat, e, v_norm, np.where(zz > 0, v_rand, np.nan)


def _perm_counts(Z: np.ndarray, w: sps.csr_matrix, method: str, stat: np.ndarray, n_perms: int,
                 rng: np.random.Generator):
    """How many permutations are at least as extreme as ``stat`` towards positive and towards negative
    autocorrelation (the cells' values shuffled over the graph)."""
    pos = np.zeros(Z.shape[1], np.int64)
    neg = np.zeros(Z.shape[1], np.int64)
    n = Z.shape[0]
    for _ in range(n_perms):
        s, _, _, _ = _block(Z[rng.permutation(n)], w, method)
        hi, lo = s >= stat, s <= stat
        pos += hi if method == "moran" else lo
        neg += lo if method == "moran" else hi
    return pos, neg


def spatial_autocorr(cd=None, features=None, *, graph: SpatialGraph, values=None, method: str = "moran",
                     transform: str = "r", alternative: str = "greater", n_perms: int = 0, seed: int = 0,
                     min_cells: int = 10) -> pd.DataFrame:
    """Moran's I or Geary's C of every feature over ``graph``.

    Parameters
    ----------
    cd, features, values
        The per-cell values (:func:`cell_values`); ``cd`` may be None with ``values=``.
    graph
        :func:`~uchrom.spatial.spatial_neighbors` (its cells; values of other cells are ignored).
    method
        ``"moran"`` or ``"geary"``.
    transform
        ``"r"`` row-standardised (default, as esda) or ``"b"`` binary weights.
    alternative
        ``"greater"`` (positive autocorrelation; default), ``"less"`` or ``"two-sided"``.
    n_perms
        Permutations for ``p_perm`` (0: none); the cells' values are shuffled over the graph.
    min_cells
        Features with fewer cells with a value get NaN.

    Returns
    -------
    DataFrame
        One row per feature: ``n`` (cells with a value), ``I`` or ``C``, ``expected``, ``var_norm``,
        ``z_norm``, ``p_norm``, ``var_rand``, ``z_rand``, ``p_rand`` [, ``p_perm``], ``pval`` (``p_perm`` with
        permutations, else ``p_rand``) and ``padj`` (Benjamini-Hochberg over the features).
    """
    if method not in ("moran", "geary"):
        raise ValueError(f"method must be 'moran' or 'geary', not {method!r}")
    if alternative not in ("greater", "less", "two-sided"):
        raise ValueError(f"alternative must be 'greater', 'less' or 'two-sided', not {alternative!r}")
    df = cell_values(cd, features, values=values).reindex(pd.Index(graph.cell_ids.astype(str)))
    X = df.to_numpy(float)
    finite = np.isfinite(X)
    p = X.shape[1]
    cols = {k: np.full(p, np.nan) for k in ("stat", "expected", "var_norm", "var_rand", "n")}
    if n_perms:
        cols["p_perm"] = np.full(p, np.nan)
    rng = np.random.default_rng(seed)
    # features grouped by the cells that have a value (one restricted graph per pattern)
    keys = {}
    for j in range(p):
        keys.setdefault(finite[:, j].tobytes(), []).append(j)
    for key, js in keys.items():
        mask = finite[:, js[0]]
        n = int(mask.sum())
        if n < max(min_cells, 4):
            continue
        adj = graph.adjacency[mask][:, mask] if not mask.all() else graph.adjacency
        w = _weights(adj, transform)
        if w.nnz == 0:
            continue
        Z = X[np.ix_(mask, js)]
        Z = Z - Z.mean(axis=0)
        stat, e, v_norm, v_rand = _block(Z, w, method)
        cols["stat"][js], cols["expected"][js], cols["n"][js] = stat, e, n
        cols["var_norm"][js], cols["var_rand"][js] = v_norm, v_rand
        if n_perms:
            pos, neg = _perm_counts(Z, w, method, stat, n_perms, rng)
            p_pos, p_neg = (pos + 1) / (n_perms + 1), (neg + 1) / (n_perms + 1)
            pp = {"greater": p_pos, "less": p_neg,
                  "two-sided": np.minimum(1.0, 2 * np.minimum(p_pos, p_neg))}[alternative]
            cols["p_perm"][js] = np.where(np.isfinite(stat), pp, np.nan)
    lower = method == "geary"
    with np.errstate(divide="ignore", invalid="ignore"):
        z_norm = (cols["stat"] - cols["expected"]) / np.sqrt(cols["var_norm"])
        z_rand = (cols["stat"] - cols["expected"]) / np.sqrt(cols["var_rand"])
    out = pd.DataFrame({"n": cols["n"], "I" if method == "moran" else "C": cols["stat"],
                        "expected": cols["expected"], "var_norm": cols["var_norm"], "z_norm": z_norm,
                        "p_norm": _tail(z_norm, alternative, lower), "var_rand": cols["var_rand"],
                        "z_rand": z_rand, "p_rand": _tail(z_rand, alternative, lower)},
                       index=pd.Index(df.columns, name="feature"))
    if n_perms:
        out["p_perm"] = cols["p_perm"]
    out["pval"] = out["p_perm"] if n_perms else out["p_rand"]
    out["padj"] = bh_adjust(out["pval"].to_numpy())
    out["n"] = out["n"].astype("Int64")
    return out
