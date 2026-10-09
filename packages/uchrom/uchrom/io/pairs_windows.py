"""Per-cell contact counts inside windows of the contact map, accumulated over chunks of pairs: how many of each
cell's (or spatial Hi-C spot's) cis contacts fall into given rectangles of bin pairs.  With the windows of known
structures — the two flanks and the crossing square of a domain boundary, the peak and the donut around a loop —
these counts are the per-cell insulation and loop strength of structures called once on the pooled map, without
writing a fine per-cell map (a spot has ~1e5-1e6 contacts; its 25-kb map is mostly empty).

A window is ``chrom, start1, end1, start2, end2`` (bp, half-open, ``start1 <= start2``) at a resolution: the
bin pairs (i, j) with i in its first and j in its second interval, i <= j (contacts are counted once, in the
upper triangle; a window on the diagonal is a triangle).  Windows may overlap; each counts its contacts.
Positions are 1-based (pairs format): a contact at pos falls into bin ``(pos - 1) // resolution``.

:func:`boundary_windows` and :func:`loop_windows` build the windows of boundaries and loops;
:func:`uchrom.fea.window_scores` turns the counts into scores.
"""

from __future__ import annotations

import json
import os
from typing import Optional, Sequence, Union

import numpy as np
import pandas as pd

__all__ = ["WindowCounts", "boundary_windows", "loop_windows"]


def boundary_windows(boundaries: pd.DataFrame, *, window: int, resolution: int) -> pd.DataFrame:
    """Three windows per boundary (``chrom``, ``pos`` bp, snapped to the bin grid): ``left`` (both ends in the
    ``window`` bp upstream), ``right`` (both downstream) and ``cross`` (one end on each side).  The columns
    ``feature`` (the boundary's row) and ``part`` say which."""
    r = int(resolution)
    w = int(window) // r * r
    rows = []
    for k, b in enumerate(boundaries.itertuples(index=False)):
        p = int(round(int(b.pos) / r)) * r
        lo, hi = max(p - w, 0), p + w
        rows += [(b.chrom, lo, p, lo, p, k, "left"), (b.chrom, p, hi, p, hi, k, "right"),
                 (b.chrom, lo, p, p, hi, k, "cross")]
    return pd.DataFrame(rows, columns=["chrom", "start1", "end1", "start2", "end2", "feature", "part"])


def loop_windows(loops: pd.DataFrame, *, resolution: int, peak: int = 1, donut: Sequence[int] = (2, 5)
                 ) -> pd.DataFrame:
    """Windows of each loop (``chrom1, start1, start2``: its anchors, bp) at ``resolution``: ``peak`` — the
    (2 peak + 1)^2 pixels around the loop pixel — and ``donut`` — the ring of pixels between ``donut[0]`` and
    ``donut[1]`` pixels from it (Chebyshev distance), as four non-overlapping strips.  Columns ``feature`` and
    ``part``."""
    r = int(resolution)
    d0, d1 = int(donut[0]), int(donut[1])
    rows = []
    for k, lp in enumerate(loops.itertuples(index=False)):
        i, j = int(lp.start1) // r, int(lp.start2) // r
        c = lp.chrom1

        def rect(a0, a1, b0, b1, part):
            rows.append((c, max(a0, 0) * r, max(a1, 0) * r, max(b0, 0) * r, max(b1, 0) * r, k, part))

        rect(i - peak, i + peak + 1, j - peak, j + peak + 1, "peak")
        rect(i - d1, i - d0 + 1, j - d1, j + d1 + 1, "donut")          # rows above the inner square
        rect(i + d0, i + d1 + 1, j - d1, j + d1 + 1, "donut")          # rows below
        rect(i - d0 + 1, i + d0, j - d1, j - d0 + 1, "donut")          # left strip
        rect(i - d0 + 1, i + d0, j + d0, j + d1 + 1, "donut")          # right strip
    return pd.DataFrame(rows, columns=["chrom", "start1", "end1", "start2", "end2", "feature", "part"])


class WindowCounts:
    """Contacts per cell in each window.

    Parameters
    ----------
    cells
        The cell ids (rows of ``counts``).
    windows
        ``chrom, start1, end1, start2, end2`` (+ any other columns, kept), bp.
    resolution
        The bin size the windows are counted at.
    chroms
        The chromosomes, in the order of the codes given to :meth:`add`.

    Attributes
    ----------
    counts : ndarray (n_cells, n_windows), int64
    """

    def __init__(self, cells: Sequence, windows: pd.DataFrame, resolution: int, chroms: Sequence[str]):
        self.cells = np.asarray([str(c) for c in cells], dtype=object)
        self.windows = windows.reset_index(drop=True).copy()
        self.resolution = int(resolution)
        self.chroms = [str(c) for c in chroms]
        self.counts = np.zeros((len(self.cells), len(self.windows)), np.int64)
        self._index()

    def _index(self):
        r = self.resolution
        code = {c: i for i, c in enumerate(self.chroms)}
        w = self.windows
        keys, wins = [], []
        span = int(np.ceil(max(int(w["end1"].max()) if len(w) else 1, int(w["end2"].max()) if len(w) else 1) / r)) + 2
        self._nb = span
        for k, row in enumerate(w.itertuples(index=False)):
            if row.chrom not in code:
                continue
            a = np.arange(int(row.start1) // r, -(-int(row.end1) // r))
            b = np.arange(int(row.start2) // r, -(-int(row.end2) // r))
            ii, jj = np.meshgrid(a, b, indexing="ij")
            ok = ii <= jj
            kk = (code[row.chrom] * span + ii[ok]) * span + jj[ok]
            keys.append(kk.astype(np.int64))
            wins.append(np.full(kk.size, k, np.int64))
        if keys:
            k = np.concatenate(keys)
            v = np.concatenate(wins)
            order = np.argsort(k, kind="stable")
            k, v = k[order], v[order]
            self._keys, starts = np.unique(k, return_index=True)
            self._indptr = np.r_[starts, len(k)]
            self._wins = v
        else:
            self._keys = np.zeros(0, np.int64)
            self._indptr = np.zeros(1, np.int64)
            self._wins = np.zeros(0, np.int64)

    def add(self, cell, chrom1, pos1, chrom2, pos2) -> None:
        """Count a chunk of contacts: ``cell`` rows (-1: skip), chromosome codes (index into ``chroms``,
        -1: other), 1-based positions.  Trans contacts are ignored."""
        cell = np.asarray(cell, np.int64)
        c1 = np.asarray(chrom1, np.int64)
        c2 = np.asarray(chrom2, np.int64)
        ok = (cell >= 0) & (c1 >= 0) & (c1 == c2)
        if not ok.any() or len(self._keys) == 0:
            return
        r = self.resolution
        b1 = (np.asarray(pos1, np.int64)[ok] - 1) // r
        b2 = (np.asarray(pos2, np.int64)[ok] - 1) // r
        lo, hi = np.minimum(b1, b2), np.maximum(b1, b2)
        inside = hi < self._nb
        lo, hi, cc, ch = lo[inside], hi[inside], cell[ok][inside], c1[ok][inside]
        k = (ch * self._nb + lo) * self._nb + hi
        pos = np.searchsorted(self._keys, k)
        pos[pos == len(self._keys)] = 0
        hit = self._keys[pos] == k
        pos, cc = pos[hit], cc[hit]
        n = self._indptr[pos + 1] - self._indptr[pos]
        cells = np.repeat(cc, n)
        first = np.repeat(self._indptr[pos], n)
        offset = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)
        wins = self._wins[first + offset]
        flat, cnt = np.unique(cells * len(self.windows) + wins, return_counts=True)
        np.add.at(self.counts.reshape(-1), flat, cnt)

    def merge(self, other: "WindowCounts") -> "WindowCounts":
        if list(other.cells) != list(self.cells) or not other.windows.equals(self.windows):
            raise ValueError("WindowCounts.merge: cells and windows must match")
        self.counts += other.counts
        return self

    def save(self, path: Union[str, os.PathLike], **meta) -> None:
        w = self.windows
        np.savez_compressed(path, cells=self.cells.astype(str), counts=self.counts,
                            resolution=np.int64(self.resolution), chroms=np.asarray(self.chroms, dtype=str),
                            windows=np.asarray(w.to_json(orient="split")), meta=np.asarray(json.dumps(meta)))

    @classmethod
    def load(cls, path: Union[str, os.PathLike]) -> "WindowCounts":
        from io import StringIO

        with np.load(path, allow_pickle=False) as z:
            w = pd.read_json(StringIO(str(z["windows"])), orient="split")
            out = cls.__new__(cls)
            out.cells = z["cells"].astype(object)
            out.windows = w
            out.resolution = int(z["resolution"])
            out.chroms = list(z["chroms"])
            out.counts = z["counts"].astype(np.int64)
            out.meta = json.loads(str(z["meta"]))
        return out

    def by_part(self) -> dict:
        """Counts summed per (feature, part): ``{part: ndarray (n_cells, n_features)}`` (features in order)."""
        w = self.windows
        out = {}
        nf = int(w["feature"].max()) + 1 if len(w) else 0
        for part, g in w.groupby("part", sort=False):
            m = np.zeros((len(self.cells), nf), np.int64)
            for f, gg in g.groupby("feature"):
                m[:, int(f)] = self.counts[:, gg.index.to_numpy()].sum(axis=1)
            out[str(part)] = m
        return out
