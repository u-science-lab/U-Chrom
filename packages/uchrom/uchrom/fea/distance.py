"""Distance-based aggregate statistics over a population of traces.

Input convention: a flat DataFrame with columns
``chrom, start, end, x, y, z, trace_id`` (what ``ChromData.to_dataframe()``
produces, or what the browser's :class:`ChromatinLayer.df` stores).

The core helper :func:`_bin_coord_cube` pivots the flat table into a
``(n_traces, n_bins, 3)`` array with NaN for missing spots, which lets
every aggregate statistic be computed as a straightforward NaN-aware
reduction.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _bin_coord_cube(df: pd.DataFrame, chrom=None):
    """Pivot a flat spots+coords table into a per-trace coordinate cube.

    Returns
    -------
    cube : ndarray, shape (n_traces, n_bins, 3)
        Coordinates with NaN where a trace is missing a bin.
    bin_ids : list of tuples
        ``(start, end)`` for each bin, sorted by ``start``.
    trace_ids : list
        Trace identifiers in cube axis-0 order.
    """
    required = {"chrom", "start", "end", "x", "y", "z", "trace_id"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"DataFrame missing columns: {missing}")

    if chrom is not None:
        df = df[df["chrom"].astype(str) == str(chrom)]
    if df.empty:
        raise ValueError("No rows after filtering; cannot compute cube.")

    # Coerce start/end to int so dict-key lookups don't fall over float.
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
    bin_ids = [(int(s), int(e)) for s, e in zip(bins["start"], bins["end"])]
    bin_to_idx = {k: i for i, k in enumerate(bin_ids)}
    n_bins = len(bin_ids)

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
    return cube, bin_ids, trace_ids


def _pairwise_distance_per_trace(cube: np.ndarray) -> np.ndarray:
    """Return a (n_traces, n_bins, n_bins) Euclidean distance tensor.

    Missing spots propagate as NaN distances.
    """
    diff = cube[:, :, None, :] - cube[:, None, :, :]
    return np.sqrt(np.sum(diff ** 2, axis=-1))


def mean_distance_matrix(
    df: pd.DataFrame,
    chrom=None,
    reduce: str = "median",
):
    """Population-level mean/median pairwise distance matrix.

    For each pair of genomic bins ``(i, j)``, the distance is computed
    per-trace and then reduced across traces with ``np.nanmedian`` (the
    Bintu 2018 convention) or ``np.nanmean``.

    Parameters
    ----------
    df : DataFrame with spots + coords.
    chrom : optional chromosome filter.
    reduce : 'median' (default) or 'mean'.

    Returns
    -------
    matrix : ndarray (n_bins, n_bins)
    bin_ids : list of (start, end)
    n_traces : int
    """
    cube, bin_ids, trace_ids = _bin_coord_cube(df, chrom=chrom)
    dist = _pairwise_distance_per_trace(cube)
    if reduce == "mean":
        agg = np.nanmean(dist, axis=0)
    else:
        agg = np.nanmedian(dist, axis=0)
    return agg, bin_ids, len(trace_ids)


class DistanceMap(dict):
    """Result of :func:`distance_map` (a dict with attribute access):
    ``matrix`` (n_bins × n_bins), ``count`` (traces observing each pair;
    the diagonal counts the traces observing the bin), ``bins`` (``bin_id``,
    ``chrom``, ``start``, ``end`` of the rows), ``n_traces``, ``stat``,
    ``streaming``, ``n_passes`` (reads of the chromosome's traces) and
    ``n_bands``."""

    __getattr__ = dict.__getitem__


def distance_map(cd, chrom, stat: str = "median", *, streaming=None, batch="auto",
                 memory_budget=None, observed: bool = True) -> DistanceMap:
    """Population median / mean 3-D distance of every bin pair of one
    chromosome — exact, in memory or streaming over the traces.

    Same definition as :func:`mean_distance_matrix` (per trace, the
    Euclidean distance of its two spots; NaN / missing spots skipped; a
    trace observing a bin twice keeps its last spot), but without the dense
    ``(n_traces, n_bins, n_bins)`` tensor, so it runs on genome-wide data:

    * ``stat="mean"`` accumulates per-pair sums and counts in trace order
      (``np.add.at``) — the additions the dense ``np.nanmean`` makes, in the
      same order, so the result is bitwise identical (``float64``); memory
      ``O(n_bins²)``.
    * ``stat="median"`` is an **exact** median (the mean of the two middle
      values for an even count, as ``np.nanmedian``).  An exact median needs
      all values of a pair at once, so the observations are gathered for one
      *row band* of the matrix at a time — the rows ``i`` whose pairs
      ``(i, j > i)`` fit ``memory_budget`` (``BYTES_PER_OBS`` bytes each) —
      and reduced with a grouped median (pandas).  A band costs one pass over
      the chromosome's traces; memory is the band plus the ``n_bins²``
      output, independent of the number of traces.  No approximation.

    Parameters
    ----------
    cd : ChromData, in memory or backed
    chrom : chromosome name
    stat : ``"median"`` or ``"mean"``
    streaming : bool, optional
        Read the traces in batches (``iter_traces(chrom=..., columns="coords")``) and band the
        median; default ``True`` for a backed object.  ``False`` gathers every observation at once
        (the in-memory baseline).
    batch : int or "auto"
        Traces per batch, or ``"auto"`` (from the memory budget).
    memory_budget : default :data:`uchrom.settings.memory_budget`
    observed : rows / columns = the chromosome's observed bins sorted by
        start (the :func:`mean_distance_matrix` convention), or every bin of
        the chromosome in ``cd.bins``

    Returns
    -------
    DistanceMap
    """
    from uchrom.utils.memory import release_memory

    from ._pairs import BYTES_PER_OBS, MAX_BLOCK_PAIRS, ChromPairs, pair_distance

    if stat not in ("median", "mean"):
        raise ValueError("stat must be 'median' or 'mean'")
    P = ChromPairs(cd, chrom, streaming=streaming, batch=batch, observed=observed,
                   memory_budget=memory_budget)
    P.prepare()
    B = P.n_bins
    passes = 1
    idx_dtype = np.int32 if B * B < 2 ** 31 else np.int64
    count = np.zeros(B * B, dtype=np.int32)
    out = np.full(B * B, np.nan)
    if stat == "mean":
        total = np.zeros(B * B, dtype=np.float64)
        for i, j, ci, cj in P.pairs():
            idx = i * B + j
            np.add.at(total, idx, pair_distance(ci, cj))
            np.add.at(count, idx, 1)
        passes += 1
        n_bands = 1
        with np.errstate(invalid="ignore", divide="ignore"):
            np.divide(total, count, out=out, where=count > 0)
        del total
    else:
        # the n_bins² outputs, a block of pairs, a batch of traces
        fixed = B * B * 12 + MAX_BLOCK_PAIRS * 100 + int(0.1 * P.memory_budget)
        bands = P.bands(BYTES_PER_OBS, fixed_bytes=fixed)
        n_bands = len(bands)
        for lo, hi in bands:
            n_obs = int(P.row_counts[lo:hi].sum())
            if not n_obs:
                continue
            idx = np.empty(n_obs, dtype=idx_dtype)
            d = np.empty(n_obs, dtype=np.float64)
            pos = 0
            for i, j, ci, cj in P.pairs(lo, hi):
                m = len(i)
                idx[pos:pos + m] = i * B + j
                d[pos:pos + m] = pair_distance(ci, cj)
                pos += m
            passes += 1
            if pos != n_obs:  # pragma: no cover - the two passes must agree
                raise RuntimeError(f"pair count changed between passes ({pos} != {n_obs})")
            g = pd.Series(d, copy=False).groupby(idx, sort=True)
            med = g.median()
            del d
            keys = med.index.to_numpy()
            out[keys] = med.to_numpy()
            count[keys] = g.size().to_numpy()
            del g, med, idx, keys
            release_memory()
    mat = out.reshape(B, B)
    cnt = count.reshape(B, B)
    for i in range(B - 1):                 # mirror the upper triangle, in place
        mat[i + 1:, i] = mat[i, i + 1:]
        cnt[i + 1:, i] = cnt[i, i + 1:]
    diag = np.arange(B)
    cnt[diag, diag] = P.bin_counts
    mat[diag, diag] = np.where(P.bin_counts > 0, 0.0, np.nan)
    return DistanceMap(matrix=mat, count=cnt, bins=P.bin_table(), n_traces=int(P.n_traces),
                       stat=stat, streaming=P.streaming, n_passes=passes, n_bands=n_bands,
                       chrom=str(chrom))


def contact_frequency(
    df: pd.DataFrame,
    threshold: float,
    chrom=None,
):
    """Fraction of traces where a pair of bins are within ``threshold``.

    NaN distances (missing spots) are excluded from both numerator and
    denominator — each bin pair's frequency is over the set of traces
    that have both endpoints detected.

    Parameters
    ----------
    df : DataFrame with spots + coords.
    threshold : distance threshold in the same units as x/y/z.
    chrom : optional chromosome filter.

    Returns
    -------
    frequency : ndarray (n_bins, n_bins) in [0, 1], NaN where no
        trace had both endpoints detected.
    bin_ids : list of (start, end)
    n_traces : int
    """
    cube, bin_ids, trace_ids = _bin_coord_cube(df, chrom=chrom)
    dist = _pairwise_distance_per_trace(cube)
    valid = ~np.isnan(dist)
    contact = np.where(valid, dist < threshold, False)
    n_contacts = contact.sum(axis=0)
    n_valid = valid.sum(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        freq = np.where(n_valid > 0, n_contacts / n_valid, np.nan)
    return freq, bin_ids, len(trace_ids)


def radius_of_gyration(df: pd.DataFrame, chrom=None) -> pd.Series:
    """Per-trace radius of gyration.

    ``Rg = sqrt(mean over spots of ||r - centroid||²)``.  Traces with
    fewer than 2 spots contribute NaN.
    """
    if chrom is not None:
        df = df[df["chrom"].astype(str) == str(chrom)]
    rgs = {}
    for tid, sdf in df.groupby("trace_id", observed=True):
        pos = sdf[["x", "y", "z"]].to_numpy()
        if pos.shape[0] < 2:
            rgs[tid] = np.nan
            continue
        centroid = pos.mean(axis=0)
        rgs[tid] = float(np.sqrt(np.mean(np.sum((pos - centroid) ** 2, axis=1))))
    return pd.Series(rgs, name="rg").sort_index()


__all__ = [
    "DistanceMap",
    "distance_map",
    "mean_distance_matrix",
    "contact_frequency",
    "radius_of_gyration",
]
