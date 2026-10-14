"""Streaming ArcFISH preprocessing: the axis-variance cube without the
``(3, n_traces, n_bins, n_bins)`` tensor.

:func:`axis_cube_streaming` returns what
``filter_normalize(axis_variance_cube(cd, chrom))`` returns (``var``,
``count``, ``raw_var``, ``expected``, ``norm_var``, ``genomic_distance``,
``bin_ids``, ``n_traces``, ``chrom``, ``axis_weight``), reading the
chromosome's traces in batches (``cd.iter_traces(chrom=..., columns="coords")``)
— so a backed store of any size — with memory ``O(n_bins²)`` plus one row band
of pair observations (:mod:`uchrom.fea._pairs`).  Same conventions as
:mod:`uchrom.fea.arc` (loci with a finite coordinate, a repeated locus keeps
its first spot, the usual median).

How each quantity is computed, and how exactly it matches the in-memory
(torch) path:

* **medians** (per-axis median of the pairwise difference, then of its
  squared deviation — the first LOWESS pass): exact order statistics per
  bin pair, gathered one row band at a time; the median is the mean of the
  ranks ``(n - 1) // 2`` and ``n // 2``.  Identical values.  The matrices are
  symmetric (the lower triangle holds the negated differences, whose median is
  minus the upper one), so only the upper triangle is computed.
* **outlier filter** (``|diff - median| > k_sigma × strata_std``): the same
  comparisons on the same values.  Identical masks.
* **filtered count / mean / variance** (second pass): counts identical;
  sums are accumulated in trace order, torch sums in its own (cascade)
  order, so ``var`` / ``norm_var`` agree to floating-point rounding
  (relative differences ~1e-15; tested ≤ 1e-9).
* **axis weights**: per trace the mean over its loci, per locus the mean
  square of the centred values over the traces, the median over the loci
  (same rounding caveat).

Round trips over the data: 1 (bins, traces) + 1 (weights, diagonal) + 2 ×
the number of row bands.
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np

from ._pairs import MAX_BLOCK_PAIRS, ChromPairs, grouped_order_stats
from .arc import _genomic_distance_matrix, _lowess_symmetric, _normalise

#: working bytes per pair observation of a band (3 axes × (index + value)
#: plus sort temporaries)
BYTES_PER_PAIR = 120


def _finite_any(coords: np.ndarray) -> np.ndarray:
    return np.isfinite(coords).any(axis=1)


def _weights_and_diagonal(P: ChromPairs):
    """:func:`uchrom.fea.arc.axis_weight` of one chromosome and the diagonal of the count matrix (traces with a
    finite coordinate at each locus, per axis), in one pass over the traces."""
    B = P.n_bins
    sumsq = np.zeros((3, B))
    nobs = np.zeros((3, B), dtype=np.int64)
    for bid, coords, runs in P.chunks():
        n_runs = len(runs) - 1
        if n_runs <= 0:
            continue
        li = P.local(bid)
        inside = li >= 0
        starts = runs[:-1]
        lens = np.diff(runs)
        valid = np.isfinite(coords) & inside[:, None]
        safe = np.where(valid, coords, 0.0)
        cnt = np.add.reduceat(valid.astype(np.float64), starts, axis=0)
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = np.add.reduceat(safe, starts, axis=0) / cnt          # NaN for a trace without a value
        centred = coords - np.repeat(mean, lens, axis=0)
        for a in range(3):
            ok = valid[:, a] & np.isfinite(centred[:, a])
            np.add.at(sumsq[a], li[ok], centred[ok, a] ** 2)
            np.add.at(nobs[a], li[valid[:, a]], 1)
    w = np.empty(3)
    with np.errstate(invalid="ignore", divide="ignore"):
        for a in range(3):
            xvars = np.where(nobs[a] > 0, sumsq[a] / np.maximum(nobs[a], 1), np.nan)
            w[a] = 1.0 / np.nanmedian(xvars)
    return w / w.sum(), nobs


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


def axis_cube_streaming(cd, chrom: str, *, k_sigma: float = 4.0, frac: float = 0.1,
                        streaming: Optional[bool] = None, batch="auto",
                        memory_budget=None) -> Dict[str, object]:
    """``filter_normalize(axis_variance_cube(cd, chrom))`` (with its ``axis_weight``), streaming over the traces
    (see the module docstring).

    Returns the ``filter_normalize`` keys plus ``axis_weight`` (3,), ``n_bands``, ``n_passes`` and ``pairs`` (the
    :class:`ChromPairs` — used by the loop caller's pseudo-contact frequency)."""
    from uchrom.utils.memory import release_memory

    P = ChromPairs(cd, chrom, streaming=streaming, batch=batch, observed=True, memory_budget=memory_budget,
                   duplicates="first", observed_finite=True)
    P.prepare()
    B = P.n_bins
    bin_ids = P.bin_intervals()
    d1d = _genomic_distance_matrix(bin_ids)
    iu = np.triu_indices(B, k=1)
    d_flat = d1d[iu]
    idx_dtype = np.int32 if B * B < 2 ** 31 else np.int64
    w, diag = _weights_and_diagonal(P)
    passes = 2

    fixed = B * B * 8 * 8 + MAX_BLOCK_PAIRS * 150 + int(0.1 * P.memory_budget)
    bands = P.bands(BYTES_PER_PAIR, fixed_bytes=fixed)

    # ---- round 1: exact medians -> raw_var (upper triangle) ----------------
    med = np.full((3, B * B), np.nan)
    rv = np.full((3, B * B), np.nan)
    for lo, hi in bands:
        for a, (k, x) in enumerate(_band_values(P, lo, hi, B, idx_dtype)):
            if not len(k):
                continue
            keys, counts, m_lo, m_hi, order = grouped_order_stats(k, x)
            m = (m_lo + m_hi) / 2
            med[a, keys] = m
            ks = k[order]
            dev = x[order] - m[np.repeat(np.arange(len(keys)), counts)]
            del order
            _, _, v_lo, v_hi, _ = grouped_order_stats(ks, dev * dev)
            rv[a, keys] = (v_lo + v_hi) / 2
            del ks, dev, k, x
        passes += 1
        release_memory()
    raw_var = rv.reshape(3, B, B)
    for a in range(3):
        raw_var[a].T[iu] = raw_var[a][iu]
    strata_std = np.stack([np.sqrt(_lowess_symmetric(raw_var[a][iu], d_flat, iu, B, frac)) for a in range(3)])
    thr = (k_sigma * strata_std).reshape(3, B * B)

    # ---- round 2: outlier filter -> filtered count / mean / var ------------
    cnt = np.zeros((3, B * B), dtype=np.int64)
    fvar = np.full((3, B * B), np.nan)
    for lo, hi in bands:
        base, size = lo * B, (hi - lo) * B          # the band's slice of the flat matrix
        for a, (k, x) in enumerate(_band_values(P, lo, hi, B, idx_dtype)):
            if not len(k):
                continue
            keep = ~(np.abs(x - med[a, k]) > thr[a, k])
            kk = k[keep].astype(np.int64) - base
            xx = x[keep]
            del keep, k, x
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
            cnt[a, base + touched] = n[touched]
            fvar[a, base + touched] = ss[touched] / n[touched]
            del s, n, mfull, dev, ss, kk, xx
        passes += 1
        release_memory()
    count = cnt.reshape(3, B, B)
    var = fvar.reshape(3, B, B)
    for a in range(3):
        count[a].T[iu] = count[a][iu]
        var[a].T[iu] = var[a][iu]
        np.fill_diagonal(count[a], diag[a])
        np.fill_diagonal(var[a], np.where(diag[a] > 0, 0.0, np.nan))
    del cnt, fvar

    out = _normalise({"bin_ids": bin_ids, "n_traces": int(P.n_traces), "chrom": chrom}, var, count,
                     raw_var, d1d, iu, frac)
    out.update({"axis_weight": w, "n_bands": len(bands), "n_passes": passes, "pairs": P})
    return out


def pseudo_contact_frequency_streaming(P: ChromPairs, contact_sep: float = 2.5e4) -> np.ndarray:
    """The loop caller's contact frequency (:func:`uchrom.strc.loop.axiswise_f._pseudo_contact_frequency`),
    streaming: the cutoff is the mean 3-D distance of the locus pairs exactly ``contact_sep`` apart (all traces,
    both triangles; all ones when there is no such pair); ``freq[i, j]`` the fraction of the traces observing both
    loci whose distance is below it (NaN when none).  Two passes."""
    from ._pairs import pair_distance
    from .arc import _bin_starts

    P.prepare()
    B = P.n_bins
    st = _bin_starts(P.bin_intervals())
    d1sel = np.abs(st[:, None] - st[None, :]) == contact_sep
    if not d1sel.any():
        return np.ones((B, B))
    sel_flat = d1sel.reshape(-1)
    total, n = 0.0, 0
    for i, j, ci, cj in P.pairs():
        d = pair_distance(ci, cj)
        m = sel_flat[i * B + j]
        total += 2.0 * float(d[m].sum())
        n += 2 * int(m.sum())
    cutoff = total / n if n else float("nan")
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
    np.fill_diagonal(valid, P.bin_counts)
    np.fill_diagonal(hit, P.bin_counts if cutoff > 0 else 0)     # distance 0 < cutoff
    with np.errstate(divide="ignore", invalid="ignore"):
        return hit / valid


__all__ = ["axis_cube_streaming", "pseudo_contact_frequency_streaming"]
