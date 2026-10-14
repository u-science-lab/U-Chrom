"""ArcFISH's loop caller for chromatin tracing: the axis-wise F test of every locus pair against its local
background (``LoopCaller`` with ``AxisWiseF``).

Reference: Yu H. *et al.* ArcFISH: accurate and robust 3D genome feature discovery from chromatin tracing data.
bioRxiv 2025.11.26.690837 (github.com/hyuyu104/ArcFISH).  U-Chrom's own implementation of the published algorithm;
``benchmarks/arcfish_parity/`` checks it against the authors' package (commit a21d889): the same test matrices and
the same loops.

Algorithm (per chromosome; loci and genomic distances as :mod:`uchrom.fea.arc`)
------------------------------------------------------------------------------
1. Normalised variances ``norm_var`` and counts ``count`` (:func:`uchrom.fea.arc.filter_normalize`) and the axis
   weights ``w``.
2. Every pair ``i < j`` whose distance ``start_j - start_i`` lies in ``[cut_lo, cut_up]`` is tested against its
   local background: the pairs ``(k, l)``, ``k < l``, with ``|start_k - start_i| <= outer_cut`` and
   ``|start_l - start_j| <= outer_cut``, except those with both distances ``<= inner_cut`` and those in row ``i``
   or column ``j``.  A pair with at most 3 background pairs is not tested.  Per axis
   ``F = norm_var[i, j] / (count-weighted mean of the background's norm_var)`` (a background pair whose variance
   is missing counts in the weights but adds nothing) and ``p = F.cdf(F; count[i, j], Σ background counts)``.
3. ``stat = Σ w tan((0.5 − p) π)`` over the axes, ``pval = 1 − Cauchy.cdf(stat)``; Benjamini–Hochberg over the
   tested pairs; candidates have ``fdr < fdr_cutoff``.
4. Candidates are grouped into clusters: two candidates are linked when both their loci are within ``gap`` of each
   other's (in bp).  The summit of a cluster is its candidate with the smallest ``pval``; it is kept when the
   fraction of traces whose two spots are closer than the contact cutoff exceeds 1/2 for a cluster of two pairs
   and 1/3 otherwise (the authors' rule as implemented: their "singleton" test counts a symmetric pair twice) —
   the contact cutoff is the mean 3-D distance of the locus pairs exactly ``contact_sep`` apart (25 kb; with no
   such pair the test is off).
5. A loop is a summit with ``pval < pval_cutoff``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

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
from uchrom.fea.arc import axis_variance_cube, bh_fdr, filter_normalize
from uchrom.fea.arc import _bin_starts, _coord_tensor, _diff_rows, _row_blocks


# ----------------------------------------------------------------------
# Parameters
# ----------------------------------------------------------------------

@dataclass
class LoopCallerParams:
    """Runtime parameters for :func:`call_loops_axiswise_f` (ArcFISH's ``LoopCaller`` defaults; distances in bp).

    ``inner_cut`` and ``contact_sep`` are fixed at 25 kb in the authors' code; ``min_cluster_size`` (U-Chrom,
    default 1 = off) drops clusters with fewer candidate pairs.  ``k_sigma`` / ``frac``: the outlier filter and
    LOWESS span of :func:`uchrom.fea.arc.filter_normalize`.

    Before U-Chrom 0.3 (2026-10) the background ring was rounded to bins, untestable axes entered the combination
    with ``p = 1``, summits were chosen by a weighted log-p and the contact cutoff used pairs one median bin apart;
    results differ from the authors' (``docs/source/reference/changelog.md``).
    """

    cut_lo: float = 1e5
    cut_up: float = 1e6
    inner_cut: float = 2.5e4
    outer_cut: float = 5e4
    fdr_cutoff: float = 0.1
    pval_cutoff: float = 1e-5
    gap: float = 5e4
    contact_sep: float = 2.5e4
    k_sigma: float = 4.0
    frac: float = 0.1
    min_cluster_size: int = 1

    def __post_init__(self):
        assert self.cut_lo < self.cut_up
        assert self.inner_cut < self.outer_cut


# ----------------------------------------------------------------------
# The test (module docstring, steps 2-5)
# ----------------------------------------------------------------------

def loop_tests(norm_var: np.ndarray, count: np.ndarray, starts: np.ndarray, weights: np.ndarray,
               params: LoopCallerParams) -> dict:
    """``(B, B)`` symmetric matrices ``stat``, ``pval`` and ``(3, B, B)`` ``axis_stat``, ``axis_pval`` of the
    pairs tested (NaN elsewhere)."""
    from scipy import stats

    B = len(starts)
    d = np.asarray(starts, dtype=np.float64)
    axis_stat = np.full((3, B, B), np.nan)
    axis_pval = np.full((3, B, B), np.nan)
    sep = d[None, :] - d[:, None]
    for i, j in zip(*np.nonzero((sep >= params.cut_lo) & (sep <= params.cut_up))):
        K = np.flatnonzero(np.abs(d - d[i]) <= params.outer_cut)
        L = np.flatnonzero(np.abs(d - d[j]) <= params.outer_cut)
        bk = np.ones((len(K), len(L)), dtype=bool)
        bk &= ~((np.abs(d[K] - d[i]) <= params.inner_cut)[:, None] & (np.abs(d[L] - d[j]) <= params.inner_cut)[None, :])
        bk &= (K != i)[:, None] & (L != j)[None, :]
        bk &= K[:, None] < L[None, :]
        if bk.sum() <= 3:
            continue
        kk, ll = np.nonzero(bk)
        kk, ll = K[kk], L[ll]
        c = count[:, kk, ll].astype(np.float64)
        n_bg = c.sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            den = np.nansum((c / n_bg[:, None]) * norm_var[:, kk, ll], axis=1)
            f = norm_var[:, i, j] / den
        p = stats.f.cdf(f, count[:, i, j], n_bg)
        axis_stat[:, i, j] = axis_stat[:, j, i] = f
        axis_pval[:, i, j] = axis_pval[:, j, i] = p
    w = np.asarray(weights, dtype=np.float64)[:, None, None]
    stat = np.sum(w * np.tan((0.5 - axis_pval) * np.pi), axis=0)
    return {"axis_stat": axis_stat, "axis_pval": axis_pval, "stat": stat, "pval": 1 - stats.cauchy.cdf(stat)}


def _clusters(cand: np.ndarray, starts: np.ndarray, gap: float) -> np.ndarray:
    """``(B, B)`` labels (1, 2, …; NaN elsewhere) of the candidates' clusters: candidates linked when both loci are
    within ``gap`` (bp), a pair and its mirror sharing a label.  Labels are numbered by the first upper-triangle
    entry of each cluster in row-major order."""
    d = np.asarray(starts, dtype=np.float64)
    ii, jj = np.nonzero(cand)
    n = len(ii)
    parent = np.arange(n)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    pos = {(int(a), int(b)): k for k, (a, b) in enumerate(zip(ii, jj))}
    for k, (a, b) in enumerate(zip(ii, jj)):
        m = pos.get((int(b), int(a)))
        if m is not None:
            parent[find(k)] = find(m)
    for k0 in range(0, n, 2048):
        a = slice(k0, min(n, k0 + 2048))
        near = (np.abs(d[ii[a]][:, None] - d[ii][None, :]) <= gap) & (np.abs(d[jj[a]][:, None] - d[jj][None, :]) <= gap)
        for r, c in zip(*np.nonzero(near)):
            ra, rb = find(k0 + r), find(c)
            if ra != rb:
                parent[ra] = rb
    roots = np.array([find(k) for k in range(n)])
    label = np.full(cand.shape, np.nan)
    upper = ii < jj
    order = np.lexsort((jj, ii))
    num = {}
    for k in order:
        if upper[k] and roots[k] not in num:
            num[roots[k]] = len(num) + 1
    for k in order:
        if roots[k] not in num:
            num[roots[k]] = len(num) + 1
    label[ii, jj] = [num[r] for r in roots]
    return label


def _summits(label: np.ndarray, pval: np.ndarray, freq: np.ndarray) -> np.ndarray:
    """Boolean ``(B, B)`` summits (module docstring, step 4)."""
    summit = np.zeros(label.shape, dtype=bool)
    upper = np.triu(np.nan_to_num(label, nan=0.0))
    for lab in np.unique(label[~np.isnan(label)]):
        idx = np.nonzero(upper == lab)
        if not len(idx[0]):
            continue
        k = int(np.argmin(pval[idx]))
        i1, i2 = idx[0][k], idx[1][k]
        need = 0.5 if len(idx[0]) == 2 else 1.0 / 3.0
        if freq[i1, i2] > need:
            summit[i1, i2] = summit[i2, i1] = True
    return summit


def loop_matrices(cube: dict, freq: np.ndarray, params: LoopCallerParams) -> dict:
    """All test matrices of one chromosome: ``axis_stat``, ``axis_pval``, ``stat``, ``pval``, ``fdr``,
    ``candidate``, ``label``, ``summit``, ``final`` (as the authors' ``LoopCaller.call_loops``) and ``freq``."""
    starts = _bin_starts(cube["bin_ids"])
    res = loop_tests(cube["norm_var"], cube["count"], starts, cube["axis_weight"], params)
    pval = res["pval"]
    iu = np.triu_indices_from(pval, 1)
    q = bh_fdr(pval[iu])
    fdr = np.full_like(pval, np.nan)
    fdr[iu] = q
    fdr.T[iu] = q
    with np.errstate(invalid="ignore"):
        cand = fdr < params.fdr_cutoff
    label = _clusters(cand, starts, params.gap)
    summit = _summits(label, pval, freq)
    with np.errstate(invalid="ignore"):
        final = summit & (pval < params.pval_cutoff)
    res.update({"fdr": fdr, "candidate": cand, "label": label, "summit": summit, "final": final, "freq": freq})
    return res


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

def call_loops_axiswise_f(
    cd,
    *args,
    chrom=None,
    trace_ids=None,
    cells=None,
    params: Optional[LoopCallerParams] = None,
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
    """ArcFISH's axis-wise F-test loop caller (chromatin tracing; module docstring).

    Parameters
    ----------
    cd : :class:`uchrom.ChromData`
        Tracing data.  Must contain ``trace_id`` in ``spots``.
    chrom : str, sequence of str, or None
        Chromosome(s) — matched against ``cd.spots['chrom']``.  ``None``
        (default) calls every chromosome and merges the tables.
    trace_ids, cells : sequence, optional
        Restrict the population to these traces / cells.
    params : LoopCallerParams, optional
        Override any default.
    device : str
        ``'auto' | 'cpu' | 'cuda' | 'mps'`` — passed to GPU-friendly
        preprocessing.
    key_added : str or None
        ``cd.results`` key (default ``"loops.axiswise_f"``); ``None`` does
        not store.
    copy : bool
        ``True`` → return a new ChromData holding the result.
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
        One row per called loop (a summit with ``pval < pval_cutoff``): BEDPE-style ``chrom1 … end2`` plus
        ``stat, pval, fdr, score`` (``-log10 pval``), ``cluster_size`` (candidate pairs of its cluster),
        ``contact_freq`` and ``summit_i, summit_j`` (per-chromosome locus indices).  The test matrices are
        :func:`arcfish_loop_matrices`.

    Notes
    -----
    Deprecated 1.x forms (positional ``chrom``, ``store=``,
    ``result_key=``) still work with a ``DeprecationWarning`` and default
    to the 1.x key ``"loops"``.
    """
    chrom, key_added, _ = parse_legacy_call(
        "call_loops_axiswise_f", args, chrom=chrom, key_added=key_added,
        store=store, result_key=result_key, default_key="loops.axiswise_f",
        legacy_key="loops", copy=copy,
    )
    params = params or LoopCallerParams()
    work = select_spots(cd, trace_ids=trace_ids, cells=cells)
    chroms = resolve_chroms(work, chrom)
    streaming = bool(getattr(work, "backed", False)) if streaming is None else bool(streaming)
    frames = [_call_loops_chrom(work, c, params, device, verbose, streaming=streaming, batch=batch,
                                memory_budget=memory_budget) for c in chroms]
    table = merge_tables(frames, _empty_result())
    return store_and_return(
        cd, table, key_added=key_added, copy=copy, kind="intervals", interval_kind="pair",
        function="uchrom.strc.loop.call_loops_axiswise_f", params=params,
        inputs=selection_inputs(work, chroms, trace_ids, cells),
    )


def _cube_and_freq(cd, chrom: str, params: LoopCallerParams, device: str, verbose: bool, *, streaming: bool,
                   batch, memory_budget):
    """The normalised variance cube (with its axis weights) and the contact-frequency matrix of one chromosome."""
    if verbose:
        print(f"[loop/{chrom}] variance cube{' (streaming)' if streaming else ''}...")
    if streaming:
        from uchrom.fea.arc_stream import axis_cube_streaming, pseudo_contact_frequency_streaming

        cube = axis_cube_streaming(cd, chrom, k_sigma=params.k_sigma, frac=params.frac,
                                   streaming=True, batch=batch, memory_budget=memory_budget)
        return cube, pseudo_contact_frequency_streaming(cube["pairs"], params.contact_sep)
    cube = axis_variance_cube(cd, chrom=chrom, device=device)
    freq = _pseudo_contact_frequency(cd, chrom, cube["bin_ids"], params.contact_sep, device=device)
    return filter_normalize(cube, k_sigma=params.k_sigma, frac=params.frac), freq


def arcfish_loop_matrices(cd, *, chrom: str, trace_ids=None, cells=None, params: Optional[LoopCallerParams] = None,
                          device: str = "auto", streaming: Optional[bool] = None, batch="auto",
                          memory_budget=None) -> dict:
    """The ``(B, B)`` test matrices of one chromosome (:func:`loop_matrices`) and its loci (``bin_ids``) — the
    authors' ``LoopCaller.call_loops`` dict, for inspection; not stored."""
    params = params or LoopCallerParams()
    work = select_spots(cd, trace_ids=trace_ids, cells=cells)
    streaming = bool(getattr(work, "backed", False)) if streaming is None else bool(streaming)
    cube, freq = _cube_and_freq(work, chrom, params, device, False, streaming=streaming, batch=batch,
                                memory_budget=memory_budget)
    out = loop_matrices(cube, freq, params)
    out["bin_ids"] = cube["bin_ids"]
    out["axis_weight"] = cube["axis_weight"]
    return out


def _call_loops_chrom(cd, chrom: str, params: LoopCallerParams,
                      device: str, verbose: bool, *, streaming: bool = False, batch="auto",
                      memory_budget=None) -> pd.DataFrame:
    """Per-chromosome kernel of :func:`call_loops_axiswise_f` (no storing)."""
    cube, freq = _cube_and_freq(cd, chrom, params, device, verbose, streaming=streaming, batch=batch,
                                memory_budget=memory_budget)
    m = loop_matrices(cube, freq, params)
    if verbose:
        tested = int(np.isfinite(m["pval"][np.triu_indices_from(m["pval"], 1)]).sum())
        print(f"[loop/{chrom}] {tested} pairs tested, "
              f"{int(np.triu(m['candidate'], 1).sum())} candidates, {int(np.triu(m['final'], 1).sum())} loops")
    bin_ids = cube["bin_ids"]
    rows = []
    upper_label = np.triu(np.nan_to_num(m["label"], nan=0.0))
    for i, j in zip(*np.nonzero(np.triu(m["final"], 1))):
        size = int((upper_label == m["label"][i, j]).sum())
        if size < params.min_cluster_size:
            continue
        (s1, e1), (s2, e2) = bin_ids[i], bin_ids[j]
        p = float(m["pval"][i, j])
        rows.append({
            "chrom1": chrom, "start1": int(s1), "end1": int(e1),
            "chrom2": chrom, "start2": int(s2), "end2": int(e2),
            "stat": float(m["stat"][i, j]), "pval": p, "fdr": float(m["fdr"][i, j]),
            "score": float(-np.log10(max(p, 1e-300))),
            "cluster_size": size, "contact_freq": float(freq[i, j]),
            "summit_i": int(i), "summit_j": int(j),
        })
    return pd.DataFrame(rows) if rows else _empty_result()


def _pseudo_contact_frequency(cd, chrom, bin_ids, contact_sep: float = 2.5e4, device="auto"):
    """Fraction of traces whose two spots are closer than the contact cutoff, per locus pair (module docstring,
    step 4): the cutoff is the mean 3-D distance of the pairs exactly ``contact_sep`` apart (all traces, both
    triangles); with no such pair the matrix is all ones.  NaN where no trace observed both loci."""
    import torch

    c, _, _ = _coord_tensor(cd, chrom, device)
    B = len(bin_ids)
    st = _bin_starts(bin_ids)
    d1sel = np.abs(st[:, None] - st[None, :]) == contact_sep
    if c.shape[1] != B or not d1sel.any():
        return np.ones((B, B))

    def pdist_rows(i0, i1):
        diff = _diff_rows(c, i0, i1)                            # (3, T, b, B)
        return torch.sqrt((diff ** 2).sum(dim=0)).detach().cpu().numpy().astype(np.float64)

    total, n_obs = 0.0, 0
    for i0, i1 in _row_blocks(c):
        vals = pdist_rows(i0, i1)[:, d1sel[i0:i1]]
        total += float(np.nansum(vals))
        n_obs += int(np.sum(~np.isnan(vals)))
    cutoff = total / n_obs if n_obs else float("nan")
    freq = np.empty((B, B), dtype=np.float64)
    for i0, i1 in _row_blocks(c):
        pd_rows = pdist_rows(i0, i1)
        with np.errstate(invalid="ignore", divide="ignore"):
            freq[i0:i1] = np.sum(pd_rows < cutoff, axis=0) / np.sum(~np.isnan(pd_rows), axis=0)
    return freq


def _empty_result() -> pd.DataFrame:
    return pd.DataFrame({
        "chrom1": pd.Series(dtype=str),
        "start1": pd.Series(dtype="int64"),
        "end1":   pd.Series(dtype="int64"),
        "chrom2": pd.Series(dtype=str),
        "start2": pd.Series(dtype="int64"),
        "end2":   pd.Series(dtype="int64"),
        "stat":   pd.Series(dtype="float64"),
        "pval":   pd.Series(dtype="float64"),
        "fdr":    pd.Series(dtype="float64"),
        "score":  pd.Series(dtype="float64"),
        "cluster_size": pd.Series(dtype="int64"),
        "contact_freq": pd.Series(dtype="float64"),
        "summit_i": pd.Series(dtype="int64"),
        "summit_j": pd.Series(dtype="int64"),
    })


__all__ = [
    "LoopCallerParams",
    "call_loops_axiswise_f",
    "arcfish_loop_matrices",
    "loop_matrices",
    "loop_tests",
]
