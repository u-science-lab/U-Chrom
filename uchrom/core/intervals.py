"""Typed genomic interval tables — ``cd.intervals``.

``cd.intervals`` maps a key (``"tads.arcfish"``, ``"loops.axiswise_f"``,
…) to an :class:`IntervalTable`: a ``pandas.DataFrame`` whose
``attrs["kind"]`` declares its schema and whose ``attrs["source_result"]``
names the ``cd.results`` record that produced it (if any).

========= ============================================== ======================
kind      required columns                               examples
========= ============================================== ======================
domain    ``chrom, start, end``                          TADs, FISHnet domains
pair      ``chrom1, start1, end1, chrom2, start2, end2`` loops
peak      ``chrom, start, end`` (+ summit, score, …)     MACS peaks
segment   ``chrom, start, end, label``                   A/B compartment runs
========= ============================================== ======================

Tables are validated when assigned.  :meth:`IntervalTable.to_bins` maps
intervals onto a bin table (``cd.bins``).
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Dict, Iterator, Optional

import numpy as np
import pandas as pd

INTERVAL_KINDS: Dict[str, tuple] = {
    "domain": ("chrom", "start", "end"),
    "pair": ("chrom1", "start1", "end1", "chrom2", "start2", "end2"),
    "peak": ("chrom", "start", "end"),
    "segment": ("chrom", "start", "end", "label"),
}


def infer_interval_kind(df: pd.DataFrame) -> str:
    cols = set(df.columns)
    if {"chrom1", "start1", "end1"} <= cols:
        return "pair"
    if "label" in cols:
        return "segment"
    if "summit" in cols:
        return "peak"
    return "domain"


class IntervalTable(pd.DataFrame):
    """A DataFrame of genomic intervals with a declared ``kind``."""

    @property
    def _constructor(self):
        return IntervalTable

    @property
    def kind(self) -> Optional[str]:
        return self.attrs.get("kind")

    @property
    def source_result(self) -> Optional[str]:
        return self.attrs.get("source_result")

    @classmethod
    def from_frame(cls, df: pd.DataFrame, kind: Optional[str] = None,
                   source_result: Optional[str] = None) -> "IntervalTable":
        """Validate ``df`` and wrap it (the data is not copied when ``df``
        already is an ``IntervalTable``)."""
        table = df if isinstance(df, IntervalTable) else cls(df)
        kind = kind or table.attrs.get("kind") or infer_interval_kind(table)
        validate_intervals(table, kind)
        table.attrs["kind"] = kind
        if source_result is not None:
            table.attrs["source_result"] = source_result
        return table

    def to_bins(self, bins: pd.DataFrame, how: str = "id", column: Optional[str] = None) -> pd.Series:
        """Map intervals onto ``bins`` (``cd.bins``).

        Parameters
        ----------
        how : ``"id" | "bool" | "count"``
            ``"id"`` — row position of the interval with the largest
            overlap (``-1`` for none); ``"bool"`` — any overlap;
            ``"count"`` — number of overlapping intervals.  For ``pair``
            tables both anchors count.
        column : str, optional
            With ``how="id"``, return this column of the best interval
            instead of its row position (NaN / None where no overlap),
            e.g. ``column="label"`` for compartment segments.
        """
        if how not in ("id", "bool", "count"):
            raise ValueError("how must be 'id', 'bool' or 'count'")
        best, count = _overlap(self, bins)
        index = bins.index
        if how == "bool":
            return pd.Series(count > 0, index=index, name=self.attrs.get("source_result"))
        if how == "count":
            return pd.Series(count, index=index)
        if column is None:
            return pd.Series(best, index=index)
        vals = self[column].to_numpy()
        out = pd.Series([vals[b] if b >= 0 else None for b in best], index=index, name=column,
                        dtype=object)
        if pd.api.types.is_numeric_dtype(self[column]):
            out = out.astype(float)
        return out


def validate_intervals(df: pd.DataFrame, kind: str) -> None:
    if kind not in INTERVAL_KINDS:
        raise ValueError(f"unknown interval kind {kind!r}; expected one of {sorted(INTERVAL_KINDS)}")
    required = INTERVAL_KINDS[kind]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{kind} intervals missing column(s): {missing}")
    anchors = [("start1", "end1"), ("start2", "end2")] if kind == "pair" else [("start", "end")]
    for s, e in anchors:
        for col in (s, e):
            if len(df) and not pd.api.types.is_numeric_dtype(df[col]):
                raise TypeError(f"{kind} intervals: column {col!r} must be numeric")
        if len(df):
            sv, ev = df[s].to_numpy(dtype=float), df[e].to_numpy(dtype=float)
            if np.isnan(sv).any() or np.isnan(ev).any():
                raise ValueError(f"{kind} intervals: {s}/{e} contain missing values")
            if (ev < sv).any():
                raise ValueError(f"{kind} intervals must satisfy {e} >= {s}")


def _anchor_frames(table: pd.DataFrame):
    if table.attrs.get("kind") == "pair" or "chrom1" in table.columns:
        rows = np.arange(len(table))
        for i in ("1", "2"):
            yield rows, table[f"chrom{i}"].astype(str).to_numpy(), \
                table[f"start{i}"].to_numpy(dtype=np.int64), table[f"end{i}"].to_numpy(dtype=np.int64)
    else:
        yield np.arange(len(table)), table["chrom"].astype(str).to_numpy(), \
            table["start"].to_numpy(dtype=np.int64), table["end"].to_numpy(dtype=np.int64)


def _overlap(table: pd.DataFrame, bins: pd.DataFrame, chunk: int = 4_000_000):
    """Per bin: row of the best-overlapping interval and the overlap count."""
    n = len(bins)
    best = np.full(n, -1, dtype=np.int64)
    best_bp = np.zeros(n, dtype=np.int64)
    count = np.zeros(n, dtype=np.int64)
    if n == 0 or len(table) == 0:
        return best, count
    b_chrom = bins["chrom"].astype(str).to_numpy()
    b_start = bins["start"].to_numpy(dtype=np.int64)
    b_end = bins["end"].to_numpy(dtype=np.int64)
    for rows, chrom, start, end in _anchor_frames(table):
        for c in np.unique(chrom):
            bi = np.where(b_chrom == c)[0]
            ii = np.where(chrom == c)[0]
            if not len(bi) or not len(ii):
                continue
            step = max(1, chunk // len(ii))
            for k in range(0, len(bi), step):
                bb = bi[k:k + step]
                ov = np.minimum(b_end[bb, None], end[None, ii]) - np.maximum(b_start[bb, None], start[None, ii])
                hit = ov > 0
                count[bb] += hit.sum(axis=1)
                j = np.argmax(np.where(hit, ov, -1), axis=1)
                bp = ov[np.arange(len(bb)), j]
                better = hit.any(axis=1) & (bp > best_bp[bb])
                best[bb[better]] = rows[ii[j[better]]]
                best_bp[bb[better]] = bp[better]
    return best, count


class IntervalStore(MutableMapping):
    """``cd.intervals`` — validated ``key -> IntervalTable``."""

    def __init__(self, data=None):
        self._tables: Dict[str, IntervalTable] = {}
        for key, value in (data or {}).items():
            self[key] = value

    @classmethod
    def coerce(cls, data) -> "IntervalStore":
        if isinstance(data, IntervalStore):
            return data
        return cls(data)

    def __getitem__(self, key: str) -> IntervalTable:
        return self._tables[str(key)]

    def __setitem__(self, key: str, value: pd.DataFrame) -> None:
        key = str(key)
        if "/" in key or key in ("", "."):
            raise ValueError(f"interval keys must be non-empty and contain no '/': {key!r}")
        if not isinstance(value, pd.DataFrame):
            raise TypeError(f"cd.intervals[{key!r}] must be a DataFrame, got {type(value).__name__}")
        self._tables[key] = IntervalTable.from_frame(value)

    def add(self, key: str, value: pd.DataFrame, *, kind: Optional[str] = None,
            source_result: Optional[str] = None) -> IntervalTable:
        """Store ``value`` as a ``kind`` interval table and return it."""
        table = IntervalTable.from_frame(value, kind=kind, source_result=source_result)
        self[key] = table
        return table

    def __delitem__(self, key: str) -> None:
        del self._tables[str(key)]

    def __iter__(self) -> Iterator[str]:
        return iter(self._tables)

    def __len__(self) -> int:
        return len(self._tables)

    def __repr__(self) -> str:
        inner = ", ".join(f"{k!r}: <{t.kind}, {len(t)} rows>" for k, t in self._tables.items())
        return f"IntervalStore({{{inner}}})"

    def to_bins(self, key: str, bins: pd.DataFrame, **kwargs) -> pd.Series:
        return self[key].to_bins(bins, **kwargs)


__all__ = [
    "INTERVAL_KINDS",
    "IntervalStore",
    "IntervalTable",
    "infer_interval_kind",
    "validate_intervals",
]
