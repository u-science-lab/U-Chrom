"""The locus axis of ``ChromData`` — ``bins`` and ``spots.bin_id``.

``bins`` is a DataFrame indexed by ``bin_id`` (``0 .. n_bins-1``) with
columns ``chrom`` (category), ``start`` / ``end`` (int64) and optional
``resolution`` / ``name`` / any extra per-locus column.  Every spot points
at one bin through ``spots["bin_id"]``; tracing designs with irregular
probes simply get an irregular bin table (one row per probe locus).

Helpers here derive bins from spot loci, map loci onto an existing bin
table, and split a 1.x spot-aligned ``tracks`` table into bin-level and
spot-level parts.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

LOCI = ("chrom", "start", "end")
BIN_ID = "bin_id"


def _as_int64(values, name: str) -> np.ndarray:
    arr = pd.to_numeric(pd.Series(values), errors="raise")
    if arr.isna().any():
        raise ValueError(f"{name} contains missing values; every spot / bin needs a locus")
    out = arr.to_numpy()
    if out.dtype.kind == "f":
        if not np.all(np.mod(out, 1) == 0):
            raise ValueError(f"{name} must hold integer positions")
    return out.astype(np.int64)


def _chrom_categorical(values, categories: Optional[Sequence] = None) -> pd.Categorical:
    """Chromosome names as a categorical.  Categories: the given ones, the
    input's own (if already categorical), else sorted unique names — the
    same as ``astype("category")`` in 1.x."""
    if categories is not None:
        return pd.Categorical(pd.Series(values).astype(str), categories=list(categories))
    if isinstance(getattr(values, "dtype", None), pd.CategoricalDtype):
        cats = [str(c) for c in values.cat.categories] if hasattr(values, "cat") else \
            [str(c) for c in values.categories]
        return pd.Categorical(pd.Series(values).astype(str), categories=cats)
    return pd.Categorical(pd.Series(values).astype(str))


def empty_bins() -> pd.DataFrame:
    out = pd.DataFrame({
        "chrom": pd.Categorical([]),
        "start": pd.Series([], dtype=np.int64),
        "end": pd.Series([], dtype=np.int64),
    })
    out.index = pd.RangeIndex(0, name=BIN_ID)
    return out


def normalise_bins(bins: pd.DataFrame) -> pd.DataFrame:
    """Validate a bin table and return it in canonical form (a copy)."""
    if not isinstance(bins, pd.DataFrame):
        raise TypeError(f"bins must be a DataFrame, got {type(bins).__name__}")
    missing = [c for c in LOCI if c not in bins.columns]
    if missing:
        raise ValueError(f"bins missing required column(s): {missing}")
    out = bins.copy()
    idx = out.index
    trivial = isinstance(idx, pd.RangeIndex) and idx.start == 0 and idx.step == 1
    if not trivial:
        vals = np.asarray(idx)
        if vals.dtype.kind not in "iu" or not np.array_equal(vals, np.arange(len(out))):
            raise ValueError("bins index (bin_id) must be 0 .. n_bins-1 in order")
    out.index = pd.RangeIndex(len(out), name=BIN_ID)
    out["chrom"] = _chrom_categorical(out["chrom"])
    out["start"] = _as_int64(out["start"], "bins.start")
    out["end"] = _as_int64(out["end"], "bins.end")
    if len(out) and (out["end"].to_numpy() <= out["start"].to_numpy()).any():
        bad = out[out["end"] <= out["start"]].head(3)
        raise ValueError(f"bins must satisfy end > start: {bad[list(LOCI)].to_dict('records')}")
    if out.duplicated(list(LOCI)).any():
        dup = out[out.duplicated(list(LOCI), keep=False)].head(4)
        raise ValueError(f"bins contain duplicate loci: {dup[list(LOCI)].to_dict('records')}")
    return out


def bins_from_loci(spots: pd.DataFrame) -> Tuple[pd.DataFrame, np.ndarray]:
    """Unique ``(chrom, start, end)`` of ``spots`` → ``(bins, bin_id)``.

    Bins are ordered by chromosome (category order), then start, then end.
    """
    missing = [c for c in LOCI if c not in spots.columns]
    if missing:
        raise ValueError(
            f"spots needs either 'bin_id' (with bins=) or the locus columns "
            f"{list(LOCI)}; missing {missing}"
        )
    if len(spots) == 0:
        return empty_bins(), np.zeros(0, dtype=np.int64)
    chrom = _chrom_categorical(spots["chrom"])
    frame = pd.DataFrame({
        "c": chrom.codes.astype(np.int64),
        "s": _as_int64(spots["start"], "spots.start"),
        "e": _as_int64(spots["end"], "spots.end"),
    })
    if (frame["c"] < 0).any():
        raise ValueError("spots.chrom contains missing values")
    grouped = frame.groupby(["c", "s", "e"], sort=True)
    bin_id = grouped.ngroup().to_numpy(dtype=np.int64)
    keys = grouped.size().index.to_frame(index=False)
    bins = pd.DataFrame({
        "chrom": pd.Categorical.from_codes(keys["c"].to_numpy(), categories=chrom.categories),
        "start": keys["s"].to_numpy(dtype=np.int64),
        "end": keys["e"].to_numpy(dtype=np.int64),
    })
    bins.index = pd.RangeIndex(len(bins), name=BIN_ID)
    return bins, bin_id


def map_loci_to_bins(spots: pd.DataFrame, bins: pd.DataFrame) -> np.ndarray:
    """``bin_id`` of every spot locus; ``-1`` where the locus is not a bin."""
    if len(spots) == 0:
        return np.zeros(0, dtype=np.int64)
    key_b = pd.MultiIndex.from_arrays([
        bins["chrom"].astype(str).to_numpy(),
        bins["start"].to_numpy(dtype=np.int64),
        bins["end"].to_numpy(dtype=np.int64),
    ])
    key_s = pd.MultiIndex.from_arrays([
        spots["chrom"].astype(str).to_numpy(),
        _as_int64(spots["start"], "spots.start"),
        _as_int64(spots["end"], "spots.end"),
    ])
    return np.asarray(key_b.get_indexer(key_s), dtype=np.int64)


def loci_of(bins: pd.DataFrame, bin_id: np.ndarray) -> dict:
    """Spot-aligned ``chrom`` (categorical) / ``start`` / ``end`` columns."""
    bin_id = np.asarray(bin_id, dtype=np.int64)
    chrom = bins["chrom"].cat
    return {
        "chrom": pd.Categorical.from_codes(
            np.asarray(chrom.codes)[bin_id] if len(bin_id) else np.zeros(0, dtype=np.int8),
            categories=chrom.categories),
        "start": bins["start"].to_numpy(dtype=np.int64)[bin_id],
        "end": bins["end"].to_numpy(dtype=np.int64)[bin_id],
    }


def constant_per_bin(values: pd.Series, bin_id: np.ndarray, order: np.ndarray) -> bool:
    """True if every spot sharing a bin has the same value (NaN == NaN)."""
    if len(values) < 2:
        return True
    b = bin_id[order]
    same_bin = b[1:] == b[:-1]
    if not same_bin.any():
        return True
    s = values.iloc[order].reset_index(drop=True)
    a, c = s.iloc[1:].reset_index(drop=True), s.iloc[:-1].reset_index(drop=True)
    eq = (a == c).to_numpy(dtype=bool, na_value=False) | (a.isna() & c.isna()).to_numpy()
    return bool(eq[same_bin].all())


def split_spot_tracks(
    tracks: pd.DataFrame, bin_id: np.ndarray, n_bins: int,
) -> Tuple[pd.DataFrame, pd.DataFrame, List[str]]:
    """Split a spot-aligned 1.x ``tracks`` table.

    Columns whose value is the same for every spot of a bin move to a
    bin-level table (``n_bins`` rows; bins without spots are NaN); the
    rest stay spot-level.  Returns ``(bin_tracks, spot_tracks, order)``
    where ``order`` is the original column order.
    """
    bin_id = np.asarray(bin_id, dtype=np.int64)
    order = np.argsort(bin_id, kind="stable")
    bin_cols, spot_cols = [], []
    for col in tracks.columns:
        (bin_cols if constant_per_bin(tracks[col], bin_id, order) else spot_cols).append(col)
    first = np.full(n_bins, -1, dtype=np.int64)
    if len(bin_id):
        uniq, pos = np.unique(bin_id[order], return_index=True)
        first[uniq] = order[pos]
    observed = first >= 0
    bin_tracks = pd.DataFrame(index=pd.RangeIndex(n_bins, name=BIN_ID))
    for col in bin_cols:
        src = tracks[col]
        if observed.all():
            vals = src.iloc[first].to_numpy()
            bin_tracks[col] = pd.Series(vals, index=bin_tracks.index, dtype=src.dtype)
        else:
            full = pd.Series(index=bin_tracks.index, dtype=object if src.dtype == object else None)
            full.iloc[np.where(observed)[0]] = src.iloc[first[observed]].to_numpy()
            bin_tracks[col] = full
    spot_tracks = tracks[spot_cols].reset_index(drop=True)
    return bin_tracks, spot_tracks, [str(c) for c in tracks.columns]


__all__ = [
    "BIN_ID",
    "LOCI",
    "bins_from_loci",
    "empty_bins",
    "loci_of",
    "map_loci_to_bins",
    "normalise_bins",
    "split_spot_tracks",
]
