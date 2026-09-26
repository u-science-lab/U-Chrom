"""ArcFISH-style axis-wise F-test loop caller (``AxisWiseF`` + ``LoopCaller``).

Independent implementation of the algorithm described in Yu et al. 2025
(ArcFISH); not derived from the GPL-3.0 ArcFISH source.

Pipeline
--------
1. Per-axis variance + counts → :func:`uchrom.fea.arc.axis_variance_cube`.
2. LOWESS-normalised variance → :func:`uchrom.fea.arc.filter_normalize`.
3. Axis weights for ACAT → :func:`uchrom.fea.arc.axis_weight`.
4. For each candidate bin pair ``(i, j)`` within ``[cut_lo, cut_up]`` 1D
   genomic distance:
     a. Compute a local background mean of normalised variance over a
        ring ``[inner_cut, outer_cut]`` around ``(i, j)``, *excluding* its
        own row/column.
     b. Per-axis F-statistic ``F_c = var_c[i,j] / denom_c``; left-tailed
        F-CDF gives ``p_c`` (loops have below-average variance).
     c. ACAT combine per-axis p-values with axis weights → per-pair p.
5. BH-FDR adjust; accept candidates with ``fdr < fdr_cutoff``.
6. Cluster accepted candidates within ``gap`` 1D distance; pick the
   lowest-p entry in each cluster as the "summit".
7. Optionally filter summits by raw ``pval_cutoff`` and minimum cluster
   size.

Result columns
--------------
``chrom1, start1, end1, chrom2, start2, end2, score (-log10 p), pval, fdr,
 summit_i, summit_j, cluster_size``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from uchrom.fea.arc import axis_variance_cube, filter_normalize, axis_weight
from uchrom.fea.arc import _coord_tensor, _diff_rows, _row_blocks
from uchrom.utils.stats import cauchy_combination


# ----------------------------------------------------------------------
# Parameters
# ----------------------------------------------------------------------

@dataclass
class LoopCallerParams:
    """Runtime parameters for :func:`call_loops_axiswise_f`.

    Defaults mirror ArcFISH's ``LoopCaller``.
    """

    cut_lo: float = 1e5            # min 1D size of a candidate loop
    cut_up: float = 1e6            # max 1D size of a candidate loop
    inner_cut: float = 2.5e4       # inner ring radius for local background
    outer_cut: float = 5e4         # outer ring radius for local background
    fdr_cutoff: float = 0.1
    pval_cutoff: float = 1e-5
    gap: float = 5e4               # 1D gap for clustering summit neighbours
    k_sigma: float = 4.0           # outlier k for LOWESS-based filter
    frac: float = 0.1              # LOWESS span
    min_cluster_size: int = 1

    def __post_init__(self):
        assert self.cut_lo < self.cut_up
        assert self.inner_cut < self.outer_cut


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _bh_fdr(pvals: np.ndarray) -> np.ndarray:
    """Benjamini–Hochberg FDR on a flat array of p-values.

    NaNs pass through as NaNs.  Returns q-values the same shape as input.
    """
    p = np.asarray(pvals, dtype=np.float64)
    out = np.full_like(p, np.nan)
    finite = np.isfinite(p)
    if not finite.any():
        return out
    pf = p[finite]
    n = pf.size
    order = np.argsort(pf)
    ranked = pf[order]
    q = ranked * n / (np.arange(n) + 1.0)
    # Enforce monotonicity (reverse cumulative min)
    q = np.minimum.accumulate(q[::-1])[::-1]
    q = np.clip(q, 0.0, 1.0)
    out_finite = np.empty_like(pf)
    out_finite[order] = q
    out[finite] = out_finite
    return out


def _ring_mask(B: int, inner_bins: int, outer_bins: int):
    """Boolean ``(B, B, B, B)`` ring mask for per-pair backgrounds.

    ``mask[i, j, a, b]`` is True if ``(a, b)`` lies in the 1D-distance
    ring of ``(i, j)`` excluding row ``i``, column ``j``, and
    ``(a, b) == (i, j)``.  This can be huge — we instead compute the
    background mean on the fly rather than materialising a 4D mask.
    """
    raise NotImplementedError("Handled inline in _background_mean_axis.")


def _background_ring(
    var_axis: np.ndarray,
    count_axis: np.ndarray,
    i: int,
    j: int,
    inner_bins: int,
    outer_bins: int,
):
    """Return ``(denom, total_count)`` for the ring around ``(i, j)``.

    ``denom`` is the count-weighted mean of ``var_axis`` over the ring
    ``[inner_bins, outer_bins]`` around ``(i, j)``, excluding row ``i``
    and column ``j``.  ``total_count`` is the sum of counts in the same
    ring — used as the ``df2`` for the F-test.  NaN-safe.
    """
    B = var_axis.shape[0]
    lo_i = max(0, i - outer_bins)
    hi_i = min(B, i + outer_bins + 1)
    in_lo_i = max(0, i - inner_bins)
    in_hi_i = min(B, i + inner_bins + 1)
    lo_j = max(0, j - outer_bins)
    hi_j = min(B, j + outer_bins + 1)
    in_lo_j = max(0, j - inner_bins)
    in_hi_j = min(B, j + inner_bins + 1)

    # Build a boolean mask of kept entries then sum (avoids the sum-of-
    # rectangles book-keeping and matches ArcFISH's `ij_background` logic).
    mask = np.zeros((B, B), dtype=bool)
    mask[lo_i:hi_i, lo_j:hi_j] = True
    mask[in_lo_i:in_hi_i, in_lo_j:in_hi_j] = False
    mask[i, :] = False
    mask[:, j] = False

    vals = var_axis[mask]
    cnts = count_axis[mask]
    finite = np.isfinite(vals) & (cnts > 0)
    if not finite.any():
        return np.nan, 0

    v = vals[finite]
    c = cnts[finite].astype(np.float64)
    total = c.sum()
    denom = float((c * v).sum() / total)
    return denom, float(total)


def _cluster_summits(
    triu_hits: np.ndarray,
    pvals: np.ndarray,
    d1d: np.ndarray,
    gap: float,
):
    """Cluster accepted candidates by 1D proximity; pick lowest-p summits.

    Parameters
    ----------
    triu_hits : bool array (n_hit,)
        Already filtered upper-triangle candidates.
    pvals : float array (n_hit,)
        Raw p-values for those candidates.
    d1d : float array (n_hit, n_hit)
        Pairwise 1D genomic distance between candidate centres in bp,
        computed upstream.
    gap : float
        Max separation for two candidates to be in the same cluster.

    Returns
    -------
    clusters : list[list[int]]
        Index lists per cluster (into the ``triu_hits`` / ``pvals`` arrays).
    summits : list[int]
        Index into ``pvals`` of the lowest-p entry per cluster.
    """
    n = pvals.size
    if n == 0:
        return [], []

    # Union-Find via simple BFS on adjacency where nodes ≤ gap apart
    adj = [set() for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if d1d[i, j] <= gap:
                adj[i].add(j)
                adj[j].add(i)

    seen = [False] * n
    clusters = []
    for i in range(n):
        if seen[i]:
            continue
        stack = [i]
        comp = []
        while stack:
            k = stack.pop()
            if seen[k]:
                continue
            seen[k] = True
            comp.append(k)
            stack.extend(adj[k])
        clusters.append(comp)

    summits = []
    for comp in clusters:
        best = comp[int(np.argmin(pvals[comp]))]
        summits.append(best)
    return clusters, summits


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

def call_loops_axiswise_f(
    cd,
    chrom: str,
    params: Optional[LoopCallerParams] = None,
    device: str = "auto",
    store: bool = True,
    result_key: str = "loops",
    verbose: bool = False,
) -> pd.DataFrame:
    """ArcFISH-style loop caller on a single chromosome.

    Parameters
    ----------
    cd : :class:`uchrom.ChromData`
        Tracing data.  Must contain ``trace_id`` in ``spots`` and positive
        coordinates.
    chrom : str
        Chromosome name — matched against ``cd.spots['chrom']``.
    params : LoopCallerParams, optional
        Override any default.
    device : str
        ``'auto' | 'cpu' | 'cuda' | 'mps'`` — passed to GPU-friendly
        preprocessing.
    store : bool
        If True, also write the result DataFrame into
        ``cd.results[result_key]``.
    result_key : str
        Key under which to store the result (default ``'loops'``).

    Returns
    -------
    DataFrame
        One row per called loop summit.
    """
    params = params or LoopCallerParams()
    from scipy.stats import f as _f_dist

    # Step 1 + 2: variances + LOWESS normalisation
    if verbose:
        print(f"[loop/{chrom}] computing axis variance cube...")
    cube = axis_variance_cube(cd, chrom=chrom, device=device)
    if verbose:
        print(f"[loop/{chrom}] {cube['n_traces']} traces, "
              f"{len(cube['bin_ids'])} bins; normalising...")
    cube = filter_normalize(cube, k_sigma=params.k_sigma, frac=params.frac)

    bin_ids = cube["bin_ids"]
    B = len(bin_ids)
    norm_var = cube["norm_var"]                     # (3, B, B)
    count = cube["count"]                           # (3, B, B)
    d1d = cube["genomic_distance"]                  # (B, B)

    # Step 3: axis weights
    w = axis_weight(cd, chrom=chrom, device=device)
    if verbose:
        print(f"[loop/{chrom}] axis weights x={w[0]:.3f}, y={w[1]:.3f}, z={w[2]:.3f}")

    # Figure out integer bin widths for the background ring
    med_bin_size = float(np.median([e - s for s, e in bin_ids]))
    inner_bins = max(1, int(round(params.inner_cut / med_bin_size)))
    outer_bins = max(inner_bins + 1, int(round(params.outer_cut / med_bin_size)))
    if verbose:
        print(f"[loop/{chrom}] median bin size {med_bin_size:.0f} bp, "
              f"ring bins [{inner_bins}, {outer_bins}]")

    # Candidate mask: upper triangle with 1D distance in [cut_lo, cut_up]
    cand = (d1d >= params.cut_lo) & (d1d <= params.cut_up)
    cand = np.triu(cand, k=1)
    cand_idx = np.argwhere(cand)
    if cand_idx.size == 0:
        if verbose:
            print(f"[loop/{chrom}] no candidates in [{params.cut_lo}, {params.cut_up}]")
        empty = _empty_result()
        if store:
            _store_result(cd, result_key, empty)
        return empty

    # Step 4: per-axis F-test
    if verbose:
        print(f"[loop/{chrom}] {len(cand_idx)} candidates; running F-test...")

    # Work in log-p space to avoid floor-clipping ties at the minimum p.
    # scipy's F.logcdf handles extreme F values without underflow, so a
    # loop with F ≈ 1e-4 and a non-loop pair with F ≈ 0.2 stay
    # distinguishable after ACAT combination, which matters for summit
    # tie-breaking later.
    per_axis_logp = np.full((3, len(cand_idx)), 0.0, dtype=np.float64)
    per_axis_F = np.full((3, len(cand_idx)), np.nan, dtype=np.float64)
    for k, (i, j) in enumerate(cand_idx):
        for ax in range(3):
            vij = norm_var[ax, i, j]
            cij = count[ax, i, j]
            if not np.isfinite(vij) or cij <= 0:
                continue
            denom, bg_count = _background_ring(
                norm_var[ax], count[ax], int(i), int(j),
                inner_bins, outer_bins,
            )
            if not np.isfinite(denom) or denom <= 0 or bg_count <= 3:
                continue
            F = vij / denom
            logp = _f_dist.logcdf(F, dfn=max(int(cij), 1), dfd=max(bg_count, 1))
            per_axis_F[ax, k] = F
            per_axis_logp[ax, k] = logp

    # Convert log-p back to p for ACAT (clip only here; ACAT needs raw p).
    # A small floor (1e-300) still limits the dynamic range but that is
    # enough precision for ACAT — the F-based ``score`` below breaks any
    # remaining ties when picking the summit of a cluster.
    per_axis_logp = np.where(np.isfinite(per_axis_logp), per_axis_logp, 0.0)
    per_axis_p = np.clip(np.exp(per_axis_logp), 1e-300, 1 - 1e-15)

    # Step 4c: ACAT combine
    combined = cauchy_combination(per_axis_p.T, weights=w, axis=1)
    # cauchy_combination returns upper tail (1 - CDF); for this left-tail
    # setup that's our raw p-value.
    pvals = np.clip(np.asarray(combined), 1e-300, 1.0)

    # Step 5: BH-FDR
    fdr = _bh_fdr(pvals)
    accept = (fdr < params.fdr_cutoff)

    if not accept.any():
        if verbose:
            print(f"[loop/{chrom}] no candidates pass FDR < {params.fdr_cutoff}")
        empty = _empty_result()
        if store:
            _store_result(cd, result_key, empty)
        return empty

    # Step 6: cluster accepted hits by 1D distance between midpoints.
    # We order candidates inside a cluster by a full-precision log-p
    # "score" (weighted sum of per-axis log-p) so that p-value ties at
    # the numerical floor are broken by the actual F-statistic strength.
    hits_idx = cand_idx[accept]
    hit_pvals = pvals[accept]
    w_arr = np.asarray(w).reshape(3, 1)
    hit_score = (per_axis_logp * w_arr).sum(axis=0)[accept]   # smaller = better
    mids_i = np.array([(bin_ids[i][0] + bin_ids[i][1]) * 0.5 for i in hits_idx[:, 0]])
    mids_j = np.array([(bin_ids[j][0] + bin_ids[j][1]) * 0.5 for j in hits_idx[:, 1]])
    di = np.abs(mids_i[:, None] - mids_i[None, :])
    dj = np.abs(mids_j[:, None] - mids_j[None, :])
    d1d_hits = np.maximum(di, dj)
    clusters, summits = _cluster_summits(accept, hit_score, d1d_hits, params.gap)

    # Step 7: pseudo-contact frequency filter
    # Build the (n_traces, n_bins, n_bins) 3D pdist matrix.  Uses the same
    # coord cube as filter_normalize — compute once, store on CPU.
    freq_mat = _pseudo_contact_frequency(cd, chrom, bin_ids, device=device)

    # Step 8: final filter — p-value + pseudo-contact frequency
    rows = []
    accept_idx_in_cand = np.where(accept)[0]
    for comp, summit in zip(clusters, summits):
        if len(comp) < params.min_cluster_size:
            continue
        i_b, j_b = hits_idx[summit]
        p_summit = hit_pvals[summit]
        if p_summit >= params.pval_cutoff:
            continue
        # Pseudo-contact frequency rule (ArcFISH "summit"):
        #   singleton cluster (== 1 triu entry) → freq > 1/2
        #   larger cluster                     → freq > 1/3
        is_singleton = len(comp) == 1
        freq_thresh = 0.5 if is_singleton else (1.0 / 3.0)
        f = freq_mat[int(i_b), int(j_b)]
        if not (np.isfinite(f) and f > freq_thresh):
            continue

        s1, e1 = bin_ids[i_b]
        s2, e2 = bin_ids[j_b]
        rows.append({
            "chrom1": chrom,
            "start1": int(s1),
            "end1": int(e1),
            "chrom2": chrom,
            "start2": int(s2),
            "end2": int(e2),
            "score": float(-np.log10(max(p_summit, 1e-300))),
            "pval": float(p_summit),
            "fdr": float(fdr[accept_idx_in_cand[summit]]),
            "cluster_size": int(len(comp)),
            "contact_freq": float(f),
            "summit_i": int(i_b),
            "summit_j": int(j_b),
        })

    df_out = pd.DataFrame(rows)
    if df_out.empty:
        df_out = _empty_result()

    if store:
        _store_result(cd, result_key, df_out)

    return df_out


def _store_result(cd, key: str, df: pd.DataFrame):
    """Assign ``df`` into ``cd.results[key]``, creating ``cd.results`` if needed."""
    results = getattr(cd, "results", None)
    if results is None:
        cd.results = {}
        results = cd.results
    results[key] = df


def _pseudo_contact_frequency(cd, chrom, bin_ids, device="auto"):
    """Fraction of traces whose 3D pairwise distance falls under a
    data-driven "contact" cutoff.

    Replicates ArcFISH's ``AxisWiseF.append_summit`` frequency rule:
    the cutoff is the NaN-mean pairwise distance at 1D separation
    equal to one bin width; ``freq_mat[i, j]`` is the fraction of
    traces where the (i, j) 3D distance is below that cutoff,
    conditional on both endpoints being observed.
    """
    import torch

    c, _, _ = _coord_tensor(cd, chrom, device)
    B = len(bin_ids)
    if c.shape[1] != B:
        return np.ones((B, B))  # defensive

    # 1D distance between bins in bp
    mids = np.array([(s + e) * 0.5 for (s, e) in bin_ids])
    d1d = np.abs(mids[:, None] - mids[None, :])
    med_bin_size = float(np.median([e - s for s, e in bin_ids]))
    # ArcFISH uses |d1d[i] - d1d[j]| == 25e3 (one bin).  Generalise to
    # a small tolerance around the median bin size.
    tol = max(1.0, 0.1 * med_bin_size)
    d1sel = np.abs(d1d - med_bin_size) <= tol

    if d1sel.sum() == 0:
        return np.ones((B, B))

    # (T, B, B) 3D pdist, one block of rows at a time: the cutoff (NaN-mean
    # over the one-bin pairs) first, then the per-pair contact fraction.
    def pdist_rows(i0, i1):
        diff = _diff_rows(c, i0, i1)                            # (3, T, b, B)
        return torch.sqrt((diff ** 2).sum(dim=0)).detach().cpu().numpy().astype(np.float64)

    total, n_obs = 0.0, 0
    for i0, i1 in _row_blocks(c):
        vals = pdist_rows(i0, i1)[:, d1sel[i0:i1]]
        total += float(np.nansum(vals))
        n_obs += int(np.sum(~np.isnan(vals)))
    cutoff = total / n_obs if n_obs else float("nan")
    if not np.isfinite(cutoff) or cutoff <= 0:
        return np.ones((B, B))

    freq = np.empty((B, B), dtype=np.float64)
    for i0, i1 in _row_blocks(c):
        pd_rows = pdist_rows(i0, i1)
        with np.errstate(invalid="ignore"):
            n_contact = np.nansum(pd_rows < cutoff, axis=0)
            n_valid = np.sum(~np.isnan(pd_rows), axis=0)
            freq[i0:i1] = np.where(n_valid > 0, n_contact / n_valid, 0.0)
    return freq


def _empty_result() -> pd.DataFrame:
    return pd.DataFrame({
        "chrom1": pd.Series(dtype=str),
        "start1": pd.Series(dtype="int64"),
        "end1":   pd.Series(dtype="int64"),
        "chrom2": pd.Series(dtype=str),
        "start2": pd.Series(dtype="int64"),
        "end2":   pd.Series(dtype="int64"),
        "score":  pd.Series(dtype="float64"),
        "pval":   pd.Series(dtype="float64"),
        "fdr":    pd.Series(dtype="float64"),
        "cluster_size": pd.Series(dtype="int64"),
        "summit_i": pd.Series(dtype="int64"),
        "summit_j": pd.Series(dtype="int64"),
    })


__all__ = [
    "LoopCallerParams",
    "call_loops_axiswise_f",
]
