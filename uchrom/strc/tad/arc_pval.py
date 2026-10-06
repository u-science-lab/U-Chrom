"""ArcFISH-style TAD caller based on intra/inter-domain variance F-test.

Independent implementation of Yu et al. 2025 (*ArcFISH*,
bioRxiv 2025.11.26.690837v1) ``TADCaller.by_pval``.  Not derived from
the GPL-3.0 upstream source.

Algorithm (per chromosome)
--------------------------
1. Build the per-axis normalised variance ``norm_var[c, i, j]`` via
   :func:`uchrom.fea.arc.filter_normalize` (same preprocessing as the
   loop caller).
2. For each candidate boundary position ``b`` with a window of size
   ``window_bp`` (bp), split the window into a left segment
   ``L = [b - w/2, b)`` and a right segment ``R = (b, b + w/2]``.  The
   intra-domain set is the pairs within ``L`` or within ``R``; the
   inter-domain set is the pairs that cross ``b``.
3. Per-axis F-test on the count-weighted intra-/inter-mean variance:
   ``F_c = intra_mean_c / inter_mean_c``.  If ``b`` is a true TAD
   boundary, intra-domain distances are tighter than inter-domain →
   ``F`` is small → left-tail F-CDF gives small p.
4. ACAT Cauchy combine across axes with the ArcFISH axis weights.
5. Run ``scipy.signal.find_peaks`` on the combined statistic to pick
   local minima in p-value (peaks in ``-log10 p``).
6. BH-FDR adjust the per-peak p-values.  Boundaries are peaks with
   ``fdr < fdr_cutoff``.
7. (Optional) **Hierarchical TADs** — repeatedly drop the weakest
   boundary and emit the regions that the remaining boundaries define,
   producing nested levels.

Output
------
A DataFrame with columns ``chrom, start, end, level, score, pval, fdr``,
one merged table over all requested chromosomes, stored with provenance
at ``cd.results[key_added]`` (default ``"tads.arcfish"``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from uchrom.convention import (
    UNSET,
    merge_tables,
    parse_legacy_call,
    resolve_chroms,
    select_spots,
    selection_inputs,
    store_and_return,
)
from uchrom.fea.arc import axis_variance_cube, filter_normalize, axis_weight
from uchrom.utils.stats import cauchy_combination


@dataclass
class TADCallerParams:
    """Runtime parameters for :func:`call_tads_by_pval`.

    Defaults follow ArcFISH's ``TADCaller(method='pval')``.
    """

    window_bp: float = 1e5          # boundary window size
    fdr_cutoff: float = 0.1
    hierarchical: bool = True       # emit nested hierarchy levels
    max_levels: int = 4             # cap the hierarchy depth
    prominence: float = 0.0         # pass-through to find_peaks
    distance: int = 1               # pass-through to find_peaks
    k_sigma: float = 4.0
    frac: float = 0.1


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _bh_fdr(pvals: np.ndarray) -> np.ndarray:
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
    q = np.minimum.accumulate(q[::-1])[::-1]
    q = np.clip(q, 0.0, 1.0)
    o = np.empty_like(pf)
    o[order] = q
    out[finite] = o
    return out


def _boundary_pvals(
    norm_var: np.ndarray,
    count: np.ndarray,
    bin_midpoints: np.ndarray,
    axis_weights: np.ndarray,
    window_bp: float,
):
    """Per-bin ACAT p-value for intra-vs-inter domain variance ratio.

    Returns ``(pvals (B,), per_axis_logp (3, B))``.  Bins whose window
    does not have at least one intra and one inter pair get NaN.
    """
    from scipy.stats import f as _f_dist

    B = len(bin_midpoints)
    pvals = np.full(B, np.nan, dtype=np.float64)
    per_axis_logp = np.full((3, B), 0.0, dtype=np.float64)
    half_w = 0.5 * window_bp

    # Count-weighted var and weights per axis — precompute once
    w_var = np.where(np.isfinite(norm_var), norm_var * count, 0.0)
    w_cnt = np.where(np.isfinite(norm_var), count, 0.0)

    for b in range(B):
        left_mask = (bin_midpoints >= bin_midpoints[b] - half_w) & \
                    (bin_midpoints < bin_midpoints[b])
        right_mask = (bin_midpoints > bin_midpoints[b]) & \
                     (bin_midpoints <= bin_midpoints[b] + half_w)
        if left_mask.sum() < 1 or right_mask.sum() < 1:
            continue

        li = np.where(left_mask)[0]
        ri = np.where(right_mask)[0]

        # Pairs (i, j) where i < j and (both in L) or (both in R) → intra
        # Pairs (i, j) where i in L and j in R → inter
        intra_mask = np.zeros((B, B), dtype=bool)
        inter_mask = np.zeros((B, B), dtype=bool)
        for i in li:
            for j in li:
                if i < j:
                    intra_mask[i, j] = True
        for i in ri:
            for j in ri:
                if i < j:
                    intra_mask[i, j] = True
        for i in li:
            for j in ri:
                if i < j:
                    inter_mask[i, j] = True

        combined_logp = np.zeros(3)
        combined_F = np.zeros(3)
        ok = True
        for ax in range(3):
            wv_intra = w_var[ax][intra_mask].sum()
            wc_intra = w_cnt[ax][intra_mask].sum()
            wv_inter = w_var[ax][inter_mask].sum()
            wc_inter = w_cnt[ax][inter_mask].sum()
            if wc_intra <= 0 or wc_inter <= 0:
                ok = False
                break
            intra_mean = wv_intra / wc_intra
            inter_mean = wv_inter / wc_inter
            if intra_mean <= 0 or inter_mean <= 0:
                ok = False
                break
            F = intra_mean / inter_mean
            combined_F[ax] = F
            combined_logp[ax] = _f_dist.logcdf(
                F, dfn=max(wc_intra, 1.0), dfd=max(wc_inter, 1.0)
            )
        if not ok:
            continue

        per_axis_logp[:, b] = combined_logp
        # ACAT combine on p-scale
        p = np.clip(np.exp(combined_logp), 1e-300, 1 - 1e-15)
        pvals[b] = float(cauchy_combination(p[None, :], weights=axis_weights, axis=1)[0])

    return pvals, per_axis_logp


def _emit_tads(
    boundaries: List[int],
    bin_ids,
    chrom: str,
    level: int,
    pvals: np.ndarray,
    fdr: np.ndarray,
) -> List[dict]:
    """Given sorted boundary bin indices, emit (start, end) TADs."""
    if not boundaries:
        return []
    B = len(bin_ids)
    pts = [0] + sorted(boundaries) + [B]
    rows = []
    for a, b in zip(pts[:-1], pts[1:]):
        if b - a < 2:
            continue
        s = bin_ids[a][0]
        e = bin_ids[b - 1][1]
        # Score: min fdr of the enclosing boundaries (worst confidence)
        adj = []
        if a > 0:
            adj.append(a)
        if b < B:
            adj.append(b)
        if not adj:
            score, p, q = np.nan, np.nan, np.nan
        else:
            qs = [fdr[k] for k in adj if np.isfinite(fdr[k])]
            ps = [pvals[k] for k in adj if np.isfinite(pvals[k])]
            q = float(min(qs)) if qs else np.nan
            p = float(min(ps)) if ps else np.nan
            score = -np.log10(max(p, 1e-300)) if np.isfinite(p) else np.nan
        rows.append({
            "chrom": chrom,
            "start": int(s),
            "end": int(e),
            "level": int(level),
            "score": score,
            "pval": p,
            "fdr": q,
        })
    return rows


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

def call_tads_by_pval(
    cd,
    *args,
    chrom=None,
    trace_ids=None,
    cells=None,
    params: Optional[TADCallerParams] = None,
    device: str = "auto",
    key_added: Optional[str] = UNSET,
    copy: bool = False,
    verbose: bool = False,
    streaming: Optional[bool] = None,
    batch="auto",
    memory_budget=None,
    store=UNSET,
    result_key=UNSET,
):
    """ArcFISH-style TAD caller (chromatin tracing).

    Parameters
    ----------
    cd : ChromData
    chrom : str, sequence of str, or None
        Chromosome(s) to call.  ``None`` (default) calls every chromosome
        with spots and merges the per-chromosome tables.
    trace_ids, cells : sequence, optional
        Restrict the population to these traces / cells.
    params : TADCallerParams, optional
    device : ``'auto' | 'cpu' | 'cuda' | 'mps'``
    key_added : str or None
        ``cd.results`` key for the merged table (default ``"tads.arcfish"``);
        ``None`` does not store.
    copy : bool
        ``True`` → return a new ChromData with the result; ``cd`` is not
        modified.
    streaming : bool, optional
        Compute the axis-variance cube by streaming over the traces
        (:func:`uchrom.fea.arc_stream.axis_cube_streaming`: exact medians per
        row band, memory ``O(n_bins²)`` instead of
        ``O(n_traces × n_bins²)``).  Default: ``True`` for a backed
        ``ChromData``.  Results equal the in-memory path up to
        floating-point rounding of the variance sums.
    batch, memory_budget
        Traces per batch (``"auto"``) and working-memory budget of the
        streaming path (default :data:`uchrom.settings.memory_budget`).

    Returns
    -------
    DataFrame (``copy=False``) or ChromData (``copy=True``)
        Columns ``chrom, start, end, level, score, pval, fdr``.  Level 1
        is the finest partition (all boundaries); each further level
        drops the weakest boundary when ``params.hierarchical=True``.

    Notes
    -----
    Deprecated 1.x forms still work with a ``DeprecationWarning``:
    positional ``chrom``, ``store=`` and ``result_key=``.  When any of
    them is used and ``key_added`` is not given, the result is stored
    under the 1.x key ``"tads"``.
    """
    chrom, key_added, _ = parse_legacy_call(
        "call_tads_by_pval", args, chrom=chrom, key_added=key_added,
        store=store, result_key=result_key, default_key="tads.arcfish",
        legacy_key="tads", copy=copy,
    )
    params = params or TADCallerParams()
    work = select_spots(cd, trace_ids=trace_ids, cells=cells)
    chroms = resolve_chroms(work, chrom)
    streaming = bool(getattr(work, "backed", False)) if streaming is None else bool(streaming)
    frames = [_call_tads_by_pval_chrom(work, c, params, device, verbose, streaming=streaming,
                                       batch=batch, memory_budget=memory_budget) for c in chroms]
    table = merge_tables(frames, _empty_tads())
    return store_and_return(
        cd, table, key_added=key_added, copy=copy, kind="intervals", interval_kind="domain",
        function="uchrom.strc.tad.call_tads_by_pval", params=params,
        inputs=selection_inputs(work, chroms, trace_ids, cells),
    )


def _call_tads_by_pval_chrom(cd, chrom: str, params: TADCallerParams,
                             device: str, verbose: bool, *, streaming: bool = False,
                             batch="auto", memory_budget=None) -> pd.DataFrame:
    """Per-chromosome kernel of :func:`call_tads_by_pval` (no storing)."""
    from scipy.signal import find_peaks

    if verbose:
        print(f"[tad/{chrom}] variance cube{' (streaming)' if streaming else ''}...")
    if streaming:
        from uchrom.fea.arc_stream import axis_cube_streaming

        cube = axis_cube_streaming(cd, chrom, k_sigma=params.k_sigma, frac=params.frac,
                                   streaming=True, batch=batch, memory_budget=memory_budget)
        w = cube["axis_weight"]
    else:
        cube = axis_variance_cube(cd, chrom=chrom, device=device)
        if verbose:
            print(f"[tad/{chrom}] filter + normalise...")
        cube = filter_normalize(cube, k_sigma=params.k_sigma, frac=params.frac)
        w = axis_weight(cd, chrom=chrom, device=device)

    norm_var = cube["norm_var"]
    count = cube["count"]
    bin_ids = cube["bin_ids"]
    B = len(bin_ids)
    midpoints = np.array([(s + e) * 0.5 for (s, e) in bin_ids])

    if verbose:
        print(f"[tad/{chrom}] axis weights: {np.round(w, 3)}")

    pvals, per_axis_logp = _boundary_pvals(
        norm_var, count, midpoints, w, params.window_bp
    )

    # Peak-picking on -log10 p
    neg_log_p = np.where(
        np.isfinite(pvals) & (pvals > 0),
        -np.log10(np.clip(pvals, 1e-300, 1.0)),
        0.0,
    )
    peak_idx, _ = find_peaks(
        neg_log_p,
        prominence=params.prominence if params.prominence > 0 else None,
        distance=params.distance if params.distance >= 1 else None,
    )

    if len(peak_idx) == 0:
        if verbose:
            print(f"[tad/{chrom}] no peaks found")
        return _empty_tads()

    peak_pvals = pvals[peak_idx]
    peak_fdr = _bh_fdr(peak_pvals)
    accept = np.where((peak_fdr < params.fdr_cutoff) & np.isfinite(peak_fdr))[0]
    if len(accept) == 0:
        if verbose:
            print(f"[tad/{chrom}] no boundary passes fdr<{params.fdr_cutoff}")
        return _empty_tads()

    # Full per-bin fdr array (NaN for non-peaks)
    fdr_full = np.full(B, np.nan, dtype=np.float64)
    fdr_full[peak_idx] = peak_fdr

    accepted_bins = list(peak_idx[accept])
    # Sort boundaries by descending strength: strongest first.
    sorted_by_strength = sorted(accepted_bins, key=lambda i: float(fdr_full[i]))
    n_bdry = len(sorted_by_strength)

    # Hierarchy convention: **level 1 = all boundaries** (finest TAD
    # partition — the natural "full" result).  Each subsequent level
    # drops the weakest remaining boundary, producing progressively
    # coarser nested TADs.
    rows = []
    if not params.hierarchical:
        rows.extend(_emit_tads(sorted_by_strength, bin_ids, chrom, 1, pvals, fdr_full))
    else:
        levels = min(params.max_levels, max(1, n_bdry))
        for level in range(1, levels + 1):
            # level 1: keep all n boundaries
            # level 2: drop the 1 weakest
            # level k: drop (k-1) weakest
            n_keep = max(1, n_bdry - (level - 1))
            kept = sorted_by_strength[:n_keep]
            rows.extend(_emit_tads(kept, bin_ids, chrom, level, pvals, fdr_full))

    df_out = pd.DataFrame(rows)
    if df_out.empty:
        df_out = _empty_tads()
    return df_out


def _empty_tads() -> pd.DataFrame:
    return pd.DataFrame({
        "chrom": pd.Series(dtype=str),
        "start": pd.Series(dtype="int64"),
        "end":   pd.Series(dtype="int64"),
        "level": pd.Series(dtype="int64"),
        "score": pd.Series(dtype="float64"),
        "pval":  pd.Series(dtype="float64"),
        "fdr":   pd.Series(dtype="float64"),
    })


__all__ = [
    "TADCallerParams",
    "call_tads_by_pval",
]
