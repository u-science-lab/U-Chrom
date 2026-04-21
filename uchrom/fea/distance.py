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

    bins = (
        df[["start", "end"]]
        .drop_duplicates()
        .sort_values("start", kind="mergesort")
        .reset_index(drop=True)
    )
    bin_ids = list(zip(bins["start"].tolist(), bins["end"].tolist()))
    bin_to_idx = {k: i for i, k in enumerate(bin_ids)}
    n_bins = len(bin_ids)

    trace_ids = list(df["trace_id"].unique())
    tid_to_idx = {t: i for i, t in enumerate(trace_ids)}
    n_traces = len(trace_ids)

    cube = np.full((n_traces, n_bins, 3), np.nan, dtype=np.float64)
    # Vectorised assignment via numpy indexing
    ti = df["trace_id"].map(tid_to_idx).to_numpy()
    bi = pd.Series(list(zip(df["start"], df["end"]))).map(bin_to_idx).to_numpy()
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
    "mean_distance_matrix",
    "contact_frequency",
    "radius_of_gyration",
]
