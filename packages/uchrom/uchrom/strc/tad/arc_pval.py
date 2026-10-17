"""ArcFISH's TAD caller for chromatin tracing: the arc p-value test of every locus as a domain boundary.

Reference: Yu H. *et al.* ArcFISH: accurate and robust 3D genome feature discovery from chromatin tracing data.
bioRxiv 2025.11.26.690837 (``TADCaller(method="pval")`` of github.com/hyuyu104/ArcFISH).  U-Chrom's own
implementation of the published algorithm; uchrom-reproducibility ``supp_table3/arcfish_parity/`` checks it against the authors' package
(commit a21d889): the same per-locus statistics and the same domains.

Algorithm (per chromosome)
--------------------------
1. Per-axis normalised variances ``norm_var`` and counts ``count`` of every locus pair
   (:func:`uchrom.fea.arc.filter_normalize`) and the axis weights ``w`` (:func:`uchrom.fea.arc.axis_weight`).
2. For every locus ``i`` at least ``window_bp / 2`` from both ends of the chromosome's loci: the loci within
   ``window_bp`` of it on each side, ``L`` (left of ``i``) and ``R`` (right of ``i``); per axis the count-weighted
   mean normalised variance of the pairs within ``L`` or within ``R`` (intra) and of the pairs across
   (inter) — a pair whose variance is missing counts in the weights but adds nothing —, ``F = intra / inter``, and
   ``p = F.cdf(F; Σ intra counts, Σ inter counts)`` (small at a boundary: tight domains, loose across).
3. The Cauchy combination over the axes, ``stat = Σ w tan((0.5 − p) π)``, its p-value ``1 − Cauchy.cdf(stat)``,
   and the same with ``F.cdf(F; 1, 1)`` (``stat_prox``).
4. Benjamini–Hochberg over every tested locus; a boundary is a local maximum of ``stat_prox``
   (``scipy.signal.find_peaks``) with ``fdr < fdr_cutoff``.
5. Domains: the first and the last locus count as boundaries; level 0 holds the domain between every two
   consecutive boundaries (the finest partition); when ``hierarchical``, the interior boundaries are removed one at
   a time, weakest ``stat`` first, and each removal adds the merged domain at the next level (1, 2, …).  Domains
   with ``start2 - start1 <= min_tad_size`` are dropped.

``method="insulation"`` (the authors' ``TADCaller(method="insulation")``, Su et al. 2020): the median 3-D distance of
every locus pair over the traces; per locus (same window and edge rule) the normalised insulation score
``(inter − intra) / (inter + intra)`` of the medians of the pairs across and within the two segments (0 where either
set is empty); boundaries are its local maxima (``find_peaks`` with ``prominence`` / ``distance``); domains as in step
5, ranked by the score.

Output
------
One row per domain: ``chrom, start, end, level`` (``start`` = start of the left boundary locus, ``end`` = start of
the right boundary locus, so that the domains of a level tile the chromosome's loci and a boundary is the start of
the next domain) and the boundary loci ``start1, end1, start2, end2`` with their ``stat1, stat2``;
stored with provenance at ``cd.results[key_added]`` (default ``"tads.arcfish"``).  The per-locus statistics are
:func:`arcfish_boundary_stats`.
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


@dataclass
class TADCallerParams:
    """Runtime parameters for :func:`call_tads_by_pval` (ArcFISH's ``TADCaller(method="pval")`` defaults).

    ``method``: ``"pval"`` (the arc p-value test) or ``"insulation"`` (Su et al. 2020; module docstring).
    ``window_bp`` (ArcFISH ``window``): the loci within this distance on each side of a locus form its left and
    right segments; loci closer than ``window_bp / 2`` to either end of the chromosome are not tested.
    ``hierarchical`` (ArcFISH ``tree``), ``min_tad_size`` in bp.  ``max_levels`` (U-Chrom): keep levels
    ``0 .. max_levels - 1`` only (``None``: all).  ``prominence`` / ``distance``: passed to ``find_peaks`` (the
    authors' parameters of the insulation method; also applied to ``"pval"``, where the authors use none).  ``k_sigma`` / ``frac``: the outlier filter and LOWESS span of
    :func:`uchrom.fea.arc.filter_normalize`.

    Before U-Chrom 0.3 (2026-10) ``window_bp`` was the *whole* window (half on each side), level 1 was the finest
    partition with up to ``max_levels=4`` partitions, boundaries were peaks of the combined p-value and the FDR was
    computed over the peaks only; results differ from the authors' (``docs/source/reference/changelog.md``).
    """

    window_bp: float = 1e5
    fdr_cutoff: float = 0.1
    method: str = "pval"
    hierarchical: bool = True
    min_tad_size: float = 0.0
    max_levels: Optional[int] = None
    prominence: Optional[float] = None
    distance: Optional[int] = None
    k_sigma: float = 4.0
    frac: float = 0.1


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def boundary_statistics(norm_var: np.ndarray, count: np.ndarray, starts: np.ndarray, weights: np.ndarray,
                        window_bp: float) -> dict:
    """Per-locus arc statistics (module docstring, steps 2-3) from ``(3, B, B)`` normalised variances / counts,
    the loci's ``starts`` (sorted) and the axis weights.  Returns arrays of length ``B``: ``stat_x/y/z`` (F),
    ``pval_x/y/z``, ``stat``, ``stat_prox``, ``pval`` (NaN where not tested)."""
    from scipy import stats

    B = len(starts)
    d = np.asarray(starts, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    out = {k: np.full(B, np.nan) for k in ("stat_x", "stat_y", "stat_z", "pval_x", "pval_y", "pval_z",
                                           "stat", "stat_prox", "pval")}
    with np.errstate(invalid="ignore", divide="ignore"):
        for i in range(B):
            if d[i] - d[0] < window_bp / 2 or d[-1] - d[i] < window_bp / 2:
                continue
            near = np.flatnonzero(np.abs(d - d[i]) <= window_bp)
            left, right = near[0], near[-1]
            iu_l = np.triu_indices(i - left, 1)
            iu_r = np.triu_indices(right - i, 1)
            ls, rs = slice(left, i), slice(i + 1, right + 1)
            lcount = count[:, ls, ls][:, iu_l[0], iu_l[1]].astype(np.float64)
            rcount = count[:, rs, rs][:, iu_r[0], iu_r[1]].astype(np.float64)
            intra = np.hstack([lcount, rcount]).sum(axis=1)
            lvar = norm_var[:, ls, ls][:, iu_l[0], iu_l[1]]
            rvar = norm_var[:, rs, rs][:, iu_r[0], iu_r[1]]
            num = np.nansum(np.hstack([lvar * (lcount / intra[:, None]), rvar * (rcount / intra[:, None])]), axis=1)
            cross = count[:, ls, rs].astype(np.float64)
            inter = cross.sum(axis=(1, 2))
            den = np.nansum(norm_var[:, ls, rs] * (cross / inter[:, None, None]), axis=(1, 2))
            f = num / den
            p = stats.f.cdf(f, intra, inter)
            stat = np.sum(w * np.tan((0.5 - p) * np.pi))
            stat_prox = np.sum(w * np.tan((0.5 - stats.f.cdf(f, 1, 1)) * np.pi))
            for a, c in enumerate("xyz"):
                out[f"stat_{c}"][i] = f[a]
                out[f"pval_{c}"][i] = p[a]
            out["stat"][i] = stat
            out["stat_prox"][i] = stat_prox
            out["pval"][i] = 1 - stats.cauchy.cdf(stat)
    return out


def median_distance_matrix(cd, chrom: str, device: str = "auto"):
    """``(B, B)`` median over the traces of the 3-D distance of every locus pair (a pair with a missing coordinate in
    a trace is left out for that trace) and the loci ``bin_ids`` (conventions of :mod:`uchrom.fea.arc`)."""
    import torch

    from uchrom.fea.arc import _coord_tensor, _diff_rows, _nanmedian_along_dim, _row_blocks

    c, bin_ids, _ = _coord_tensor(cd, chrom, device)
    B = c.shape[1]
    med = np.empty((B, B))
    for i0, i1 in _row_blocks(c):
        d = torch.sqrt((_diff_rows(c, i0, i1) ** 2).sum(dim=0))        # (T, b, B), NaN if an axis is missing
        med[i0:i1] = _nanmedian_along_dim(d, 0).detach().cpu().numpy().astype(np.float64)
    return med, bin_ids


def insulation_scores(med: np.ndarray, starts: np.ndarray, window_bp: float) -> np.ndarray:
    """The normalised insulation score of every locus (module docstring, ``method="insulation"``)."""
    d = np.asarray(starts, dtype=np.float64)
    B = len(d)
    out = np.zeros(B)
    for i in range(B):
        if d[i] - d[0] < window_bp / 2 or d[-1] - d[i] < window_bp / 2:
            continue
        near = np.flatnonzero(np.abs(d - d[i]) <= window_bp)
        left, right = near[0], near[-1]
        ls, rs = slice(left, i), slice(i + 1, right + 1)
        intra = np.concatenate([med[ls, ls][np.triu_indices(i - left, 1)], med[rs, rs][np.triu_indices(right - i, 1)]])
        inter = med[ls, rs].ravel()
        if np.all(np.isnan(intra)) or np.all(np.isnan(inter)):
            continue
        a, b = np.nanmedian(intra), np.nanmedian(inter)
        out[i] = (b - a) / (b + a)
    return out


def _domains(chrom: str, starts: np.ndarray, ends: np.ndarray, stat: np.ndarray, peak: np.ndarray,
             params: TADCallerParams) -> pd.DataFrame:
    """Domains of one chromosome from its boundary loci (module docstring, step 5)."""
    bnd = peak.copy()
    bnd[0] = bnd[-1] = True
    idx = list(np.flatnonzero(bnd))
    rows = [(a, b, 0) for a, b in zip(idx[:-1], idx[1:])]
    if params.hierarchical and len(idx) > 2:
        interior = sorted(idx[1:-1], key=lambda k: (stat[k], idx.index(k)))   # ascending, stable
        kept = list(idx)
        level = 0
        for k in interior:
            pos = kept.index(k)
            kept.pop(pos)
            level += 1
            rows.append((kept[pos - 1], kept[pos], level))
    df = pd.DataFrame({
        "chrom": chrom,
        "start": [int(starts[a]) for a, _, _ in rows],
        "end": [int(starts[b]) for _, b, _ in rows],
        "level": [lv for _, _, lv in rows],
        "start1": [int(starts[a]) for a, _, _ in rows], "end1": [int(ends[a]) for a, _, _ in rows],
        "start2": [int(starts[b]) for _, b, _ in rows], "end2": [int(ends[b]) for _, b, _ in rows],
        "stat1": [float(stat[a]) for a, _, _ in rows], "stat2": [float(stat[b]) for _, b, _ in rows],
    })
    df = df[(df["start2"] - df["start1"]) > params.min_tad_size]
    if params.max_levels is not None:
        df = df[df["level"] < params.max_levels]
    return df.reset_index(drop=True).astype({"start": "int64", "end": "int64", "level": "int64"})


def _preprocess(cd, chrom: str, params: TADCallerParams, device: str, verbose: bool, *, streaming: bool,
                batch, memory_budget) -> dict:
    """The normalised variance cube of one chromosome and its axis weights."""
    if params.method == "insulation":
        med, bin_ids = median_distance_matrix(cd, chrom, device)
        return {"median_distance": med, "bin_ids": bin_ids, "axis_weight": np.full(3, np.nan)}
    if verbose:
        print(f"[tad/{chrom}] variance cube{' (streaming)' if streaming else ''}...")
    if streaming:
        from uchrom.fea.arc_stream import axis_cube_streaming

        return axis_cube_streaming(cd, chrom, k_sigma=params.k_sigma, frac=params.frac, streaming=True,
                                   batch=batch, memory_budget=memory_budget)
    cube = axis_variance_cube(cd, chrom=chrom, device=device)
    return filter_normalize(cube, k_sigma=params.k_sigma, frac=params.frac)


def _stats_table(cube: dict, chrom: str, params: TADCallerParams) -> pd.DataFrame:
    """Per-locus statistics, FDR and boundary calls of one chromosome (``method="insulation"``: the insulation
    score and its peaks; ``cube`` then holds ``median_distance`` and ``bin_ids``)."""
    from scipy.signal import find_peaks

    bin_ids = cube["bin_ids"]
    if params.method == "insulation":
        starts = np.array([s for s, _ in bin_ids], dtype=np.int64)
        score = insulation_scores(cube["median_distance"], starts, params.window_bp)
        peak = np.zeros(len(starts), dtype=bool)
        peak[find_peaks(score, prominence=params.prominence, distance=params.distance)[0]] = True
        return pd.DataFrame({"chrom": chrom, "start": starts, "end": [e for _, e in bin_ids], "insulation": score,
                             "stat": score, "peak": peak})
    if params.method != "pval":
        raise ValueError(f"TADCallerParams.method must be 'pval' or 'insulation', got {params.method!r}")
    starts = np.array([s for s, _ in bin_ids], dtype=np.int64)
    ends = np.array([e for _, e in bin_ids], dtype=np.int64)
    st = boundary_statistics(cube["norm_var"], cube["count"], starts, cube["axis_weight"], params.window_bp)
    fdr = bh_fdr(st["pval"])
    raw_peak = np.zeros(len(starts), dtype=bool)
    raw_peak[find_peaks(st["stat_prox"], prominence=params.prominence, distance=params.distance)[0]] = True
    with np.errstate(invalid="ignore"):
        fdr_peak = fdr < params.fdr_cutoff
    return pd.DataFrame({"chrom": chrom, "start": starts, "end": ends, **st, "fdr": fdr,
                         "fdr_peak": fdr_peak, "raw_peak": raw_peak, "peak": raw_peak & fdr_peak})


def arcfish_boundary_stats(cd, *, chrom=None, trace_ids=None, cells=None, params: Optional[TADCallerParams] = None,
                           device: str = "auto", streaming: Optional[bool] = None, batch="auto",
                           memory_budget=None) -> pd.DataFrame:
    """The per-locus table of :func:`call_tads_by_pval` (not stored): ``chrom, start, end``, the per-axis F
    statistics ``stat_x/y/z`` and p-values ``pval_x/y/z``, ``stat``, ``stat_prox``, ``pval``, ``fdr`` and the
    boundary calls ``raw_peak`` (local maximum of ``stat_prox``), ``fdr_peak``, ``peak`` (both) — ArcFISH's
    ``TADCaller.by_pval`` table."""
    params = params or TADCallerParams()
    work = select_spots(cd, trace_ids=trace_ids, cells=cells)
    streaming = bool(getattr(work, "backed", False)) if streaming is None else bool(streaming)
    frames = [_stats_table(_preprocess(work, c, params, device, False, streaming=streaming, batch=batch,
                                       memory_budget=memory_budget), c, params)
              for c in resolve_chroms(work, chrom)]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


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
    """ArcFISH's TAD caller (chromatin tracing; module docstring).

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
        One row per domain (module docstring): ``chrom, start, end, level, start1, end1, start2, end2, stat1,
        stat2``.  Level 0 is the finest partition (every boundary); with ``params.hierarchical`` each further
        level is the domain merged by removing the next weakest boundary.

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
    cube = _preprocess(cd, chrom, params, device, verbose, streaming=streaming, batch=batch,
                       memory_budget=memory_budget)
    if verbose:
        print(f"[tad/{chrom}] axis weights: {np.round(cube['axis_weight'], 3)}")
    t = _stats_table(cube, chrom, params)
    if verbose:
        print(f"[tad/{chrom}] {int(t['peak'].sum())} boundaries (fdr < {params.fdr_cutoff})")
    if len(t) < 2:
        return _empty_tads()
    return _domains(chrom, t["start"].to_numpy(), t["end"].to_numpy(), t["stat"].to_numpy(),
                    t["peak"].to_numpy(), params)


def _empty_tads() -> pd.DataFrame:
    return pd.DataFrame({
        "chrom": pd.Series(dtype=str),
        "start": pd.Series(dtype="int64"),
        "end":   pd.Series(dtype="int64"),
        "level": pd.Series(dtype="int64"),
        "start1": pd.Series(dtype="int64"), "end1": pd.Series(dtype="int64"),
        "start2": pd.Series(dtype="int64"), "end2": pd.Series(dtype="int64"),
        "stat1": pd.Series(dtype="float64"), "stat2": pd.Series(dtype="float64"),
    })


__all__ = [
    "TADCallerParams",
    "call_tads_by_pval",
    "arcfish_boundary_stats",
    "boundary_statistics",
    "insulation_scores",
    "median_distance_matrix",
]
