"""Streaming ArcFISH preprocessing: the axis-variance cube without the
``(3, n_traces, n_bins, n_bins)`` tensor.

:func:`axis_cube_streaming` returns what
``filter_normalize(axis_variance_cube(cd, chrom))`` returns (``var``,
``count``, ``raw_var``, ``expected``, ``norm_var``, ``genomic_distance``,
``bin_ids``, ``n_traces``, ``chrom``) plus the ArcFISH axis weights
(:func:`uchrom.fea.arc.axis_weight`), reading the chromosome's traces in
batches (``cd.iter_traces(chrom=..., columns="coords")``) — so a backed
store of any size — with memory ``O(n_bins²)`` plus one row band of pair
observations (:mod:`uchrom.fea._pairs`).

How each quantity is computed, and how exactly it matches the in-memory
(torch) path:

* **medians** (per-axis median of the pairwise difference, then of its
  squared deviation — the first LOWESS pass): exact order statistics per
  bin pair, gathered one row band at a time (``torch.nanmedian`` returns the
  *lower* median, rank ``(n - 1) // 2``; the lower triangle ``(j, i)`` holds
  the negated differences, whose lower median is minus the upper median of
  the upper triangle).  Identical values.
* **outlier filter** (``|diff - median| > k_sigma × strata_std``): the same
  comparisons on the same values.  Identical masks.
* **filtered count / mean / variance** (second pass): counts identical;
  sums are accumulated in trace order, torch sums in its own (cascade)
  order, so ``var`` / ``norm_var`` agree to floating-point rounding
  (relative differences ~1e-15; tested ≤ 1e-9).
* **axis weights**: per-trace variances in numpy instead of torch (same
  rounding caveat), then the exact lower median across traces.

Round trips over the data: 1 (bins, traces, weights) + 2 × the number of
row bands.
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np

from ._pairs import MAX_BLOCK_PAIRS, ChromPairs, grouped_order_stats
from .arc import _bin_midpoints, _genomic_distance_matrix
from uchrom.utils import lowess_log_log

#: working bytes per pair observation of a band (3 axes × (index + value)
#: plus sort temporaries)
BYTES_PER_PAIR = 120


def _finite_any(coords: np.ndarray) -> np.ndarray:
    return np.isfinite(coords).any(axis=1)


def _trace_weights(P: ChromPairs) -> np.ndarray:
    """:func:`uchrom.fea.arc.axis_weight` of one chromosome, streaming.

    Per trace and axis: the variance of the trace's coordinates over its
    (finite) bins (count clamped to 1, so a trace without a finite value on
    an axis contributes 0), then the lower median across traces; weights
    ``∝ 1 / median``, summing to 1."""
    per_trace = []
    for bid, coords, runs in P.chunks():
        n_runs = len(runs) - 1
        if n_runs <= 0:
            continue
        starts = runs[:-1]
        valid = np.isfinite(coords)
        safe = np.where(valid, coords, 0.0)
        cnt = np.maximum(np.add.reduceat(valid.astype(np.float64), starts, axis=0), 1.0)
        mean = np.add.reduceat(safe, starts, axis=0) / cnt
        lens = np.diff(runs)
        centred = np.where(valid, coords - np.repeat(mean, lens, axis=0), 0.0)
        per_trace.append(np.add.reduceat(centred ** 2, starts, axis=0) / cnt)
    tv = np.concatenate(per_trace) if per_trace else np.zeros((0, 3))
    med = np.empty(3)
    for a in range(3):
        v = np.sort(tv[:, a])
        med[a] = v[(len(v) - 1) // 2] if len(v) else np.nan
    w = 1.0 / np.maximum(med, 1e-30)
    return w / w.sum()


def _band_values(P: ChromPairs, lo: int, hi: int, B: int, idx_dtype):
    """Per axis: (pair index ``i * B + j``, difference ``c_i - c_j``) of the
    band's pairs with both coordinates finite on that axis."""
    idx = [[], [], []]
    val = [[], [], []]
    for i, j, ci, cj in P.pairs(lo, hi, valid=_finite_any):
        k = (i * B + j).astype(idx_dtype)
        diff = ci - cj
        for a in range(3):
            ok = np.isfinite(diff[:, a])
            if ok.all():
                idx[a].append(k)
                val[a].append(diff[:, a].copy())
            else:
                idx[a].append(k[ok])
                val[a].append(diff[ok, a])
    out = []
    for a in range(3):
        if idx[a]:
            out.append((np.concatenate(idx[a]), np.concatenate(val[a])))
        else:
            out.append((np.zeros(0, idx_dtype), np.zeros(0)))
        idx[a] = val[a] = None
    return out


def _lowess_matrix(values: np.ndarray, d_flat: np.ndarray, iu, B: int, frac: float) -> np.ndarray:
    """LOWESS log-log fit of one (B, B) upper triangle, as a symmetric matrix
    (NaN diagonal) — the per-axis step of ``filter_normalize``."""
    fit = lowess_log_log(d_flat, values[iu], frac=frac)
    m = np.full((B, B), np.nan)
    m[iu] = fit
    m.T[iu] = fit
    return m


def axis_cube_streaming(cd, chrom: str, *, k_sigma: float = 4.0, frac: float = 0.1,
                        streaming: Optional[bool] = None, batch="auto",
                        memory_budget=None) -> Dict[str, object]:
    """``filter_normalize(axis_variance_cube(cd, chrom))`` + ``axis_weight``,
    streaming over the traces (see the module docstring).

    Returns the ``filter_normalize`` keys plus ``axis_weight`` (3,),
    ``n_bands``, ``n_passes`` and ``pairs`` (the :class:`ChromPairs` —
    used by the loop caller's pseudo-contact frequency)."""
    from uchrom.utils.memory import release_memory

    P = ChromPairs(cd, chrom, streaming=streaming, batch=batch, observed=True,
                   memory_budget=memory_budget)
    P.prepare()
    B = P.n_bins
    bin_ids = P.bin_intervals()
    d1d = _genomic_distance_matrix(bin_ids)
    iu = np.triu_indices(B, k=1)
    d_flat = d1d[iu]
    idx_dtype = np.int32 if B * B < 2 ** 31 else np.int64
    w = _trace_weights(P)
    passes = 2

    # diagonal: the traces observing each bin (per axis, finite coordinate)
    diag = np.zeros((3, B), dtype=np.int64)
    for bid, coords, runs in P.chunks():
        li = P.local(bid)
        for a in range(3):
            ok = np.isfinite(coords[:, a])
            np.add.at(diag[a], li[ok], 1)
    passes += 1

    fixed = B * B * 8 * 12 + MAX_BLOCK_PAIRS * 150 + int(0.1 * P.memory_budget)
    bands = P.bands(BYTES_PER_PAIR, fixed_bytes=fixed)

    # ---- round 1: exact medians -> raw_var (both triangles) ---------------
    med_lo = np.full((3, B * B), np.nan)
    med_hi = np.full((3, B * B), np.nan)
    raw_var = np.full((3, B, B), np.nan)
    rv = raw_var.reshape(3, B * B)
    rv_t = np.full((3, B * B), np.nan)            # lower triangle, stored at [i*B + j]
    for lo, hi in bands:
        for a, (k, x) in enumerate(_band_values(P, lo, hi, B, idx_dtype)):
            if not len(k):
                continue
            keys, counts, m_lo, m_hi, order = grouped_order_stats(k, x)
            med_lo[a, keys] = m_lo
            med_hi[a, keys] = m_hi
            # squared deviations from the lower / upper median, per group
            ks = k[order]
            xs = x[order]
            del order
            grp = np.repeat(np.arange(len(keys)), counts)
            for m, dst in ((m_lo, rv), (m_hi, rv_t)):
                dev = xs - m[grp]
                sq = dev * dev
                _, _, v_lo, _, _ = grouped_order_stats(ks, sq)
                dst[a, keys] = v_lo
                del dev, sq
            del ks, xs, grp, k, x
        passes += 1
        release_memory()
    for a in range(3):
        lower = rv_t[a].reshape(B, B)
        raw_var[a].T[iu] = lower[iu]               # (j, i) <- stats of the upper-triangle values
    del rv_t
    raw_var = np.where(raw_var < 1e-30, np.nan, raw_var)
    strata_std = np.stack([np.sqrt(np.clip(_lowess_matrix(raw_var[a], d_flat, iu, B, frac), 1e-30, None))
                           for a in range(3)])
    thr = k_sigma * strata_std                     # (3, B, B), as torch: k_sigma * strata_std

    # ---- round 2: outlier filter -> filtered count / mean / var ------------
    cnt = np.zeros((3, B * B), dtype=np.int64)
    fvar = np.full((3, B * B), np.nan)
    thr_up = thr.reshape(3, B * B)
    thr_lo = np.stack([thr[a].T.reshape(B * B) for a in range(3)])   # threshold of (j, i) at i*B + j
    cnt_t = np.zeros((3, B * B), dtype=np.int64)
    fvar_t = np.full((3, B * B), np.nan)
    for lo, hi in bands:
        base, size = lo * B, (hi - lo) * B          # the band's slice of the flat matrix
        for a, (k, x) in enumerate(_band_values(P, lo, hi, B, idx_dtype)):
            if not len(k):
                continue
            for med, t, c_dst, v_dst in ((med_lo, thr_up, cnt, fvar), (med_hi, thr_lo, cnt_t, fvar_t)):
                keep = ~(np.abs(x - med[a, k]) > t[a, k])
                kk = k[keep].astype(np.int64) - base
                xx = x[keep]
                if not len(kk):
                    continue
                # sums in trace order, then the mean, then squared deviations
                s = np.zeros(size)
                n = np.zeros(size, dtype=np.int64)
                np.add.at(s, kk, xx)
                np.add.at(n, kk, 1)
                touched = np.flatnonzero(n)
                mfull = np.zeros(size)
                mfull[touched] = s[touched] / n[touched]
                dev = xx - mfull[kk]
                ss = np.zeros(size)
                np.add.at(ss, kk, dev * dev)
                c_dst[a, base + touched] = n[touched]
                v_dst[a, base + touched] = ss[touched] / n[touched]
                del s, n, mfull, dev, ss, kk, xx, keep
            del k, x
        passes += 1
        release_memory()
    count = np.zeros((3, B, B), dtype=np.int64)
    var = np.full((3, B, B), np.nan)
    for a in range(3):
        cu = cnt[a].reshape(B, B)
        cl = cnt_t[a].reshape(B, B)
        vu = fvar[a].reshape(B, B)
        vl = fvar_t[a].reshape(B, B)
        count[a][iu] = cu[iu]
        count[a].T[iu] = cl[iu]
        var[a][iu] = vu[iu]
        var[a].T[iu] = vl[iu]
        np.fill_diagonal(count[a], diag[a])
        np.fill_diagonal(var[a], np.where(diag[a] > 0, 0.0, np.nan))
    del cnt, cnt_t, fvar, fvar_t

    expected = np.full_like(var, np.nan)
    norm_var = np.full_like(var, np.nan)
    for a in range(3):
        v_flat = var[a][iu]
        v_flat_ok = np.where(v_flat > 1e-30, v_flat, np.nan)
        fit = lowess_log_log(d_flat, v_flat_ok, frac=frac)
        exp_axis = np.full((B, B), np.nan)
        exp_axis[iu] = fit
        exp_axis.T[iu] = fit
        expected[a] = exp_axis
        with np.errstate(invalid="ignore", divide="ignore"):
            norm_var[a] = np.where(exp_axis > 0, var[a] / exp_axis, np.nan)
        np.fill_diagonal(norm_var[a], 0.0)
    raw_out = raw_var.copy()
    for a in range(3):
        np.fill_diagonal(raw_out[a], np.nan)
    return {
        "var": var, "count": count, "raw_var": raw_out, "expected": expected,
        "norm_var": norm_var, "genomic_distance": d1d, "bin_ids": bin_ids,
        "n_traces": int(P.n_traces), "chrom": chrom, "axis_weight": w,
        "n_bands": len(bands), "n_passes": passes, "pairs": P,
    }


def pseudo_contact_frequency_streaming(P: ChromPairs) -> np.ndarray:
    """``_pseudo_contact_frequency`` of the loop caller, streaming: the
    cutoff is the mean 3-D distance of the pairs one median bin apart (all
    traces, both triangles); ``freq[i, j]`` the fraction of traces with both
    spots whose distance is below it.  Two passes."""
    from ._pairs import pair_distance

    P.prepare()
    B = P.n_bins
    bin_ids = P.bin_intervals()
    mids = _bin_midpoints(bin_ids)
    d1d = np.abs(mids[:, None] - mids[None, :])
    med_bin_size = float(np.median([e - s for s, e in bin_ids]))
    tol = max(1.0, 0.1 * med_bin_size)
    d1sel = np.abs(d1d - med_bin_size) <= tol
    if d1sel.sum() == 0:
        return np.ones((B, B))
    sel_flat = d1sel.reshape(-1)
    total, n = 0.0, 0
    for i, j, ci, cj in P.pairs():
        d = pair_distance(ci, cj)
        m = sel_flat[i * B + j]
        total += 2.0 * float(d[m].sum())
        n += 2 * int(m.sum())
    if not n:
        return np.ones((B, B))
    cutoff = total / n
    if not np.isfinite(cutoff) or cutoff <= 0:
        return np.ones((B, B))
    hit = np.zeros(B * B, dtype=np.int64)
    valid = np.zeros(B * B, dtype=np.int64)
    for i, j, ci, cj in P.pairs():
        k = i * B + j
        d = pair_distance(ci, cj)
        np.add.at(valid, k, 1)
        np.add.at(hit, k[d < cutoff], 1)
    hit = hit.reshape(B, B)
    valid = valid.reshape(B, B)
    iu = np.triu_indices(B, k=1)
    hit.T[iu] = hit[iu]
    valid.T[iu] = valid[iu]
    np.fill_diagonal(hit, P.bin_counts)            # distance 0 < cutoff
    np.fill_diagonal(valid, P.bin_counts)
    with np.errstate(divide="ignore", invalid="ignore"):
        freq = np.where(valid > 0, hit / np.maximum(valid, 1), 0.0)
    return freq.astype(np.float64)


__all__ = ["axis_cube_streaming", "pseudo_contact_frequency_streaming"]
