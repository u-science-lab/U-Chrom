"""ArcFISH-style axis-wise preprocessing for chromatin tracing data.

References
----------
Yu H. *et al.* *Accurate and robust 3D genome feature discovery from
multiplexed DNA FISH*, bioRxiv 2025.11.26.690837v1.

Independent implementation in :mod:`uchrom` — not derived from the GPL-3.0
ArcFISH source.

Pipeline (per chromosome)
-------------------------
1. ``axis_variance_cube``
   Builds ``(3, n_bins, n_bins)`` per-axis pairwise variance + count cubes
   from ``ChromData`` spots.  Each trace contributes a rank-1 outer
   difference for each axis; aggregation is NaN-aware.
2. ``filter_normalize``
   Two-pass LOWESS stratification on log(1D genomic distance):
     - first pass: flag entries whose per-pair squared deviation is more
       than ``k_sigma`` × stratified std as outliers and NaN them;
     - second pass: refit LOWESS on the cleaned variances to give each
       entry a genome-distance-matched expectation, then normalise.
3. ``axis_weight``
   Returns a 3-vector of weights (sum 1) inversely proportional to the
   per-axis trace-variance median — the exact weighting used by the
   ACAT combination step in the loop / tad / comp callers.

All tensor-heavy computation runs on a user-selected torch device
(``'auto' | 'cpu' | 'cuda' | 'mps'``).  LOWESS stays on CPU via
``statsmodels`` because it's a non-vectorised kernel smoother whose
input size is ``O(n_bins²)`` (typically ≤ 10 k).
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from uchrom.utils import get_device, lowess_log_log
from uchrom.utils.stats import default_float_dtype


# ----------------------------------------------------------------------
# Coordinate cube: (n_traces, n_bins, 3) with NaN padding
# ----------------------------------------------------------------------

def _coord_cube_for_chrom(cd, chrom):
    """Return ``(coords_cube, bin_ids, trace_ids)`` for one chromosome.

    ``coords_cube[t, i, :]`` is the (x, y, z) of trace ``t`` at bin ``i``,
    NaN if the trace missed that bin.  Bins are sorted by ``start``.
    """
    df = cd.spots.copy()
    df["x"] = cd.coords[:, 0]
    df["y"] = cd.coords[:, 1]
    df["z"] = cd.coords[:, 2]
    df = df[df["chrom"].astype(str) == str(chrom)]
    if df.empty:
        raise ValueError(f"No spots found for chromosome {chrom}")

    # Coerce start/end to int to avoid float-keyed lookups
    df = df.assign(
        start=df["start"].astype(np.int64),
        end=df["end"].astype(np.int64),
    )

    bins = (
        df[["start", "end"]]
        .drop_duplicates()
        .sort_values("start", kind="mergesort")
        .reset_index(drop=True)
    )
    bin_keys = [(int(s), int(e)) for s, e in zip(bins["start"], bins["end"])]
    bin_to_idx = {k: i for i, k in enumerate(bin_keys)}
    n_bins = len(bin_keys)

    trace_ids = list(df["trace_id"].unique())
    tid_to_idx = {t: i for i, t in enumerate(trace_ids)}
    n_traces = len(trace_ids)

    cube = np.full((n_traces, n_bins, 3), np.nan, dtype=np.float64)
    ti = np.asarray(
        [tid_to_idx[t] for t in df["trace_id"]], dtype=np.int64
    )
    bi = np.asarray(
        [bin_to_idx[(int(s), int(e))] for s, e in zip(df["start"], df["end"])],
        dtype=np.int64,
    )
    cube[ti, bi, 0] = df["x"].to_numpy()
    cube[ti, bi, 1] = df["y"].to_numpy()
    cube[ti, bi, 2] = df["z"].to_numpy()
    return cube, bin_keys, trace_ids


# ----------------------------------------------------------------------
# Step 1: axis variance cube (3, n_bins, n_bins)
# ----------------------------------------------------------------------

def _pairwise_diff_tensor(cd, chrom: str, device: str = "auto"):
    """Return the full ``(3, n_traces, n_bins, n_bins)`` pairwise difference.

    ``diff[c, t, i, j] = coord_c[t, j] - coord_c[t, i]`` with NaN where a
    trace is missing a bin.  Kept on ``device``; caller is responsible for
    moving to CPU if needed.
    """
    import torch

    cube, bin_ids, trace_ids = _coord_cube_for_chrom(cd, chrom)
    dev = get_device(device)
    dtype = default_float_dtype(dev)

    c = torch.as_tensor(cube, dtype=dtype, device=dev)   # (T, B, 3)
    diff = c.unsqueeze(2) - c.unsqueeze(1)               # (T, B, B, 3)
    diff = diff.permute(3, 0, 1, 2).contiguous()         # (3, T, B, B)
    return diff, bin_ids, trace_ids


def axis_variance_cube(
    cd,
    chrom: str,
    device: str = "auto",
) -> dict:
    """Compute per-axis pairwise variance + sample-count cubes.

    Returns a dict with ``var``, ``count``, ``mean`` (all ``(3, B, B)``)
    plus ``bin_ids``, ``n_traces``, ``chrom``, and — for downstream
    :func:`filter_normalize` — the full ``(3, T, B, B)`` pairwise diff
    tensor on the GPU device under key ``"diff"``.
    """
    import torch

    diff, bin_ids, trace_ids = _pairwise_diff_tensor(cd, chrom, device)
    valid = ~torch.isnan(diff)
    count = valid.sum(dim=1).to(torch.int64)            # (3, B, B)

    # NaN-aware mean + variance along trace dim
    safe = torch.where(valid, diff, torch.zeros_like(diff))
    safe_count = count.clamp(min=1).to(diff.dtype)
    mean = safe.sum(dim=1) / safe_count
    dev_sq = torch.where(valid, (diff - mean.unsqueeze(1)) ** 2,
                         torch.zeros_like(diff))
    var = dev_sq.sum(dim=1) / safe_count                # (3, B, B)

    no_obs = count == 0
    var = torch.where(no_obs, torch.full_like(var, float("nan")), var)
    mean = torch.where(no_obs, torch.full_like(mean, float("nan")), mean)

    return {
        "var": var.detach().cpu().numpy().astype(np.float64),
        "count": count.detach().cpu().numpy().astype(np.int64),
        "mean": mean.detach().cpu().numpy().astype(np.float64),
        "diff": diff,                                   # stays on device
        "bin_ids": bin_ids,
        "n_traces": len(trace_ids),
        "chrom": chrom,
    }


# ----------------------------------------------------------------------
# Step 2: filter_normalize (2-pass LOWESS)
# ----------------------------------------------------------------------

def _bin_midpoints(bin_ids):
    """Return 1D array of midpoints (start+end)/2 for each bin."""
    return np.array([(s + e) * 0.5 for (s, e) in bin_ids], dtype=np.float64)


def _genomic_distance_matrix(bin_ids):
    """``(n_bins, n_bins)`` matrix of |midpoint_i - midpoint_j|."""
    mids = _bin_midpoints(bin_ids)
    return np.abs(mids[:, None] - mids[None, :])


def filter_normalize(
    cube: dict,
    k_sigma: float = 4.0,
    frac: float = 0.1,
) -> dict:
    """ArcFISH-style per-trace LOWESS filter + normalise.

    Operates on the full ``(3, n_traces, n_bins, n_bins)`` pairwise-diff
    tensor kept on the GPU (under ``cube['diff']``).  Two passes:

    1. Per-pair ``raw_var = nanmedian(trace_diff²)`` → LOWESS over
       ``log(genomic_distance)`` → ``strata_std``.  Individual trace
       observations where ``|diff - median(diff)| > k_sigma × strata_std``
       are NaN'd in-place in the 4D tensor.
    2. After filtering, per-pair ``filtered_var = nanmean((diff - mean)²)``
       and per-pair ``count = n_valid`` recomputed.  LOWESS again over
       log(d1d) → expected; normalised variance = filtered / expected.

    Output (numpy, on CPU): ``var``, ``count`` (refreshed after filter),
    ``norm_var``, ``expected``, ``raw_var``, ``genomic_distance``.  The
    original 4D tensor under ``"diff"`` is consumed (may be modified).
    """
    import torch

    diff: "torch.Tensor" = cube["diff"]          # (3, T, B, B) on device
    n_axes, T, B, _ = diff.shape
    bin_ids = cube["bin_ids"]
    d1d = _genomic_distance_matrix(bin_ids)      # (B, B) numpy
    iu = np.triu_indices(B, k=1)
    d_flat = d1d[iu]

    # -------- Pass 1: raw_var via nanmedian, LOWESS, outlier mask --------
    # arr_dev[c, n, i, j] centred deviation from trace median.
    # raw_var[c, i, j] = nanmedian_n((arr - nanmedian_n arr)²)
    dev = diff - _nanmedian_along_dim(diff, 1, keepdim=True)   # (3, T, B, B)
    sq = dev ** 2
    # nanmedian along trace axis
    raw_var = _nanmedian_along_dim(sq, 1, keepdim=False)       # (3, B, B)

    # Replace near-zero → NaN
    raw_var = torch.where(raw_var < 1e-30,
                          torch.full_like(raw_var, float("nan")),
                          raw_var)

    # LOWESS log(raw_var) ~ log(d1d)
    raw_var_np = raw_var.detach().cpu().numpy().astype(np.float64)
    strata_std = np.full_like(raw_var_np, np.nan)
    for a in range(n_axes):
        v_flat = raw_var_np[a][iu]
        fit = lowess_log_log(d_flat, v_flat, frac=frac)
        std_flat = np.sqrt(np.clip(fit, 1e-30, None))
        axm = np.full((B, B), np.nan)
        axm[iu] = std_flat
        axm.T[iu] = std_flat
        strata_std[a] = axm

    # Per-trace outlier mask: |diff - median_t(diff)| > k_sigma * strata_std
    strata_std_t = torch.as_tensor(
        strata_std, dtype=diff.dtype, device=diff.device
    )  # (3, B, B)
    # abs_dev[c, n, i, j]
    abs_dev = (diff - _nanmedian_along_dim(diff, 1, keepdim=True)).abs()
    threshold = (k_sigma * strata_std_t).unsqueeze(1)  # (3, 1, B, B)
    outlier = abs_dev > threshold
    # NaN out outliers in-place
    diff = torch.where(outlier, torch.full_like(diff, float("nan")), diff)

    # -------- Pass 2: filtered_var via nanmean squared deviation --------
    valid = ~torch.isnan(diff)
    count = valid.sum(dim=1).to(torch.int64)                   # (3, B, B)
    safe_count = count.clamp(min=1).to(diff.dtype)
    safe = torch.where(valid, diff, torch.zeros_like(diff))
    mean = safe.sum(dim=1) / safe_count                        # (3, B, B)
    dev_sq = torch.where(valid, (diff - mean.unsqueeze(1)) ** 2,
                         torch.zeros_like(diff))
    filtered_var = dev_sq.sum(dim=1) / safe_count              # (3, B, B)
    filtered_var = torch.where(count == 0,
                               torch.full_like(filtered_var, float("nan")),
                               filtered_var)

    fvar_np = filtered_var.detach().cpu().numpy().astype(np.float64)
    count_np = count.detach().cpu().numpy().astype(np.int64)

    expected = np.full_like(fvar_np, np.nan)
    norm_var = np.full_like(fvar_np, np.nan)
    for a in range(n_axes):
        v_flat = fvar_np[a][iu]
        v_flat_ok = np.where(v_flat > 1e-30, v_flat, np.nan)
        fit = lowess_log_log(d_flat, v_flat_ok, frac=frac)
        exp_axis = np.full((B, B), np.nan)
        exp_axis[iu] = fit
        exp_axis.T[iu] = fit
        expected[a] = exp_axis
        with np.errstate(invalid="ignore", divide="ignore"):
            norm_axis = np.where(exp_axis > 0, fvar_np[a] / exp_axis, np.nan)
        norm_var[a] = norm_axis
        # Zero the diagonal for cleanliness
        np.fill_diagonal(norm_var[a], 0.0)

    out = dict(cube)
    out["var"] = fvar_np
    out["count"] = count_np
    out["raw_var"] = raw_var_np
    out["expected"] = expected
    out["norm_var"] = norm_var
    out["genomic_distance"] = d1d
    # Drop large 4D tensor now — no longer needed downstream
    out.pop("diff", None)
    return out


def _nanmedian_along_dim(t, dim: int, keepdim: bool = False):
    """NaN-aware median along a single dim for a torch tensor.

    Uses ``torch.nanmedian`` (available) but falls back to numpy if on
    MPS where nanmedian kernels are spotty.
    """
    import torch

    try:
        return torch.nanmedian(t, dim=dim, keepdim=keepdim).values
    except Exception:
        arr = t.detach().cpu().numpy()
        med = np.nanmedian(arr, axis=dim, keepdims=keepdim)
        return torch.as_tensor(med, dtype=t.dtype, device=t.device)


# ----------------------------------------------------------------------
# Step 3: axis weights for ACAT
# ----------------------------------------------------------------------

def axis_weight(
    cd,
    chrom: Optional[str] = None,
    device: str = "auto",
) -> np.ndarray:
    """Compute per-axis weights ``w ∝ 1 / median(trace_variance)``.

    For each axis we centre every trace at its own mean (bins with NaN
    excluded) and take the median across traces of each trace's variance.
    The inverse of that median is the axis weight, normalised to sum 1.
    Consistent with ArcFISH's ``axis_weight`` routine.
    """
    import torch

    df = cd.spots.copy()
    df["x"] = cd.coords[:, 0]
    df["y"] = cd.coords[:, 1]
    df["z"] = cd.coords[:, 2]
    if chrom is not None:
        df = df[df["chrom"].astype(str) == str(chrom)]
    if df.empty:
        raise ValueError("No spots found for the given chromosome filter.")

    # Build (n_traces, n_bins, 3) cube — reuse the coord cube path
    if chrom is not None:
        cube, _, _ = _coord_cube_for_chrom(cd, chrom)
    else:
        # All spots; fabricate a dummy chrom to reuse the helper
        chroms = df["chrom"].unique()
        all_cubes = []
        for c in chroms:
            sub_cube, _, _ = _coord_cube_for_chrom(cd, c)
            # Transform to axis-first: (3, T, B)
            all_cubes.append(sub_cube.transpose(2, 0, 1))
        # Stack per-axis, concatenating traces across chromosomes is wrong
        # (traces are per-chromosome).  Compute per-axis median-of-variances
        # per chrom then average.  Simplest approach: operate per-chrom.
        weights_accum = []
        for c in chroms:
            w_c = axis_weight(cd, chrom=str(c), device=device)
            weights_accum.append(w_c)
        return np.mean(np.stack(weights_accum, axis=0), axis=0)

    dev = get_device(device)
    dtype = default_float_dtype(dev)
    c = torch.as_tensor(cube, dtype=dtype, device=dev)       # (T, B, 3)
    valid = ~torch.isnan(c)
    count = valid.sum(dim=1, keepdim=True).clamp(min=1).to(dtype)   # (T, 1, 3)
    safe = torch.where(valid, c, torch.zeros_like(c))
    mean = safe.sum(dim=1, keepdim=True) / count            # (T, 1, 3)
    centred = torch.where(valid, c - mean, torch.zeros_like(c))
    # Variance per trace per axis: mean over valid bins
    trace_var = (centred ** 2).sum(dim=1) / count.squeeze(1)  # (T, 3)

    # Median across traces
    per_axis_median = trace_var.nanmedian(dim=0).values       # (3,)
    w = 1.0 / per_axis_median.clamp(min=1e-30)
    w = w / w.sum()
    return w.detach().cpu().numpy().astype(np.float64)


__all__ = [
    "axis_variance_cube",
    "filter_normalize",
    "axis_weight",
]
