"""Barcode stripes of microfluidic spatial arrays (DBiT-seq and its Hi-C / ATAC / CUT&Tag variants): every array
row and every column is barcoded through its own channel, so a channel's efficiency adds the same offset to all
spots of its row or column.  Next to the tissue's own (smooth) pattern these offsets are stripes; adjacent rows
differ by chance, so they also weaken the spatial autocorrelation of a feature.

:func:`destripe` estimates the row and column offsets together with a smooth surface (cubic B-splines in x and y, knots every ``spacing``
spots) by least squares and subtracts the offsets only: the smooth part stays.  What can be
told apart is the rough part of the offsets — the jumps between neighbouring rows / columns, which make the
stripes; a channel drift that changes slowly along the array looks like anatomy that varies along one axis and
stays (no method separates the two without a reference), and a sharp anatomical edge that runs exactly along a
row or column is partly taken as offsets.  :func:`smooth_share` is the share of a feature's variance that
such a surface carries, the scale-free measure of how much spatial structure an adjustment leaves.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

__all__ = ["destripe", "smooth_basis", "smooth_share"]


def smooth_basis(xy: np.ndarray, spacing: float = 6.0) -> np.ndarray:
    """A smooth surface basis: tensor-product cubic B-splines in x and y with knots every ``spacing`` units of the
    positions (spots on a barcode grid) — it follows anatomy a few spots wide but no single-row jump."""
    from scipy.interpolate import BSpline

    xy = np.asarray(xy, float)
    mats = []
    for d in range(2):
        u = xy[:, d]
        lo, hi = u.min(), u.max()
        n = max(int(np.ceil((hi - lo) / spacing)), 1)
        inner = np.linspace(lo, hi, n + 1)
        t = np.r_[[lo] * 3, inner, [hi] * 3]
        mats.append(BSpline.design_matrix(np.clip(u, lo, hi), t, 3).toarray())
    bx, by = mats
    B = (bx[:, :, None] * by[:, None, :]).reshape(len(xy), -1)
    return B[:, B.any(axis=0)]


def _lstsq(X: np.ndarray, y: np.ndarray):
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    return b


def destripe(values, rows, cols, xy: Optional[np.ndarray] = None, *, spacing: float = 6.0, regions=None):
    """Values with the row and column offsets of a barcode array removed.

    Parameters
    ----------
    values
        n x p (DataFrame: columns kept), NaN = missing (fitted on the spots with a value).
    rows, cols
        The array row and column of each spot (integers).
    xy
        Positions for the smooth surface (default ``(cols, rows)``).
    spacing
        Knot spacing of the smooth surface (:func:`smooth_basis`), in position units.
    regions
        Sections / arrays (one fit each; default one).

    Returns
    -------
    Same type as ``values``: each value minus its row and column offsets (offsets centred, so a feature's mean
    is kept).
    """
    is_df = isinstance(values, pd.DataFrame)
    V = values.to_numpy(float) if is_df else np.asarray(values, float)
    one = V.ndim == 1
    V = V[:, None] if one else V
    rows, cols = np.asarray(rows), np.asarray(cols)
    pos = np.c_[cols, rows].astype(float) if xy is None else np.asarray(xy, float)
    reg = np.zeros(len(V), int) if regions is None else pd.factorize(np.asarray(regions))[0]
    out = V.copy()
    finite = np.isfinite(V)
    for r in np.unique(reg):
        m = reg == r
        S = smooth_basis(pos[m], spacing)
        R = pd.get_dummies(pd.Series(rows[m]).astype(str), dtype=float).to_numpy()
        C = pd.get_dummies(pd.Series(cols[m]).astype(str), dtype=float).to_numpy()
        # offsets with no smooth part: the row / column indicators made orthogonal to the smooth surface, so
        # that what a smooth function can carry (anatomy, and the unidentifiable slow drift) stays with it
        D = np.c_[R, C]
        D = D - S @ _lstsq(S, D)
        X = np.c_[S, D]                                        # the B-splines sum to 1: no intercept
        k = S.shape[1]
        groups: dict = {}
        for j in range(V.shape[1]):
            groups.setdefault(finite[m, j].tobytes(), []).append(j)
        rows_m = np.flatnonzero(m)
        for _, js in groups.items():                           # columns with the same missing spots together
            ok = finite[m, js[0]]
            if ok.sum() <= X.shape[1]:
                continue
            b = _lstsq(X[ok], V[np.ix_(rows_m[ok], js)])
            out[np.ix_(rows_m[ok], js)] = V[np.ix_(rows_m[ok], js)] - X[ok][:, k:] @ b[k:]
    out = out[:, 0] if one else out
    if is_df:
        return pd.DataFrame(out, index=values.index, columns=values.columns)
    return out


def smooth_share(values, xy: np.ndarray, *, spacing: float = 6.0) -> np.ndarray:
    """The share of each column's variance that a smooth surface (:func:`smooth_basis`) carries (R^2 of the
    least-squares fit on the spots with a value; columns with the same missing spots are fitted together).  For
    values with no spatial pattern it is about (number of basis functions) / (number of spots)."""
    V = values.to_numpy(float) if isinstance(values, pd.DataFrame) else np.asarray(values, float)
    V = V[:, None] if V.ndim == 1 else V
    S = smooth_basis(xy, spacing)
    out = np.full(V.shape[1], np.nan)
    finite = np.isfinite(V)
    groups: dict = {}
    for j in range(V.shape[1]):
        groups.setdefault(finite[:, j].tobytes(), []).append(j)
    for _, js in groups.items():
        ok = finite[:, js[0]]
        if ok.sum() <= S.shape[1]:
            continue
        Y = V[np.ix_(ok, js)]
        b = _lstsq(S[ok], Y)
        var = Y.var(axis=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            out[js] = np.where(var > 0, 1 - (Y - S[ok] @ b).var(axis=0) / var, np.nan)
    return out
