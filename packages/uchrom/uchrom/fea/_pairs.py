"""Per-trace bin-pair observations, streamed over a chromosome's traces.

The population statistics of chromatin tracing (median / mean distance
maps, the ArcFISH axis-variance cube) are reductions over *pair
observations*: for every trace and every pair of bins ``i < j`` it observed,
one value (a distance, or a per-axis coordinate difference).  Materialising
them as a dense ``(n_traces, n_bins, n_bins)`` tensor is what makes the
in-memory callers run out of memory; here they are generated chunk by chunk
from ``cd.iter_traces(chrom=..., columns="coords")`` and, when an exact order
statistic is needed, for one **row band** of the matrix at a time (the rows
``i`` in ``[lo, hi)``), so the values held at once fit a memory budget.

Conventions (the same as the dense ``_coord_cube_for_chrom`` /
``_bin_coord_cube`` pivots):

* a trace is a (cell, trace) run of the stored order — traces are visited in
  that order (chromosome › cell › trace), spots in bin order;
* a trace that observes a bin more than once keeps its **last** spot there
  (a dense cube keeps the last write);
* the bins of a matrix are the chromosome's *observed* bins, sorted by
  start (``observed=True``, the dense convention) or all bins of the
  chromosome in ``cd.bins`` (``observed=False``).
"""

from __future__ import annotations

from typing import Iterator, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from chromdata.bins import BIN_ID

#: bytes of working memory per pair observation held in a band (value and
#: pair index, 12 bytes, plus the group-by temporaries of pandas; measured
#: ~60 on the Takei 2025 data)
BYTES_PER_OBS = 80
#: pairs generated at a time (their transient arrays take ~100 bytes each)
MAX_BLOCK_PAIRS = 1 << 21


class ChromPairs:
    """Pair observations of one chromosome of a ``ChromData``.

    Parameters
    ----------
    cd : ChromData (in memory or backed)
    chrom : chromosome name
    streaming : read the traces in batches (``cd.iter_traces``) instead of
        all at once.  Default: ``True`` for a backed object.
    batch : traces per batch (``"auto"`` from the memory budget)
    observed : matrix bins = observed bins (dense convention) or all bins
        of the chromosome
    memory_budget : bytes / string; default :data:`uchrom.settings.memory_budget`
    """

    def __init__(self, cd, chrom: str, *, streaming: Optional[bool] = None, batch="auto",
                 observed: bool = True, memory_budget=None):
        from uchrom.settings import settings

        self.cd = cd
        self.chrom = str(chrom)
        self.streaming = bool(getattr(cd, "backed", False)) if streaming is None else bool(streaming)
        self.batch = batch
        self.memory_budget = settings.resolve_budget(memory_budget)
        bins = cd.bins
        names = np.asarray(bins["chrom"].astype(str))
        chrom_ids = np.flatnonzero(names == self.chrom)
        if not len(chrom_ids):
            raise ValueError(f"No spots found for chromosome {chrom}")
        self.observed = observed
        self._chrom_ids = chrom_ids
        self._lookup: Optional[np.ndarray] = None
        self.bin_ids: Optional[np.ndarray] = None          # global bin ids of the matrix rows
        if not observed:
            self._set_bins(chrom_ids)
        self.n_traces = None

    # -- bins ----------------------------------------------------------------

    def _set_bins(self, ids: np.ndarray) -> None:
        bins = self.cd.bins
        order = np.lexsort((bins["end"].to_numpy()[ids], bins["start"].to_numpy()[ids]))
        ids = np.asarray(ids)[order]
        self.bin_ids = ids
        self._lookup = np.full(len(bins), -1, dtype=np.int64)
        self._lookup[ids] = np.arange(len(ids))

    @property
    def n_bins(self) -> int:
        return len(self.bin_ids)

    def bin_table(self) -> pd.DataFrame:
        """``chrom, start, end`` (+ ``bin_id``) of the matrix rows."""
        b = self.cd.bins.iloc[self.bin_ids]
        out = b[["chrom", "start", "end"]].reset_index()
        return out

    def bin_intervals(self) -> List[Tuple[int, int]]:
        b = self.cd.bins
        return [(int(s), int(e)) for s, e in zip(b["start"].to_numpy()[self.bin_ids],
                                                 b["end"].to_numpy()[self.bin_ids])]

    # -- chunks --------------------------------------------------------------

    def chunks(self) -> Iterator[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
        """``(bin index, coords, run offsets)`` per chunk: rows in stored
        order with duplicates (same trace, same bin) reduced to the last."""
        cd = self.cd
        if self.streaming:
            batch = self.batch
            if isinstance(batch, str):
                # a tenth of the budget for a batch of decoded coordinates
                # (~150 bytes per spot: Arrow, pandas and ChromData copies)
                per_trace = 150.0 * max(1.0, cd.n_spots / max(1, _n_runs(cd)))
                batch = max(1, int(self.memory_budget * 0.1 // per_trace))
            it = cd.iter_traces(batch, chrom=self.chrom, columns="coords")
        else:
            n_runs = max(1, _n_runs(cd))
            it = cd.iter_traces(n_runs, chrom=self.chrom, columns="coords")
        for chunk in it:
            yield self._arrays(chunk)

    def _arrays(self, chunk):
        s = chunk.spots
        n = len(s)
        if n == 0:
            return np.zeros(0, np.int64), np.zeros((0, 3)), np.zeros(1, np.int64)
        bid = s[BIN_ID].to_numpy().astype(np.int64)
        trace = np.asarray(s["trace_id"].cat.codes, dtype=np.int64)
        cell = (np.asarray(s["cell_id"].cat.codes, dtype=np.int64) if "cell_id" in s.columns
                else np.zeros(n, dtype=np.int64))
        new_run = np.r_[True, (trace[1:] != trace[:-1]) | (cell[1:] != cell[:-1])]
        # last spot of a (run, bin): the next row is another run or another bin
        last = np.r_[(bid[1:] != bid[:-1]) | new_run[1:], True]
        coords = np.asarray(chunk.coords, dtype=np.float64)
        if not last.all():
            bid, coords, new_run = bid[last], coords[last], _first_of_runs(new_run, last)
        runs = np.r_[np.flatnonzero(new_run), len(bid)].astype(np.int64)
        return bid, coords, runs

    def prepare(self) -> None:
        """Pass 0: the observed bins (when ``observed``), the number of
        traces, the finite spots per bin (``bin_counts``, the diagonal of the
        count matrix) and the pair observations per row (``row_counts``)."""
        if self.n_traces is not None:
            return
        n_all = len(self.cd.bins)
        seen = np.zeros(n_all, dtype=bool)
        rows = np.zeros(n_all, dtype=np.int64)
        diag = np.zeros(n_all, dtype=np.int64)
        n_traces = 0
        for bid, coords, runs in self.chunks():
            seen[bid] = True
            n_traces += len(runs) - 1
            ok = np.isfinite(coords).all(axis=1)
            b2, runs2 = _drop_rows(bid, runs, ok)
            np.add.at(diag, b2, 1)
            np.add.at(rows, b2, _remaining(runs2, len(b2)))
        self.n_traces = n_traces
        if self.bin_ids is None:
            self._set_bins(np.flatnonzero(seen))
        self.bin_counts = diag[self.bin_ids]
        self.row_counts = rows[self.bin_ids]

    def local(self, bid: np.ndarray) -> np.ndarray:
        return self._lookup[bid]

    # -- pairs ---------------------------------------------------------------

    def bands(self, bytes_per_obs: float = BYTES_PER_OBS, fixed_bytes: int = 0) -> List[Tuple[int, int]]:
        """Row bands ``[lo, hi)`` whose pair observations fit the memory
        budget less ``fixed_bytes`` (outputs, pair blocks; at least a quarter
        of the budget is left for a band) — one band, every row, when not
        streaming."""
        self.prepare()
        counts = self.row_counts
        if not self.streaming:
            return [(0, len(counts))]
        room = max(self.memory_budget - int(fixed_bytes), self.memory_budget // 4)
        cap = max(1, int(room // max(1.0, bytes_per_obs)))
        out = []
        lo = 0
        acc = 0
        for i, c in enumerate(counts):
            if acc and acc + c > cap:
                out.append((lo, i))
                lo, acc = i, 0
            acc += int(c)
        out.append((lo, len(counts)))
        return out

    def pairs(self, lo: int = 0, hi: Optional[int] = None, *, valid=None,
              max_pairs: int = MAX_BLOCK_PAIRS
              ) -> Iterator[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
        """Blocks of ``(i, j, ci, cj)`` for the pairs ``i < j`` of every
        trace with ``lo <= i < hi`` — local bin indices and the coordinates
        of the two spots — in trace order, then ``i``, then ``j``; at most
        ``max_pairs`` pairs per block.  Rows with a non-finite coordinate
        are dropped (``valid(coords)`` overrides the test)."""
        self.prepare()
        hi = self.n_bins if hi is None else hi
        for bid, coords, runs in self.chunks():
            li = self.local(bid)
            ok = np.isfinite(coords).all(axis=1) if valid is None else valid(coords)
            li2, runs2 = _drop_rows(li, runs, ok)
            c2 = coords[ok] if not ok.all() else coords
            n = len(li2)
            if not n:
                continue
            rem = np.where((li2 >= lo) & (li2 < hi), _remaining(runs2, n), 0)
            csum = np.cumsum(rem)
            total = int(csum[-1])
            if not total:
                continue
            # row blocks of at most max_pairs pairs (a row's pairs stay together)
            cuts = np.searchsorted(csum, np.arange(max_pairs, total, max_pairs), side="left")
            bounds = np.unique(np.r_[0, cuts + 1, n])
            for r0, r1 in zip(bounds[:-1], bounds[1:]):
                a, b = _pair_rows(rem, int(r0), int(r1))
                if len(a):
                    yield li2[a], li2[b], c2[a], c2[b]


def _n_runs(cd) -> int:
    idx = getattr(cd, "_index", None)
    if idx is not None:
        return len(idx["trace_offsets"]) - 1
    return int(cd.n_spots) or 1


def _first_of_runs(new_run: np.ndarray, keep: np.ndarray) -> np.ndarray:
    """``new_run`` flags after dropping rows (a run starts at its first kept row)."""
    run_id = np.cumsum(new_run)
    r = run_id[keep]
    return np.r_[True, r[1:] != r[:-1]] if len(r) else np.zeros(0, dtype=bool)


def _drop_rows(li: np.ndarray, runs: np.ndarray, keep: np.ndarray):
    if keep.all():
        return li, runs
    run_id = np.repeat(np.arange(len(runs) - 1), np.diff(runs))
    r = run_id[keep]
    li = li[keep]
    if not len(li):
        return li, np.zeros(1, dtype=np.int64)
    new = np.r_[True, r[1:] != r[:-1]]
    return li, np.r_[np.flatnonzero(new), len(li)].astype(np.int64)


def _remaining(runs: np.ndarray, n: int) -> np.ndarray:
    """For each row: rows after it in its run."""
    lens = np.diff(runs)
    end = np.repeat(runs[1:], lens)
    return end - np.arange(n) - 1


def _pair_rows(rem: np.ndarray, r0: int, r1: int):
    """Row indices ``(a, b)`` of the pairs ``(a, a + 1 .. a + rem[a])`` for
    the rows ``a`` in ``[r0, r1)``, ordered by ``a`` then ``b``."""
    rem = rem[r0:r1]
    total = int(rem.sum())
    if total == 0:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    a = np.repeat(np.arange(r0, r1, dtype=np.int64), rem)
    starts = np.cumsum(rem) - rem
    b = a + 1 + (np.arange(total, dtype=np.int64) - np.repeat(starts, rem))
    return a, b


def sort_within_groups(keys: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Permutation sorting by ``keys``, then ``values`` — exact, but ~10x
    faster than ``np.lexsort`` on 10⁷–10⁸ elements.

    One float sort on ``key * S + (value - min)`` (``S`` > twice the value
    span, so groups cannot interleave) orders everything but values closer
    than the key's rounding; the groups where such a pair ends up out of
    order are then re-sorted exactly with ``np.lexsort``.  ``values`` must
    be finite."""
    n = len(keys)
    if n == 0:
        return np.zeros(0, dtype=np.int64)
    vmin = float(values.min())
    span = float(values.max()) - vmin
    scale = 2.0 * span + 1.0
    key = keys.astype(np.float64) * scale + (values - vmin)
    order = np.argsort(key)
    del key
    k = keys[order]
    if (k[1:] < k[:-1]).any():  # pragma: no cover - cannot happen for finite values
        return np.lexsort((values, keys))
    v = values[order]
    bad = (k[1:] == k[:-1]) & (v[1:] < v[:-1])
    if bad.any():
        rows = np.flatnonzero(np.isin(k, np.unique(k[1:][bad])))
        sub = order[rows]
        order[rows] = sub[np.lexsort((values[sub], keys[sub]))]
    return order


def grouped_order_stats(keys: np.ndarray, values: np.ndarray):
    """Exact per-group order statistics of ``values`` (finite).

    Returns ``(group keys ascending, counts, lower medians, upper medians,
    order)``: the lower median is the element of rank ``(n - 1) // 2`` —
    what ``torch.nanmedian`` returns —, the upper one of rank ``n // 2``;
    ``order`` sorts the inputs by (key, value)."""
    order = sort_within_groups(keys, values)
    k = keys[order]
    v = values[order]
    if not len(k):
        e = np.zeros(0)
        return np.zeros(0, keys.dtype), np.zeros(0, np.int64), e, e, order
    starts = np.flatnonzero(np.r_[True, k[1:] != k[:-1]])
    counts = np.diff(np.r_[starts, len(k)])
    lo = v[starts + (counts - 1) // 2]
    hi = v[starts + counts // 2]
    return k[starts], counts, lo, hi, order


def pair_distance(ci: np.ndarray, cj: np.ndarray) -> np.ndarray:
    """Euclidean distances, computed as the dense pivots compute them:
    ``sqrt(((xi - xj)² + (yi - yj)²) + (zi - zj)²)``."""
    d = ci - cj
    d *= d
    return np.sqrt((d[:, 0] + d[:, 1]) + d[:, 2])


__all__ = ["BYTES_PER_OBS", "ChromPairs", "grouped_order_stats", "pair_distance", "sort_within_groups"]
