"""ArcFISH preprocessing of chromatin tracing data: per-axis pairwise variances, their outlier filter and
normalisation by genomic distance, and the axis weights.

Reference
---------
Yu H. *et al.* ArcFISH: accurate and robust 3D genome feature discovery from chromatin tracing data.  bioRxiv
2025.11.26.690837 (software: github.com/hyuyu104/ArcFISH).  U-Chrom's own implementation of the published
algorithm; its output is checked against the authors' package (commit a21d889) by uchrom-reproducibility ``benchmarks/toolkit_parity/arcfish_parity/``
(per-position statistics and calls on the datasets of the authors' tutorials and others).

Conventions (the authors', so that the results agree)
-----------------------------------------------------
* The loci of a chromosome are its bins with at least one finite coordinate, keyed and sorted by ``start``; the
  genomic distance of two loci is ``|start_i - start_j|``.
* A trace that observed a locus more than once keeps its first spot (spot order).
* Medians are the usual medians: the mean of the two middle values for an even count.
* A variance within ``1e-8`` of zero (``numpy.isclose``) is left out of a LOWESS fit.

Pipeline (per chromosome)
-------------------------
1. :func:`axis_variance_cube`: the coordinates as a ``(traces, loci, 3)`` cube, the per-axis pairwise variance /
   count / mean (unfiltered) and the axis weights.
2. :func:`filter_normalize`, per axis and locus pair, over the traces observing both loci:

   - pass 1: the raw variance is the median squared deviation of the differences from their median; LOWESS of
     ``log raw variance`` on ``log genomic distance`` (``frac`` 0.1, upper triangle) gives a stratified variance,
     its square root the stratified s.d.; a difference farther than ``k_sigma`` (4) s.d. from the pair's median is
     an outlier and is removed;
   - pass 2: ``count`` = the remaining traces, ``var`` = the mean squared deviation from their mean; LOWESS of
     ``log var`` on ``log genomic distance`` gives the expected variance and ``norm_var = var / expected``
     (diagonal 0).

3. :func:`axis_weight`: per axis, each trace centred at its mean over loci; per locus the mean square over the
   traces; the weight is ``1 / median over loci``, normalised to sum 1.

The pairwise differences run on a torch device (``'auto' | 'cpu' | 'cuda' | 'mps'``) in row blocks; the LOWESS fits
use ``statsmodels`` on the CPU.  ``uchrom.fea.arc_stream`` computes the same without the
``(3, traces, loci, loci)`` tensor.
"""

from __future__ import annotations

import warnings
from typing import Optional

import numpy as np
import pandas as pd

from uchrom.utils import get_device, lowess_log_log
from uchrom.utils.stats import default_float_dtype

#: variances within this of zero are left out of the LOWESS fits (``numpy.isclose(v, 0)``)
ZERO_VAR_ATOL = 1e-8


# ----------------------------------------------------------------------
# Coordinate cube: (n_traces, n_bins, 3) with NaN padding
# ----------------------------------------------------------------------

def _coord_cube_for_chrom(cd, chrom):
    """Return ``(coords_cube, bin_ids, trace_ids)`` for one chromosome.

    ``coords_cube[t, i, :]`` is the (x, y, z) of trace ``t`` at locus ``i`` (NaN if the trace missed it).  Loci are
    the chromosome's starts with a finite coordinate, sorted; ``bin_ids`` are their ``(start, end)`` (the end of the
    first spot at that start); traces in order of first appearance; a repeated (trace, start) keeps its first spot.
    """
    if getattr(cd, "backed", False):   # read only this chromosome's rows
        cd = cd.get_chrom(str(chrom), columns="coords")
    sp = cd.spots
    on = (sp["chrom"].astype(str) == str(chrom)).to_numpy()
    if not on.any():
        raise ValueError(f"No spots found for chromosome {chrom}")
    df = pd.DataFrame({
        "trace_id": sp["trace_id"].to_numpy()[on],
        "start": sp["start"].to_numpy()[on].astype(np.int64),
        "end": sp["end"].to_numpy()[on].astype(np.int64),
    })
    xyz = np.asarray(cd.coords, dtype=np.float64)[on]
    first = ~df.duplicated(["trace_id", "start"], keep="first").to_numpy()
    df, xyz = df[first].reset_index(drop=True), xyz[first]
    finite = np.isfinite(xyz).any(axis=1)
    observed = np.unique(df["start"].to_numpy()[finite])
    keep = np.isin(df["start"].to_numpy(), observed)
    df, xyz = df[keep].reset_index(drop=True), xyz[keep]

    starts = observed
    ends = df.groupby("start", sort=True)["end"].first().reindex(starts).to_numpy()
    bin_keys = [(int(s), int(e)) for s, e in zip(starts, ends)]
    ti, trace_ids = pd.factorize(df["trace_id"], sort=False)
    bi = np.searchsorted(starts, df["start"].to_numpy())
    cube = np.full((len(trace_ids), len(starts), 3), np.nan, dtype=np.float64)
    cube[ti, bi] = xyz
    return cube, bin_keys, list(trace_ids)


def _axis_weight_cube(cube: np.ndarray) -> np.ndarray:
    """Axis weights of a ``(traces, loci, 3)`` coordinate cube (see the module docstring)."""
    w = np.empty(3)
    with warnings.catch_warnings(), np.errstate(invalid="ignore", divide="ignore"):
        warnings.simplefilter("ignore", RuntimeWarning)
        for a in range(3):
            x = cube[:, :, a]
            x0 = x - np.nanmean(x, axis=1)[:, None]
            w[a] = 1.0 / np.nanmedian(np.nanmean(x0 * x0, axis=0))
    return w / w.sum()


# ----------------------------------------------------------------------
# Step 1: axis variance cube (3, n_bins, n_bins)
# ----------------------------------------------------------------------

# Pairwise differences for all (i, j) are ``(3, T, B, B)`` — ~30 GB for a whole
# chromosome at 25 kb (T ≈ 90, B ≈ 4,000, float64).  Every statistic below
# reduces over traces independently per (i, j), so the tensor is built one
# block of rows ``i`` at a time and each block holds about this many bytes.
_BLOCK_BYTES = 256 * 2**20


def _coord_tensor(cd, chrom: str, device: str = "auto", *, with_cube: bool = False):
    """``(coords, bin_ids, trace_ids)`` with ``coords`` a ``(T, B, 3)`` tensor on ``device`` (and the numpy cube
    when ``with_cube``)."""
    import torch

    cube, bin_ids, trace_ids = _coord_cube_for_chrom(cd, chrom)
    dev = get_device(device)
    c = torch.as_tensor(cube, dtype=default_float_dtype(dev), device=dev)
    return (c, bin_ids, trace_ids, cube) if with_cube else (c, bin_ids, trace_ids)


def _row_blocks(c):
    """Yield ``(i0, i1)`` row ranges whose ``(3, T, i1 - i0, B)`` diff fits in ``_BLOCK_BYTES``."""
    T, B, _ = c.shape
    per_row = 3 * T * B * c.element_size()
    step = max(1, _BLOCK_BYTES // max(per_row, 1))
    for i0 in range(0, B, step):
        yield i0, min(i0 + step, B)


def _diff_rows(c, i0: int, i1: int):
    """``diff[a, t, i - i0, j] = c[t, i, a] - c[t, j, a]`` for rows ``i0 <= i < i1``; NaN where missing."""
    return (c[:, i0:i1].unsqueeze(2) - c.unsqueeze(1)).permute(3, 0, 1, 2)   # (3, T, b, B)


def axis_variance_cube(
    cd,
    chrom: str,
    device: str = "auto",
) -> dict:
    """Per-axis pairwise variance and count cubes of one chromosome, before filtering.

    Returns a dict with ``var``, ``count``, ``mean`` (all ``(3, B, B)``), ``bin_ids``, ``n_traces``, ``chrom``,
    ``axis_weight`` (:func:`axis_weight` of the same cube) and, for :func:`filter_normalize`, the ``(T, B, 3)``
    coordinate tensor on the torch device under ``"coords"``.  Pairwise differences are formed block by block, so
    memory stays near ``_BLOCK_BYTES`` whatever ``B``.
    """
    import torch

    c, bin_ids, trace_ids, cube = _coord_tensor(cd, chrom, device, with_cube=True)
    B = c.shape[1]
    var = torch.empty((3, B, B), dtype=c.dtype, device=c.device)
    mean = torch.empty_like(var)
    count = torch.empty((3, B, B), dtype=torch.int64, device=c.device)
    for i0, i1 in _row_blocks(c):
        diff = _diff_rows(c, i0, i1)
        valid = ~torch.isnan(diff)
        n = valid.sum(dim=1).to(torch.int64)                   # (3, b, B)

        # NaN-aware mean + variance along trace dim
        safe = torch.where(valid, diff, torch.zeros_like(diff))
        safe_count = n.clamp(min=1).to(diff.dtype)
        m = safe.sum(dim=1) / safe_count
        dev_sq = torch.where(valid, (diff - m.unsqueeze(1)) ** 2,
                             torch.zeros_like(diff))
        v = dev_sq.sum(dim=1) / safe_count

        no_obs = n == 0
        var[:, i0:i1] = torch.where(no_obs, torch.full_like(v, float("nan")), v)
        mean[:, i0:i1] = torch.where(no_obs, torch.full_like(m, float("nan")), m)
        count[:, i0:i1] = n

    return {
        "var": var.detach().cpu().numpy().astype(np.float64),
        "count": count.detach().cpu().numpy().astype(np.int64),
        "mean": mean.detach().cpu().numpy().astype(np.float64),
        "coords": c,                                    # stays on device
        "bin_ids": bin_ids,
        "n_traces": len(trace_ids),
        "chrom": chrom,
        "axis_weight": _axis_weight_cube(cube),
    }


# ----------------------------------------------------------------------
# Step 2: filter_normalize (2-pass LOWESS)
# ----------------------------------------------------------------------

def _bin_midpoints(bin_ids):
    """Return 1D array of midpoints (start+end)/2 for each bin."""
    return np.array([(s + e) * 0.5 for (s, e) in bin_ids], dtype=np.float64)


def _bin_starts(bin_ids):
    """Return 1D array of the loci's starts."""
    return np.array([s for (s, _) in bin_ids], dtype=np.float64)


def _genomic_distance_matrix(bin_ids):
    """``(n_bins, n_bins)`` matrix of genomic distances ``|start_i - start_j|``."""
    st = _bin_starts(bin_ids)
    return np.abs(st[:, None] - st[None, :])


def _not_zero(v: np.ndarray) -> np.ndarray:
    """``v`` with the values within :data:`ZERO_VAR_ATOL` of zero set to NaN (left out of a LOWESS fit)."""
    return np.where(np.abs(v) <= ZERO_VAR_ATOL, np.nan, v)


def _lowess_symmetric(values_upper: np.ndarray, d_flat: np.ndarray, iu, B: int, frac: float) -> np.ndarray:
    """LOWESS of ``log values`` on ``log d`` over the upper triangle, back-transformed, as a symmetric ``(B, B)``
    matrix with a NaN diagonal; pairs left out of the fit are NaN."""
    fit = lowess_log_log(d_flat, _not_zero(values_upper), frac=frac)
    m = np.full((B, B), np.nan)
    m[iu] = fit
    m.T[iu] = fit
    return m


def filter_normalize(
    cube: dict,
    k_sigma: float = 4.0,
    frac: float = 0.1,
) -> dict:
    """ArcFISH's outlier filter and normalisation by genomic distance (module docstring, step 2).

    Rebuilds the ``(3, n_traces, n_bins, n_bins)`` pairwise differences block by block from ``cube['coords']``.
    Output (numpy, on CPU): ``var`` (filtered variance), ``count`` (traces left per pair), ``norm_var``,
    ``expected``, ``raw_var``, ``genomic_distance``, plus the input's other keys; the device tensor under
    ``"coords"`` is dropped.
    """
    import torch

    c: "torch.Tensor" = cube["coords"]           # (T, B, 3) on device
    B = c.shape[1]
    n_axes = 3
    bin_ids = cube["bin_ids"]
    d1d = _genomic_distance_matrix(bin_ids)      # (B, B) numpy
    iu = np.triu_indices(B, k=1)
    d_flat = d1d[iu]

    # -------- Pass 1: median difference, raw variance (median squared deviation), stratified s.d. --------
    med = torch.empty((n_axes, B, B), dtype=c.dtype, device=c.device)
    raw_var = torch.empty_like(med)
    for i0, i1 in _row_blocks(c):
        diff = _diff_rows(c, i0, i1)
        m = _nanmedian_along_dim(diff, 1, keepdim=True)          # (3, 1, b, B)
        med[:, i0:i1] = m[:, 0]
        raw_var[:, i0:i1] = _nanmedian_along_dim((diff - m) ** 2, 1, keepdim=False)
        del diff, m

    raw_var_np = raw_var.detach().cpu().numpy().astype(np.float64)
    for a in range(n_axes):
        np.fill_diagonal(raw_var_np[a], np.nan)
    strata_std = np.stack([np.sqrt(_lowess_symmetric(raw_var_np[a][iu], d_flat, iu, B, frac))
                           for a in range(n_axes)])
    threshold = k_sigma * torch.as_tensor(strata_std, dtype=c.dtype, device=c.device)   # (3, B, B)

    # -------- Pass 2: outliers removed; count, variance (mean squared deviation from the mean) --------
    filtered_var = torch.empty_like(med)
    count = torch.empty((n_axes, B, B), dtype=torch.int64, device=c.device)
    for i0, i1 in _row_blocks(c):
        diff = _diff_rows(c, i0, i1)
        outlier = (diff - med[:, i0:i1].unsqueeze(1)).abs() > threshold[:, i0:i1].unsqueeze(1)
        diff = torch.where(outlier, torch.full_like(diff, float("nan")), diff)

        valid = ~torch.isnan(diff)
        n = valid.sum(dim=1).to(torch.int64)                       # (3, b, B)
        safe_count = n.clamp(min=1).to(diff.dtype)
        safe = torch.where(valid, diff, torch.zeros_like(diff))
        m = safe.sum(dim=1) / safe_count                           # (3, b, B)
        dev_sq = torch.where(valid, (diff - m.unsqueeze(1)) ** 2,
                             torch.zeros_like(diff))
        v = dev_sq.sum(dim=1) / safe_count
        filtered_var[:, i0:i1] = torch.where(n == 0, torch.full_like(v, float("nan")), v)
        count[:, i0:i1] = n
        del diff, outlier, valid, safe, dev_sq

    fvar_np = filtered_var.detach().cpu().numpy().astype(np.float64)
    count_np = count.detach().cpu().numpy().astype(np.int64)
    return _normalise(cube, fvar_np, count_np, raw_var_np, d1d, iu, frac)


def _normalise(cube: dict, fvar: np.ndarray, count: np.ndarray, raw_var: np.ndarray, d1d: np.ndarray, iu,
               frac: float) -> dict:
    """The second LOWESS (expected variance by genomic distance) and the output dict of :func:`filter_normalize`
    (shared with the streaming path)."""
    B = d1d.shape[0]
    expected = np.stack([_lowess_symmetric(fvar[a][iu], d1d[iu], iu, B, frac) for a in range(3)])
    with np.errstate(invalid="ignore", divide="ignore"):
        norm_var = fvar / expected
    for a in range(3):
        np.fill_diagonal(norm_var[a], 0.0)
    out = dict(cube)
    out["var"] = fvar
    out["count"] = count
    out["raw_var"] = raw_var
    out["expected"] = expected
    out["norm_var"] = norm_var
    out["genomic_distance"] = d1d
    out.pop("coords", None)       # the device tensor is not needed downstream
    return out


def _nanmedian_along_dim(t, dim: int, keepdim: bool = False):
    """NaN-aware median along ``dim`` of a torch tensor: the middle value, or the mean of the two middle values for
    an even count (as ``numpy.nanmedian``); NaN where all are NaN.  ``torch.nanmedian`` returns the lower of the two
    middle values, and of ``-t`` minus the upper one, so the median is their mean — the same order statistics as a
    sort, at the cost of two selections."""
    import torch

    lo = torch.nanmedian(t, dim=dim, keepdim=keepdim).values
    hi = -torch.nanmedian(-t, dim=dim, keepdim=keepdim).values
    return (lo + hi) / 2


# ----------------------------------------------------------------------
# Step 3: axis weights for ACAT
# ----------------------------------------------------------------------

def axis_weight(
    cd,
    chrom: Optional[str] = None,
    device: str = "auto",
) -> np.ndarray:
    """ArcFISH's axis weights of a chromosome (module docstring, step 3): per axis, each trace centred at its mean
    over the loci, the mean square of each locus over the traces, ``1 / median`` over the loci, normalised to sum 1.

    ``chrom=None`` averages the weights of every chromosome.  ``device`` is accepted for compatibility (numpy).
    """
    if chrom is None:
        if getattr(cd, "backed", False):
            chroms = [str(c) for c in cd.bins["chrom"].astype(str).unique()]
        else:
            chroms = [str(c) for c in pd.unique(cd.spots["chrom"].astype(str))]
        return np.mean(np.stack([axis_weight(cd, chrom=c) for c in chroms]), axis=0)
    cube, _, _ = _coord_cube_for_chrom(cd, chrom)
    return _axis_weight_cube(cube)


def bh_fdr(pvals: np.ndarray) -> np.ndarray:
    """Benjamini–Hochberg adjusted p-values of the finite entries (NaN elsewhere), computed as
    ``statsmodels.stats.multitest.multipletests(method="fdr_bh")`` does, so that results agree to the last bit."""
    p = np.asarray(pvals, dtype=np.float64)
    out = np.full_like(p, np.nan)
    finite = np.isfinite(p)
    if not finite.any():
        return out
    pf = p[finite]
    order = np.argsort(pf)
    ranked = pf[order]
    n = ranked.size
    ecdf = np.arange(1, n + 1) / float(n)
    q = np.minimum.accumulate((ranked / ecdf)[::-1])[::-1]
    q[q > 1] = 1
    o = np.empty_like(pf)
    o[order] = q
    out[finite] = o
    return out


__all__ = [
    "axis_variance_cube",
    "filter_normalize",
    "axis_weight",
]
