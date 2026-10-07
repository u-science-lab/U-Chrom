"""Scores of recovered type profiles against truth pseudo-bulks (PREREG §14.4).

Every function takes profiles as (T, n_pairs) arrays on one :class:`tissue.Layout` (rows = types; a
NaN row = a type the method did not recover; it scores NaN and counts as 0 in the type means).

Features (computed identically for every method, the oracle and the truth)
-------------------------------------------------------------------------
``oe``        per chromosome the symmetric map, box-smoothed over (2 ``smooth`` + 1)^2 bins (mean of the
              in-chromosome entries), divided by its per-diagonal mean (O/E), log2((O + psi E) / ((1 + psi)
              E)) with psi = 0.1; the pairs with separation in ``band`` (Mb) concatenated over chromosomes.
``contrast``  oe_t minus the mean over the T types of oe (type-specific pattern).
``comp``      distance-centred compartment score per bin (as ``benchmarks/spatial_composition``):
              s_i = sum_j C_ij (v_j - v_(2i-j)) / 2 / sum_j C_ij over 2 <= |i - j| bins with a valid mirror
              bin, v = the reference E1 (fixed, from the truth's all-type pseudo-bulk).  ``comp contrast`` =
              s_t minus the mean over types.
``ins``       insulation (250 kb): log2 of the mean O/E in the w x w square upstream-downstream of each
              bin boundary (w = 4 bins), minus its chromosome median; contrast over types.
``ps``        log10 P(s) per separation bin (log-spaced), contrast over types.

Metrics
-------
P1 ``contrast_r``  Pearson r(contrast_t(method), contrast_t(truth)), mean over types (1 Mb, 2-50 Mb).
P2 ``comp_r``      Pearson r of the compartment-score contrasts, mean over types (1 Mb).
``oe_r``           r(oe_t(method), oe_t(truth)) (no contrast; high for any method).
``ident``          type identification: R_tu = r(contrast_t(method), contrast_u(truth)); accuracy =
                   fraction of types with argmax_u R_tu = t; margin = mean_t (R_tt - mean_{u != t} R_tu).
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import uniform_filter

PSI = 0.1


def _sym(vec: np.ndarray, n: int) -> np.ndarray:
    m = np.zeros((n, n))
    i, j = np.triu_indices(n)
    m[i, j] = vec
    m[j, i] = vec
    return m


def _smooth(m: np.ndarray, k: int) -> np.ndarray:
    if k <= 0:
        return m
    size = 2 * k + 1
    return uniform_filter(m, size=size, mode="constant") / np.maximum(
        uniform_filter(np.ones_like(m), size=size, mode="constant"), 1e-12)


def _diag_mean(m: np.ndarray) -> np.ndarray:
    n = len(m)
    e = np.array([np.mean(np.diagonal(m, d)) for d in range(n)])
    i, j = np.indices(m.shape)
    return e[np.abs(i - j)]


def oe_features(P: np.ndarray, layout, *, band=(2, 50), smooth: int = 1) -> np.ndarray:
    """(T, n_band_pairs) log O/E of every profile (NaN rows stay NaN)."""
    lo = int(round(band[0] * 1e6 / layout.res))
    hi = int(round(band[1] * 1e6 / layout.res))
    out = []
    for t in range(P.shape[0]):
        if not np.all(np.isfinite(P[t])):
            out.append(None)
            continue
        parts = []
        for c, _name, sl in layout.chrom_slices():
            n = int(layout.n[c])
            m = _smooth(_sym(P[t, sl], n), smooth)
            e = _diag_mean(m)
            with np.errstate(divide="ignore", invalid="ignore"):
                v = np.where(e > 0, np.log2((m + PSI * e) / ((1 + PSI) * e)), np.nan)
            i, j = np.triu_indices(n)
            sel = (j - i >= lo) & (j - i <= hi)
            parts.append(v[i[sel], j[sel]])
        out.append(np.concatenate(parts))
    L = max(len(o) for o in out if o is not None)
    return np.vstack([o if o is not None else np.full(L, np.nan) for o in out])


def contrast(F: np.ndarray) -> np.ndarray:
    """Feature rows minus the mean over the recovered rows (rows with any finite entry); an entry
    that is NaN in any recovered row is NaN in every row."""
    ok = np.any(np.isfinite(F), 1)
    if not ok.any():
        return F * np.nan
    with np.errstate(invalid="ignore"):
        return F - F[ok].mean(0)


def _r(a, b, min_n: int = 10) -> float:
    """Pearson r over the entries finite in both (NaN with fewer than ``min_n``, or a constant side)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < min_n:
        return np.nan
    a, b = a[ok], b[ok]
    if a.std() == 0 or b.std() == 0:
        return np.nan
    return float(np.corrcoef(a, b)[0, 1])


def row_r(X: np.ndarray, Y: np.ndarray) -> np.ndarray:
    return np.array([_r(X[t], Y[t]) for t in range(X.shape[0])])


def ident(Cm: np.ndarray, Ct: np.ndarray) -> dict:
    T = Cm.shape[0]
    R = np.array([[_r(Cm[t], Ct[u]) for u in range(T)] for t in range(T)])
    Rz = np.where(np.isfinite(R), R, -np.inf)
    acc = float(np.mean([np.argmax(Rz[t]) == t if np.isfinite(R[t, t]) else False for t in range(T)]))
    off = np.array([np.mean(o[np.isfinite(o)]) if np.isfinite(o).any() else np.nan
                    for o in (np.delete(R[t], t) for t in range(T))])
    margin = np.nan_to_num(np.diag(R) - off, nan=0.0)
    return {"R": R, "accuracy": acc, "margin": float(np.mean(margin))}


# --------------------------------------------------------------------------- compartments

def reference_e1(P_ref: np.ndarray, layout, smooth: int = 0) -> np.ndarray:
    """E1 per bin of one profile (1-D, n_pairs): first eigenvector of the O/E correlation, per chromosome.

    Sign: positive correlation with the bin's contact coverage (any fixed rule works: scores are compared
    as correlations of contrasts, which a per-chromosome sign flip of v leaves unchanged).
    """
    e1 = np.zeros(layout.n_bins)
    for c, _name, sl in layout.chrom_slices():
        n = int(layout.n[c])
        m = _smooth(_sym(P_ref[sl], n), smooth)
        cov = m.sum(1)
        good = cov > np.percentile(cov[cov > 0], 5) if (cov > 0).any() else cov > 0
        e = _diag_mean(m)
        oe = np.where(e > 0, m / np.maximum(e, 1e-300), 0)[np.ix_(good, good)]
        if good.sum() < 3:
            continue
        cc = np.corrcoef(oe)
        cc = np.nan_to_num(cc)
        w, v = np.linalg.eigh(cc)
        x = v[:, -1]
        if np.corrcoef(x, cov[good])[0, 1] < 0:
            x = -x
        off = int(layout.bin_off[c])
        e1[off + np.flatnonzero(good)] = x / (x.std() + 1e-12)
    return e1


def comp_scores(P: np.ndarray, layout, e1: np.ndarray, min_sep: int = 2) -> np.ndarray:
    """(T, n_bins) distance-centred compartment score (NaN where a bin has no partner contacts)."""
    T = P.shape[0]
    out = np.full((T, layout.n_bins), np.nan)
    for c, _name, sl in layout.chrom_slices():
        n = int(layout.n[c])
        off = int(layout.bin_off[c])
        v = e1[off:off + n]
        i, j = np.indices((n, n))
        mirror = 2 * i - j
        valid = (np.abs(i - j) >= min_sep) & (mirror >= 0) & (mirror < n)
        dv = np.where(valid, (v[j] - v[np.clip(mirror, 0, n - 1)]) / 2, 0.0)
        for t in range(T):
            if not np.all(np.isfinite(P[t])):
                continue
            m = _sym(P[t, sl], n)
            num = (m * dv).sum(1)
            den = (m * valid).sum(1)
            out[t, off:off + n] = np.where(den > 0, num / np.maximum(den, 1e-300), np.nan)
    return out


# --------------------------------------------------------------------------- insulation / P(s)

def insulation(P: np.ndarray, layout, w: int = 4) -> np.ndarray:
    """(T, n_bins) log2 insulation (mean O/E of the w x w square across each bin), chromosome-median centred."""
    T = P.shape[0]
    out = np.full((T, layout.n_bins), np.nan)
    for c, _name, sl in layout.chrom_slices():
        n = int(layout.n[c])
        off = int(layout.bin_off[c])
        for t in range(T):
            if not np.all(np.isfinite(P[t])):
                continue
            m = _sym(P[t, sl], n)
            e = _diag_mean(m)
            oe = np.where(e > 0, m / np.maximum(e, 1e-300), 0)
            ins = np.full(n, np.nan)
            for k in range(w, n - w):
                ins[k] = oe[k - w:k, k + 1:k + 1 + w].mean()
            with np.errstate(divide="ignore", invalid="ignore"):
                li = np.log2(ins)
            li[~np.isfinite(li)] = np.nan
            out[t, off:off + n] = li - np.nanmedian(li)
    return out


def ps_curve(P: np.ndarray, layout, n_bins: int = 30) -> tuple[np.ndarray, np.ndarray]:
    """log10 contact probability per log-spaced separation bin (>= 1 bin), (T, n_bins)."""
    sep = layout.pair_sep
    edges = np.unique(np.round(np.logspace(0, np.log10(sep.max() + 1), n_bins + 1)).astype(int))
    k = np.digitize(sep, edges) - 1
    ok = (sep >= 1) & (k >= 0) & (k < len(edges) - 1)
    npairs = np.bincount(k[ok], minlength=len(edges) - 1)
    out = []
    for t in range(P.shape[0]):
        if not np.all(np.isfinite(P[t])):
            out.append(np.full(len(edges) - 1, np.nan))
            continue
        s = np.bincount(k[ok], weights=P[t][ok], minlength=len(edges) - 1)
        with np.errstate(divide="ignore", invalid="ignore"):
            v = np.log10(s / np.maximum(npairs, 1))
        out.append(np.where(np.isfinite(v), v, np.nan))
    return np.vstack(out), edges


# --------------------------------------------------------------------------- one call

def score_profiles(P: np.ndarray, truth: dict, layout, *, band=(2, 50), smooth: int = 1) -> dict:
    """All 1 Mb metrics of ``P`` against ``truth`` (from :func:`truth_features`)."""
    F = oe_features(P, layout, band=band, smooth=smooth)
    C = contrast(F)
    res = {}
    r_c = row_r(C, truth["contrast"])
    r_o = row_r(F, truth["oe"])
    res["contrast_r_type"] = r_c.tolist()
    res["contrast_r"] = float(np.mean(np.nan_to_num(r_c, nan=0.0)))
    res["oe_r_type"] = r_o.tolist()
    res["oe_r"] = float(np.mean(np.nan_to_num(r_o, nan=0.0)))
    s = comp_scores(P, layout, truth["e1"])
    sc = contrast_bins(s)
    good = truth["comp_ok"]
    r_s = np.array([_r(sc[t, good], truth["comp_contrast"][t, good]) for t in range(P.shape[0])])
    res["comp_r_type"] = r_s.tolist()
    res["comp_r"] = float(np.mean(np.nan_to_num(r_s, nan=0.0)))
    idt = ident(C, truth["contrast"])
    res["ident_accuracy"] = idt["accuracy"]
    res["ident_margin"] = idt["margin"]
    res["ident_R"] = idt["R"].tolist()
    ps, _ = ps_curve(P, layout)
    psc = contrast(ps)
    r_ps = np.array([_r(psc[t], truth["ps_contrast"][t], min_n=5) for t in range(P.shape[0])])
    res["ps_r_type"] = r_ps.tolist()
    res["ps_r"] = float(np.mean(np.nan_to_num(r_ps, nan=0.0)))
    return res


def contrast_bins(s: np.ndarray) -> np.ndarray:
    """Per-bin features minus their mean over the recovered types (a bin NaN in any of them -> NaN)."""
    return contrast(s)


def truth_features(P_truth: np.ndarray, layout, *, band=(2, 50), smooth: int = 1, P_ref=None) -> dict:
    """Features of the truth profiles (T, pairs); ``P_ref`` (pairs) = the profile E1 is taken from
    (default: the mean of the truth profiles)."""
    F = oe_features(P_truth, layout, band=band, smooth=smooth)
    ref = P_ref if P_ref is not None else P_truth.mean(0)
    e1 = reference_e1(ref, layout)
    s = comp_scores(P_truth, layout, e1)
    ps, _ = ps_curve(P_truth, layout)
    return {"oe": F, "contrast": contrast(F), "e1": e1, "comp": s, "comp_contrast": contrast_bins(s),
            "comp_ok": np.all(np.isfinite(s), 0) & (e1 != 0),   # bins scored for every truth type
            "ps_contrast": contrast(ps)}


def score_insulation(P: np.ndarray, P_truth: np.ndarray, layout) -> dict:
    a = contrast_bins(insulation(P, layout))
    b = contrast_bins(insulation(P_truth, layout))
    r = []
    for t in range(P.shape[0]):
        ok = np.isfinite(a[t]) & np.isfinite(b[t])
        r.append(_r(a[t, ok], b[t, ok]) if ok.sum() > 10 else np.nan)
    r = np.array(r)
    return {"ins_r_type": r.tolist(), "ins_r": float(np.mean(np.nan_to_num(r, nan=0.0)))}


# --------------------------------------------------------------------------- statistics

def bootstrap_ci(x, n_boot: int = 2000, seed: int = 0, alpha: float = 0.05) -> tuple[float, float, float]:
    """Mean and percentile bootstrap CI over units."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    b = rng.choice(x, size=(n_boot, len(x)), replace=True).mean(1)
    return float(x.mean()), float(np.quantile(b, alpha / 2)), float(np.quantile(b, 1 - alpha / 2))
