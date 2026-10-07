"""Spot-level preprocessing of imaging data."""

from __future__ import annotations

import numpy as np
import pandas as pd

_HOW = ("mean", "median", "first", "last")


def _group_reduce(values: np.ndarray, group: np.ndarray, n: int, how: str) -> np.ndarray:
    """Reduce the rows of ``values`` (n_rows, k) per group (0..n-1), NaN-aware, in row order."""
    values = np.asarray(values, dtype=np.float64)
    if how == "mean":
        ok = ~np.isnan(values)
        total = np.zeros((n, values.shape[1]))
        count = np.zeros((n, values.shape[1]))
        np.add.at(total, group, np.where(ok, values, 0.0))
        np.add.at(count, group, ok)
        with np.errstate(invalid="ignore", divide="ignore"):
            return total / count
    if how == "median":
        return pd.DataFrame(values).groupby(group, sort=True).median().reindex(range(n)).to_numpy()
    rows = pd.Series(np.arange(len(group))).groupby(group, sort=True)
    pick = (rows.first() if how == "first" else rows.last()).reindex(range(n)).to_numpy()
    return values[pick]


def merge_duplicate_spots(cd, *, how: str = "mean"):
    """One spot per (trace, locus): merge the spots of a trace that share a bin.

    Multiplexed DNA-FISH often detects a locus twice in one trace (sister chromatids, a stray spot);
    per-trace statistics then depend on which spot is used — :func:`uchrom.fea.distance_map` keeps the
    last one unless ``duplicates=`` says otherwise (the same reductions as here), the web browser averages
    them.  This merges them once, for every analysis that follows.

    Parameters
    ----------
    cd : ChromData
    how : ``"mean"`` (default), ``"median"``, ``"first"`` or ``"last"``
        How the coordinates, the ``layers`` and the numeric ``spot_tracks`` of a group are combined
        (NaN values are skipped by ``mean`` / ``median``); other spot columns keep the group's first
        value.

    Returns
    -------
    ChromData
        A new object (``cd`` is not modified) with one spot per (trace, bin), in the order of each
        group's first spot, and the spot column ``n_merged`` (spots per group); the locus axis, cells,
        traces and every other attribute are kept.
    """
    if how not in _HOW:
        raise ValueError(f"how must be one of {_HOW}, got {how!r}")
    sp = cd.spots
    trace = sp["trace_id"]
    tcode = trace.cat.codes.to_numpy() if hasattr(trace, "cat") else pd.factorize(trace)[0]
    key = tcode.astype(np.int64) * (int(cd.n_bins) + 1) + sp["bin_id"].to_numpy(dtype=np.int64)
    group, uniq = pd.factorize(key, sort=False)
    n = len(uniq)
    first = np.full(n, len(group), dtype=np.int64)
    np.minimum.at(first, group, np.arange(len(group)))
    size = np.bincount(group, minlength=n)

    out = cd[first]
    if np.array_equal(size, np.ones(n, dtype=size.dtype)):
        out.spots["n_merged"] = np.ones(n, dtype=np.int64)
        return out
    out.coords = _group_reduce(cd.coords, group, n, how)
    for name, arr in cd.layers.items():
        out.layers[name] = _group_reduce(np.asarray(arr), group, n, how)
    tracks = cd.spot_tracks
    if len(tracks.columns):
        merged = out.spot_tracks.copy()
        num = [c for c in tracks.columns if pd.api.types.is_numeric_dtype(tracks[c])
               and not pd.api.types.is_bool_dtype(tracks[c])]
        if num:
            merged[num] = _group_reduce(tracks[num].to_numpy(dtype=np.float64), group, n, how)
        out.spot_tracks = merged
    out.spots["n_merged"] = size.astype(np.int64)
    return out


__all__ = ["merge_duplicate_spots"]
