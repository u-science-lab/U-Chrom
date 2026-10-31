"""Pseudo-bulk contact maps: the per-cell maps of each group of cells summed into one map per group.

Single-cell Hi-C maps are too sparse for structure calling; summed over the cells of a cell type (or a cluster,
a condition, all cells) they become bulk-like maps that the callers of :mod:`uchrom.strc` read.
:func:`pseudobulk` sums the per-cell maps linked to a ``ChromData`` (``cd.link_scool``) per group of cells,
writes one ICE-balanced ``.cool`` per group and links it to ``cd`` (``cd.link_cool``) under
``"<key_prefix>.<group>"``::

    cd = ds.load("dschic_aging_cortex")                         # 32,777 cells, 1 Mb maps embedded (HTTP)
    summary = pseudobulk(cd, "cell_type")                       # one map per cell type
    cd.uns["linked_cool"]["pseudobulk.Astrocytes"]              # {"path": ..., "n_cells": 4578, ...}
    call_compartments_hic(cd, contacts="pseudobulk.Astrocytes", ...)

The per-cell maps are read where they are:

* a linked local ``.scool``: every cell's pixels are read once (cooler's single-cell format);
* maps embedded in a store (an atlas store over HTTP, :mod:`chromdata.embedded`): each chromosome partition is
  read once for all the selected cells, in blocks of whole cells, and added by group as it streams — no
  per-cell file is exported.

One ``.cool`` per group (not one multi-resolution file): each group's map is a separate linked map that the
callers take by key, can be replaced or embedded on its own, and :func:`uchrom.fea.rebin_map` makes coarser
levels of it on demand; ``resolution=`` sums into coarser bins in the same pass.

Where the files go (``out_dir=`` overrides): next to a local store (``<store dir>/<store name>_pseudobulk/``,
linked by a path relative to the store's folder, so the folder moves as a whole); for a store read over HTTP
the data directory (``<data dir>/pseudobulk/<store name>/``, ``uchrom.datasets.data_dir()``: kept across
sessions); for a ``ChromData`` not read from a store a scratch directory removed at exit.  A map already
there with the same cells, source and parameters (recorded in the file) is reused unless ``overwrite=True``.

Depth matters when pseudo-bulks are compared (e.g. the compartment strength rises in shallow maps):
:func:`sample_cells_by_depth` draws disjoint random sets of cells with the same number of contacts per group,
the groups of a matched-depth comparison::

    sets = sample_cells_by_depth(cd, ["cell_type", "age"], n_contacts=5e6, replicates=3)
    pseudobulk(cd, sets["set"])                                 # one map per set: "Astrocytes | 3mo | 1", ...
"""

from __future__ import annotations

import hashlib
import os
import re
import time
import warnings
from collections.abc import Mapping
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

__all__ = ["pseudobulk", "ice", "sample_cells_by_depth"]

#: accumulators with at most this many (group, bin1, bin2) entries are dense int64 arrays (512 MB), larger
#: ones sparse (e.g. the trans contacts of 7 cell types at 1 Mb on mm10: 52 M entries, dense)
DENSE_MAX = 1 << 26
#: pixels buffered before a sparse accumulator folds them in (at least the accumulator's own size)
FLUSH_MIN = 1 << 23
#: pixels per block when embedded per-cell maps are read (whole cells; bounds the memory of a read)
BLOCK_PIXELS = 2_000_000
#: reads of embedded per-cell maps in flight at once (threads)
READ_WORKERS = 4
#: rows per chunk handed to cooler when a map is written
WRITE_CHUNK = 5_000_000

_SAFE = re.compile(r"[^A-Za-z0-9._+-]+")


# ----------------------------------------------------------------------------------------------------------
# accumulation
# ----------------------------------------------------------------------------------------------------------

class _Sum:
    """Per-group sums of the pixels of one partition: ``(group, bin1, bin2) -> count``.

    Dense (``np.add.at`` into a flat array) when ``n_groups * n_rows * n_cols <= DENSE_MAX``; otherwise a
    sparse CSR matrix of shape ``(n_groups * n_rows, n_cols)`` to which buffered pixels are added once the
    buffer holds at least as many pixels as the matrix (each pixel is folded in O(log n) times)."""

    def __init__(self, n_groups: int, n_rows: int, n_cols: int, budget: Optional[list] = None):
        self.G, self.R, self.C = int(n_groups), int(n_rows), int(n_cols)
        size = self.G * self.R * self.C
        # budget: [entries left] shared by accumulators alive at the same time
        dense = size <= (DENSE_MAX if budget is None else budget[0])
        if dense and budget is not None:
            budget[0] -= size
        self.dense = np.zeros(size, np.int64) if dense else None
        self.acc = None
        self.buf: List[Tuple[np.ndarray, np.ndarray, np.ndarray]] = []
        self.n_buf = 0

    def add(self, g: np.ndarray, b1: np.ndarray, b2: np.ndarray, c: np.ndarray) -> None:
        if len(c) == 0:
            return
        row = g.astype(np.int64) * self.R + b1
        if self.dense is not None:
            np.add.at(self.dense, row * self.C + b2, c.astype(np.int64))
            return
        self.buf.append((row, b2.astype(np.int64), c.astype(np.int64)))
        self.n_buf += len(c)
        if self.n_buf >= max(FLUSH_MIN, self.acc.nnz if self.acc is not None else 0):
            self._flush()

    def _flush(self) -> None:
        import scipy.sparse as sp

        if not self.buf:
            return
        rows = np.concatenate([b[0] for b in self.buf])
        cols = np.concatenate([b[1] for b in self.buf])
        vals = np.concatenate([b[2] for b in self.buf])
        self.buf, self.n_buf = [], 0
        m = sp.csr_matrix((vals, (rows, cols)), shape=(self.G * self.R, self.C))     # duplicates summed
        m.sum_duplicates()
        self.acc = m if self.acc is None else self.acc + m

    def result(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """``(group, bin1, bin2, count)`` of the non-zero sums, sorted by (group, bin1, bin2)."""
        if self.dense is not None:
            nz = np.flatnonzero(self.dense)
            cnt = self.dense[nz]
            self.dense = None                                  # freed before the index arrays are made
            row, col = np.divmod(nz, self.C)
            del nz
        else:
            self._flush()
            if self.acc is None:
                z = np.zeros(0, np.int64)
                return z, z, z, z
            self.acc.sum_duplicates()
            self.acc.eliminate_zeros()
            coo = self.acc.tocoo()
            row, col, cnt = coo.row.astype(np.int64), coo.col.astype(np.int64), coo.data.astype(np.int64)
            self.acc = None
        g, b1 = np.divmod(row, self.R)
        small = np.int32 if max(self.R, self.C, self.G) < 2**31 else np.int64
        return g.astype(small), b1.astype(small), col.astype(small), cnt


# ----------------------------------------------------------------------------------------------------------
# sources of per-cell maps
# ----------------------------------------------------------------------------------------------------------

class _Grid:
    """The bins of the per-cell maps and of the pseudo-bulk (``factor`` fine bins per coarse bin)."""

    def __init__(self, chroms: Sequence[str], sizes: Sequence[int], base: int, resolution: int):
        self.chroms = [str(c) for c in chroms]
        self.sizes = np.asarray(sizes, np.int64)
        self.base, self.res = int(base), int(resolution)
        if self.res % self.base:
            raise ValueError(f"resolution {self.res} is not a multiple of the per-cell maps' {self.base} bp")
        self.factor = self.res // self.base
        self.n_fine = -(-self.sizes // self.base)
        self.n_coarse = -(-self.sizes // self.res)
        self.first_fine = np.r_[0, np.cumsum(self.n_fine)[:-1]].astype(np.int64)
        self.first_coarse = np.r_[0, np.cumsum(self.n_coarse)[:-1]].astype(np.int64)
        self.chrom_of_fine = np.repeat(np.arange(len(self.chroms)), self.n_fine)
        self._f2c = None

    @property
    def n_bins(self) -> int:
        return int(self.n_coarse.sum())

    def f2c(self) -> np.ndarray:
        """Genome-wide fine bin -> genome-wide coarse bin."""
        if self._f2c is None:
            local = np.arange(len(self.chrom_of_fine), dtype=np.int64) - self.first_fine[self.chrom_of_fine]
            self._f2c = self.first_coarse[self.chrom_of_fine] + local // self.factor
        return self._f2c

    def bins(self) -> pd.DataFrame:
        from ..io.pairs_maps import genome_bins

        return genome_bins(dict(zip(self.chroms, self.sizes.tolist())), self.res)


class _EmbeddedSource:
    """Per-cell maps embedded in a store: one partition (``cis/<chrom>``, ``trans``) at a time."""

    sequential = True

    def __init__(self, e, max_pixels: int):
        self.e = e
        self.base = int(e.resolutions[0])
        sizes = e.chromsizes(self.base)
        self.chroms = [c for c in e.chroms if c in sizes]
        self.sizes = [int(sizes[c]) for c in self.chroms]
        self.cells = [str(c) for c in e.cells]
        self.max_pixels = int(max_pixels)
        self.assembly = None

    def check(self, grid: "_Grid") -> None:
        """The genome-wide bin numbering of the embedded map (its trans pixels) must be the grid's."""
        first = [int(self.e.first_bin(c, self.base)) for c in self.chroms]
        if first != grid.first_fine.tolist():
            raise ValueError("the embedded map numbers its bins differently from its chromosome sizes")

    def partitions(self, trans: bool) -> List[Tuple[int, str]]:
        g = self.e.g[f"r{self.base}"]
        parts = [(i, f"cis/{c}") for i, c in enumerate(self.chroms) if f"cis/{c}" in g]
        if trans and "trans" in g:
            parts.append((-1, "trans"))
        return parts

    def tasks(self, trans: bool, cell_idx: np.ndarray) -> Iterator[Tuple[int, str, np.ndarray, np.ndarray]]:
        """Reads to make, partition by partition: ``(partition index, name, cells, pixels of each cell)``, the
        cells (sorted, with pixels) of one read adding up to about ``max_pixels`` (a bigger cell alone)."""
        e, r = self.e, self.base
        order = np.unique(np.asarray(cell_idx, np.int64))
        for p, name in self.partitions(trans):
            # pixel offsets of every cell in the partition (the layout of chromdata.embedded: a cell's pixels
            # are one run, cells in order), so that each read is attributed to its cells
            off = e._offsets(r, name, "cell_offset")
            n = off[order + 1] - off[order]
            cells, n = order[n > 0], n[n > 0]
            cum = np.cumsum(n)
            start = 0
            while start < len(cells):
                base = cum[start - 1] if start else 0
                end = max(int(np.searchsorted(cum, base + self.max_pixels, side="right")), start + 1)
                yield p, name, cells[start:end], n[start:end]
                start = end

    def read(self, task) -> Tuple[int, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """``(partition, cell of every pixel, bin1, bin2, count)`` of one task; cis bins chromosome-local,
        trans bins genome-wide (as stored)."""
        p, name, cells, n = task
        d = self.e.cell_pixels(name, cells, self.base)        # the cells' pixels, concatenated in cell order
        if len(d) != int(n.sum()):
            raise RuntimeError(f"{name}: read {len(d)} pixels for cells holding {int(n.sum())}")
        return p, np.repeat(cells, n), d[:, 0], d[:, 1], d[:, 2]


def _prefetch(func, tasks, workers: int):
    """``func(task)`` of every task, in order, with up to ``workers`` reads running ahead in threads (HTTP
    range reads overlap each other and the accumulation)."""
    if workers <= 1:
        for t in tasks:
            yield func(t)
        return
    from collections import deque
    from concurrent.futures import ThreadPoolExecutor

    it = iter(tasks)
    with ThreadPoolExecutor(workers) as pool:
        pending = deque(pool.submit(func, t) for _, t in zip(range(workers + 1), it))
        while pending:
            out = pending.popleft().result()
            nxt = next(it, None)
            if nxt is not None:
                pending.append(pool.submit(func, nxt))
            yield out


class _ScoolSource:
    """A local ``.scool``: every cell's pixels read once, split into partitions on the fly."""

    sequential = False

    def __init__(self, path: str, max_pixels: int):
        import h5py

        self.path = str(path)
        self.max_pixels = int(max_pixels)
        with h5py.File(self.path, "r") as f:
            self.cells = [str(c) for c in f["cells"]]
            chroms = [str(c) for c in np.asarray(f["chroms/name"][:]).astype(str)]
            lengths = np.asarray(f["chroms/length"][:], np.int64)
            chrom = np.asarray(f["bins/chrom"][:], np.int64)
            start = np.asarray(f["bins/start"][:], np.int64)
            end = np.asarray(f["bins/end"][:], np.int64)
            info = dict(f.attrs)
        self.base = int(np.median(end - start)) if len(start) else 1
        for c in range(len(chroms)):
            s = start[chrom == c]
            if not np.array_equal(s, np.arange(len(s), dtype=np.int64) * self.base):
                raise ValueError(f"{self.path}: bins of {chroms[c]} are not uniform {self.base} bp bins from 0")
        if np.any(np.diff(chrom) < 0):
            raise ValueError(f"{self.path}: bins are not in chromosome order")
        self.chroms, self.sizes = chroms, lengths.tolist()
        self.n_bins = len(chrom)
        self.assembly = info.get("genome-assembly")
        if isinstance(self.assembly, bytes):
            self.assembly = self.assembly.decode()

    def check(self, grid: "_Grid") -> None:
        if int(grid.n_fine.sum()) != self.n_bins:
            raise ValueError(f"{self.path}: {self.n_bins} bins, but its chromosome lengths give "
                             f"{int(grid.n_fine.sum())}")

    def iter_cells(self, cell_idx: np.ndarray) -> Iterator[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
        """(cell of every pixel, bin1, bin2, count) with genome-wide fine bins, a few cells per block."""
        import h5py

        rows, b1s, b2s, cs, n = [], [], [], [], 0
        with h5py.File(self.path, "r") as f:
            for i in np.unique(np.asarray(cell_idx, np.int64)):
                px = f["cells"][self.cells[i]]["pixels"]
                b1 = px["bin1_id"][:].astype(np.int64)
                rows.append(np.full(len(b1), i, np.int64))
                b1s.append(b1)
                b2s.append(px["bin2_id"][:].astype(np.int64))
                cs.append(px["count"][:].astype(np.int64))
                n += len(b1)
                if n >= self.max_pixels:
                    yield tuple(np.concatenate(x) for x in (rows, b1s, b2s, cs))
                    rows, b1s, b2s, cs, n = [], [], [], [], 0
        if n:
            yield tuple(np.concatenate(x) for x in (rows, b1s, b2s, cs))


def _sum_groups(source, grid: _Grid, group_of_cell: np.ndarray, n_groups: int, trans: bool,
                timing: Dict[str, float], workers: int = 1) -> Dict[int, Tuple[np.ndarray, ...]]:
    """``{partition: (group, bin1, bin2, count)}``: chromosome index -> chromosome-local coarse bins (cis);
    ``-1`` -> genome-wide coarse bins (trans)."""
    f = grid.factor
    out: Dict[int, Tuple[np.ndarray, ...]] = {}
    idx = np.flatnonzero(group_of_cell >= 0)
    if source.sequential:
        cur, acc = None, None
        t_read = time.perf_counter()
        for p, cell, b1, b2, c in _prefetch(source.read, source.tasks(trans, idx), workers):
            t0 = time.perf_counter()
            timing["read"] += t0 - t_read                   # waiting for reads (the rest overlaps)
            if p != cur:
                if acc is not None:
                    out[cur] = acc.result()
                cur = p
                acc = (_Sum(n_groups, grid.n_coarse[p], grid.n_coarse[p]) if p >= 0
                       else _Sum(n_groups, grid.n_bins, grid.n_bins))
            if p >= 0:
                b1, b2 = (b1 // f, b2 // f) if f > 1 else (b1, b2)
            else:
                b1, b2 = (grid.f2c()[b1], grid.f2c()[b2]) if f > 1 else (b1, b2)
            acc.add(group_of_cell[cell], b1, b2, c)
            t_read = time.perf_counter()
            timing["add"] += t_read - t0
        t0 = time.perf_counter()
        if acc is not None:
            out[cur] = acc.result()
        timing["add"] += time.perf_counter() - t0
        return out
    accs: Dict[int, _Sum] = {}
    budget = [DENSE_MAX]                       # every partition's sums are alive at once: one dense budget
    chrom_of = grid.chrom_of_fine
    t_read = time.perf_counter()
    for cell, b1, b2, c in source.iter_cells(idx):
        t0 = time.perf_counter()
        timing["read"] += t0 - t_read
        g = group_of_cell[cell]
        c1, c2 = chrom_of[b1], chrom_of[b2]
        part = np.where(c1 == c2, c1, -1)
        if not trans:
            keep = part >= 0
            g, b1, b2, c, part = g[keep], b1[keep], b2[keep], c[keep], part[keep]
        order = np.argsort(part, kind="stable")
        part_s = part[order]
        cuts = np.flatnonzero(np.diff(part_s)) + 1
        for lo, hi in zip(np.r_[0, cuts], np.r_[cuts, len(part_s)]):
            if hi <= lo:
                continue
            sel = order[lo:hi]
            p = int(part_s[lo])
            if p >= 0:
                x1 = (b1[sel] - grid.first_fine[p]) // f
                x2 = (b2[sel] - grid.first_fine[p]) // f
                if p not in accs:
                    accs[p] = _Sum(n_groups, grid.n_coarse[p], grid.n_coarse[p], budget)
            else:
                x1, x2 = (grid.f2c()[b1[sel]], grid.f2c()[b2[sel]]) if f > 1 else (b1[sel], b2[sel])
                if p not in accs:
                    accs[p] = _Sum(n_groups, grid.n_bins, grid.n_bins, budget)
            accs[p].add(g[sel], x1, x2, c[sel])
        t_read = time.perf_counter()
        timing["add"] += t_read - t0
    t0 = time.perf_counter()
    for p in sorted(accs, key=lambda q: (q < 0, q)):
        out[p] = accs.pop(p).result()
    timing["add"] += time.perf_counter() - t0
    return out


def _group_pixels(parts: Dict[int, Tuple[np.ndarray, ...]], grid: _Grid, g: int):
    """Genome-wide (bin1, bin2, count) of group ``g`` sorted by (bin1, bin2), and its cis count.

    Each partition's sums are sorted already; the rows of a chromosome are its cis pixels followed, row by
    row, by its trans pixels (a contiguous run of the sorted trans sums): merged one chromosome at a time
    into preallocated arrays, so no genome-wide sort and no copy beyond the result."""
    sl = {}
    for p, (gg, *_rest) in parts.items():
        lo, hi = np.searchsorted(gg, [g, g + 1])
        if hi > lo:
            sl[p] = (int(lo), int(hi))
    total = sum(hi - lo for lo, hi in sl.values())
    idx = np.int32 if grid.n_bins < 2**31 else np.int64
    B1, B2, C = np.empty(total, idx), np.empty(total, idx), np.empty(total, np.int64)
    n_cis = 0
    tb1 = tb2 = tc = None
    if -1 in sl:
        lo, hi = sl[-1]
        _, tb1, tb2, tc = parts[-1]
        tb1, tb2, tc = tb1[lo:hi], tb2[lo:hi], tc[lo:hi]
        t_cut = np.searchsorted(tb1, np.r_[grid.first_coarse, grid.n_bins])     # trans rows of each chromosome
    pos = 0
    for k in range(len(grid.chroms)):
        pieces = []
        if k in sl:
            lo, hi = sl[k]
            _, b1, b2, c = parts[k]
            off = int(grid.first_coarse[k])
            pieces.append((b1[lo:hi].astype(np.int64) + off, b2[lo:hi].astype(np.int64) + off, c[lo:hi]))
            n_cis += int(c[lo:hi].sum())
        if tb1 is not None and t_cut[k + 1] > t_cut[k]:
            a, b = t_cut[k], t_cut[k + 1]
            pieces.append((tb1[a:b].astype(np.int64), tb2[a:b].astype(np.int64), tc[a:b]))
        if not pieces:
            continue
        b1 = np.concatenate([x[0] for x in pieces])
        b2 = np.concatenate([x[1] for x in pieces])
        c = np.concatenate([x[2] for x in pieces])
        if len(pieces) > 1:
            order = np.argsort(b1 * grid.n_bins + b2, kind="stable")          # two sorted runs: a merge
            b1, b2, c = b1[order], b2[order], c[order]
        n = len(c)
        B1[pos:pos + n], B2[pos:pos + n], C[pos:pos + n] = b1, b2, c
        pos += n
    return B1[:pos], B2[:pos], C[:pos], n_cis


# ----------------------------------------------------------------------------------------------------------
# writing
# ----------------------------------------------------------------------------------------------------------

class _SymUpper:
    """A symmetric map held as its upper triangle ``U``: ``S @ x = U @ x + U.T @ x - diag(U) x`` (the transpose
    is a view; the diagonal counts once, as in cooler's marginals since 0.12)."""

    def __init__(self, U):
        self.U = U
        self.d = U.diagonal()

    def __matmul__(self, x):
        return self.U @ x + self.U.T @ x - self.d * x

    def __getitem__(self, key):
        return _SymUpper(self.U[key])

    def marginals(self) -> np.ndarray:
        return self @ np.ones(self.U.shape[1])


def ice(b1: np.ndarray, b2: np.ndarray, count: np.ndarray, chrom_offsets: np.ndarray, *, cis_only: bool = False,
        ignore_diags: int = 2, min_nnz: int = 10, mad_max: float = 5, tol: float = 1e-5,
        max_iters: int = 200) -> Tuple[np.ndarray, dict]:
    """Iterative correction (ICE; Imakaev et al. 2012, Nat Methods 9:999) of an in-memory map, the algorithm
    and filters of ``cooler.balance_cooler`` (Abdennur & Mirny 2020; as of cooler 0.12) without re-reading the
    file each iteration.

    Pixels of one chromosome with ``|bin1 - bin2| < ignore_diags`` (and, ``cis_only``, the trans pixels) are
    left out — neighbouring bins across a chromosome boundary are trans; bins with
    fewer than ``min_nnz`` non-zero pixels, and bins whose marginal (normalised by its chromosome's median) lies
    ``mad_max`` median absolute deviations below the median in log space, are masked; then the bias is divided
    by the normalised marginal of the bias-corrected map until the marginals' variance is under ``tol``, and
    rescaled so that the balanced marginals are 1; bins left with no data are masked.  The main diagonal counts
    once in the marginals.  ``cis_only``: each chromosome on its own.

    Parameters
    ----------
    b1, b2, count
        Upper-triangle pixels (genome-wide bin ids).
    chrom_offsets
        First bin of every chromosome plus the number of bins (cooler's ``indexes/chrom_offset``).

    Returns
    -------
    bias : ndarray (n_bins,)
        Balanced = count * bias[i] * bias[j]; NaN on masked bins.
    stats : dict
        As ``cooler.balance_cooler``: ``tol, min_nnz, min_count, mad_max, cis_only, trans_only, ignore_diags,
        scale, converged, var, divisive_weights`` (per chromosome when ``cis_only``).
    """
    import scipy.sparse as sp

    offsets = np.asarray(chrom_offsets, np.int64)
    n = int(offsets[-1])
    chrom_of = np.repeat(np.arange(len(offsets) - 1), np.diff(offsets))
    b1, b2 = np.asarray(b1, np.int64), np.asarray(b2, np.int64)
    v = np.asarray(count, np.float64)
    keep = v != 0
    if ignore_diags:
        keep &= (np.abs(b1 - b2) >= ignore_diags) | (chrom_of[b1] != chrom_of[b2])
    if cis_only:
        keep &= chrom_of[b1] == chrom_of[b2]
    r, q, v = b1[keep], b2[keep], v[keep]
    bias = np.ones(n)
    if min_nnz > 0:
        nnz = np.bincount(r[r != q], minlength=n) + np.bincount(q, minlength=n)
        bias[nnz < min_nnz] = 0
    idx = np.int32 if n < 2**31 and len(v) < 2**31 else np.int64
    if len(r) < 2 or np.all((np.diff(r) > 0) | ((np.diff(r) == 0) & (np.diff(q) > 0))):
        # sorted, unique pixels (a cooler's order): the CSR arrays as they are, no conversion
        indptr = np.r_[0, np.cumsum(np.bincount(r, minlength=n))].astype(idx)
        U = sp.csr_matrix((v, q.astype(idx), indptr), shape=(n, n))
    else:
        U = sp.csr_matrix((v, (r, q)), shape=(n, n))                            # duplicates summed
    del r, q, v
    S = _SymUpper(U)
    with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if mad_max > 0:
            marg = S.marginals()
            for lo, hi in zip(offsets[:-1], offsets[1:]):
                cm = marg[lo:hi]
                if (cm > 0).any():                                              # empty chromosomes stay at 0
                    marg[lo:hi] = cm / np.median(cm[cm > 0])
            log_marg = np.log(marg[marg > 0])
            if len(log_marg):
                med = np.median(log_marg)
                cutoff = np.exp(med - mad_max * np.median(np.abs(log_marg - med)))
                bias[marg < cutoff] = 0

        def solve(M, b):
            scale = var = np.nan
            m = np.full(len(b), np.nan)
            for _ in range(int(max_iters)):
                m = b * (M @ b)
                nz = m[m != 0]
                if not len(nz):
                    break
                scale, var = nz.mean(), nz.var()
                f = m / scale
                f[f == 0] = 1
                b /= f
                if var < tol:
                    break
            b[m == 0] = 0                                                       # bins left with no data
            b[b == 0] = np.nan
            if np.isfinite(scale):
                b /= np.sqrt(scale)
            return b, scale, var

        if cis_only:
            scales = np.full(len(offsets) - 1, np.nan)
            variances = np.full(len(offsets) - 1, np.nan)
            for k, (lo, hi) in enumerate(zip(offsets[:-1], offsets[1:])):
                bias[lo:hi], scales[k], variances[k] = solve(S[lo:hi, lo:hi], bias[lo:hi].copy())
            empty = np.isnan(scales)
            if max_iters > 0 and not empty.all():                               # nothing to balance: converged
                variances[empty] = 0.0
            scale, var = scales, variances
        else:
            bias, scale, var = solve(S, bias)
    stats = {"tol": tol, "min_nnz": min_nnz, "min_count": 0, "mad_max": mad_max, "cis_only": bool(cis_only),
             "trans_only": False, "ignore_diags": ignore_diags, "scale": scale, "converged": np.asarray(var) < tol,
             "var": var, "divisive_weights": False}
    if not cis_only:
        stats["converged"] = bool(stats["converged"])
    return bias, stats


def _write_cool(path: Path, bins: pd.DataFrame, b1, b2, c, *, assembly, meta: dict, balance: bool,
                cis_only: bool) -> Tuple[Optional[bool], float, float]:
    """Write the map atomically and ICE-balance it (:func:`ice`, the ``cooler balance`` defaults, stored as
    ``cooler balance`` stores it).  Returns (whether the balancing converged — None when not balanced, seconds
    writing, seconds balancing)."""
    import cooler
    import h5py

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.part")
    dtype = np.int32 if (len(c) == 0 or int(c.max()) < 2**31) else np.int64

    def chunks():
        for s in range(0, max(len(c), 1), WRITE_CHUNK):
            yield pd.DataFrame({"bin1_id": b1[s:s + WRITE_CHUNK], "bin2_id": b2[s:s + WRITE_CHUNK],
                                "count": c[s:s + WRITE_CHUNK].astype(dtype)})

    converged = None
    t0 = time.perf_counter()
    try:
        cooler.create_cooler(str(tmp), bins, chunks(), ordered=True, assembly=assembly, metadata=meta,
                             dtypes={"count": dtype})
        t1 = time.perf_counter()
        if balance:
            n_per = bins.groupby("chrom", sort=False).size().to_numpy()
            weight, stats = ice(b1, b2, c, np.r_[0, np.cumsum(n_per)], cis_only=cis_only)
            with h5py.File(tmp, "r+") as h5:
                h5["bins"].create_dataset("weight", data=weight, compression="gzip", compression_opts=6)
                h5["bins/weight"].attrs.update(stats)
            converged = bool(np.all(stats["converged"]))
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return converged, t1 - t0, time.perf_counter() - t1


def _cool_meta(path: Path) -> Optional[dict]:
    """The ``pseudobulk`` record of a map written by :func:`pseudobulk` (None if absent / unreadable)."""
    try:
        import cooler

        return dict(cooler.Cooler(str(path)).info.get("metadata", {}).get("pseudobulk") or {}) or None
    except Exception:
        return None


# ----------------------------------------------------------------------------------------------------------
# the function
# ----------------------------------------------------------------------------------------------------------

def _cell_groups(cd, groupby, cells, groups, default_ids: Sequence[str]) -> Tuple[pd.Series, List[str]]:
    """(cell id -> group, both str; the groups in order); cells without a group left out.  ``groupby=None``:
    every cell of ``cd.cells`` (or ``default_ids`` when ``cd`` has no cell table) in one group ``"all"``."""
    if groupby is None:
        ids = [str(c) for c in cd.cells.index] if len(getattr(cd, "cells", ())) else list(default_ids)
        lab = pd.Series("all", index=ids)
        order = ["all"]
    else:
        if isinstance(groupby, str):
            if groupby not in cd.cells.columns:
                raise KeyError(f"groupby={groupby!r} is not a column of cd.cells ({list(cd.cells.columns)})")
            raw = cd.cells[groupby]
        elif isinstance(groupby, pd.Series):
            raw = groupby
        elif isinstance(groupby, Mapping):
            raw = pd.Series(dict(groupby))
        else:
            raise TypeError("groupby: a column of cd.cells, a Series or a mapping cell -> group (or None)")
        if isinstance(raw.dtype, pd.CategoricalDtype):
            order = [str(x) for x in raw.cat.categories]
        else:
            order = sorted({str(x) for x in raw.dropna()})
        lab = pd.Series(raw.to_numpy(), index=[str(c) for c in raw.index])
        lab = lab[lab.notna()].astype(str)
        if lab.index.has_duplicates:
            raise ValueError("groupby: a cell appears more than once")
    if cells is not None:
        want = [str(c) for c in cells]
        lab = lab[lab.index.isin(want)]
    if groups is not None:
        order = [str(g) for g in groups]
        lab = lab[lab.isin(order)]
    present = set(lab)
    order = [g for g in order if g in present]
    return lab, order


def _source_of(cd, contacts: str, max_pixels: int):
    """(source, description of the source) of the per-cell maps ``contacts``."""
    from chromdata.cdata import _linked_records

    records = _linked_records(cd.uns.get("linked_scool")) if hasattr(cd, "uns") else {}
    if contacts in records:
        path = cd.resolve_link_path(records[contacts]["path"])
        if path.exists():
            return _ScoolSource(str(path), max_pixels), {"contacts": contacts, "path": str(path)}, records[contacts]
        embedded = cd.embedded_links()["contacts"]
        if contacts in embedded:
            from chromdata.embedded import EmbeddedContacts

            loc = str(cd._links_from())
            src = _EmbeddedSource(EmbeddedContacts(loc, embedded[contacts]), max_pixels)
            return src, {"contacts": contacts, "store": loc, "embedded": embedded[contacts]}, records[contacts]
        raise FileNotFoundError(f"per-cell maps {contacts!r}: {path} does not exist and they are not embedded "
                                f"in the store")
    path = Path(str(contacts)).expanduser()
    if path.exists():
        return _ScoolSource(str(path), max_pixels), {"path": str(path.resolve())}, {}
    raise KeyError(f"contacts={contacts!r} is neither linked per-cell maps ({sorted(records)}) nor a .scool")


def _store_dir(cd) -> Tuple[Optional[Path], Optional[str]]:
    """(local folder of the store ``cd`` was read from, its URL if remote)."""
    from chromdata.remote import is_url

    src = cd._links_from() if hasattr(cd, "_links_from") else None
    if src is None:
        return None, None
    if isinstance(src, str) and is_url(src):
        return None, src
    return Path(src).resolve().parent, None


def _store_stem(name: str) -> str:
    name = name.rstrip("/").rsplit("/", 1)[-1]
    for suf in (".chromdata.zarr", ".zarr", ".cdz"):
        if name.endswith(suf):
            return name[: -len(suf)]
    return name


def _default_out_dir(cd) -> Tuple[Path, bool]:
    """(directory, whether it is kept) for the maps of ``cd`` when ``out_dir`` is not given."""
    local, url = _store_dir(cd)
    if local is not None:
        return local / f"{_store_stem(str(cd._links_from()))}_pseudobulk", True
    if url is not None:
        from ..datasets import data_dir

        return data_dir() / "pseudobulk" / _store_stem(url), True
    from .maps import _scratch_dir

    return _scratch_dir() / "pseudobulk", False


def _resolution_label(res: int) -> str:
    from .maps import _resolution_label as label

    return label(res)


def _depth_label(n: float) -> str:
    n = float(n)
    return f"{n / 1e9:g}G" if n >= 1e9 else f"{n / 1e6:g}M" if n >= 1e6 else f"{n / 1e3:g}k" if n >= 1e3 else f"{n:g}"


def sample_cells_by_depth(cd, groupby: Union[None, str, Sequence[str], pd.Series, Mapping] = None, *,
                          n_contacts: Union[float, Sequence[float]], replicates: int = 1,
                          contacts: Union[str, pd.Series] = "n_contacts", cells: Optional[Sequence] = None,
                          seed: int = 0) -> pd.DataFrame:
    """Disjoint random sets of cells holding the same number of contacts, per group: the cells of pseudo-bulk
    maps compared at matched depth.

    Each group's cells are shuffled and taken in turn until their contacts reach ``n_contacts`` (the set
    holds at least that many, by less than one cell's contacts more); the next set starts from the cells
    left, so no cell is in two sets.  A group too small for a set gets fewer sets (a warning names it).

    Parameters
    ----------
    cd : ChromData or DataFrame
        Its ``cells`` table (or the table itself).
    groupby
        A column of ``cells``, several columns (the group is their values joined by ``" | "``), a Series /
        mapping cell → group, or ``None`` (all cells one group).
    n_contacts
        Contacts per set; a sequence draws one set per amount (a depth series) from each group.
    replicates
        Sets per group and amount.
    contacts
        The contacts per cell: a column of ``cells`` (default ``"n_contacts"``) or a Series — e.g. the cis
        contacts, ``cells["n_contacts"] * (1 - cells["frac_trans"])``, for maps of cis contacts only.
    cells
        Only these cells (e.g. the cells not drawn by an earlier call).
    seed
        Seed of the shuffles.

    Returns
    -------
    DataFrame
        Index = the drawn cells; ``group``, ``n_contacts`` (the set's target), ``replicate`` (1, 2, ...) and
        ``set`` (``"<group> | <amount> | <replicate>"``, the parts that vary): pass ``sets["set"]`` as the
        ``groupby`` of :func:`pseudobulk`.
    """
    table = cd.cells if hasattr(cd, "cells") else pd.DataFrame(cd)
    w = table[contacts] if isinstance(contacts, str) else pd.Series(contacts)
    w = pd.to_numeric(w.reindex(table.index), errors="coerce").fillna(0.0)
    if groupby is None:
        g = pd.Series("all", index=table.index)
    elif isinstance(groupby, str):
        g = table[groupby].astype(object)
    elif isinstance(groupby, (pd.Series, Mapping)):
        g = pd.Series(groupby).reindex(table.index)
    else:
        g = table[list(groupby)].astype(str).agg(" | ".join, axis=1)
    if cells is not None:
        g = g[g.index.isin(pd.Index(cells))]
    g = g.dropna()
    amounts = [float(n_contacts)] if np.isscalar(n_contacts) else [float(a) for a in n_contacts]
    rng = np.random.default_rng(seed)
    parts, short = [], []
    for name in pd.unique(g.to_numpy()):
        pool = rng.permutation(g.index[g.to_numpy() == name].to_numpy())
        for amount in amounts:
            for k in range(int(replicates)):
                n = int(np.searchsorted(np.cumsum(w.loc[pool].to_numpy()), amount)) + 1
                if n > len(pool):
                    short.append(f"{name} ({_depth_label(amount)}: {k} of {replicates})")
                    break
                parts.append(pd.DataFrame({"group": name, "n_contacts": amount, "replicate": k + 1},
                                          index=pd.Index(pool[:n], name=table.index.name)))
                pool = pool[n:]
    if short:
        warnings.warn("too few contacts for every set: " + ", ".join(short), stacklevel=2)
    if not parts:
        return pd.DataFrame(columns=["group", "n_contacts", "replicate", "set"])
    out = pd.concat(parts)
    label = out["group"].astype(str)
    if len(amounts) > 1:
        label = label + " | " + out["n_contacts"].map(_depth_label)
    if replicates > 1:
        label = label + " | " + out["replicate"].astype(str)
    return out.assign(set=label)


def pseudobulk(cd, groupby: Union[None, str, pd.Series, Mapping] = None, *, contacts: str = "per_cell",
               groups: Optional[Sequence] = None, cells: Optional[Sequence] = None, min_cells: int = 1,
               resolution: Optional[int] = None, trans: bool = True, balance: bool = True,
               out_dir: Union[None, str, os.PathLike] = None, key_prefix: str = "pseudobulk",
               overwrite: bool = False, max_pixels: int = BLOCK_PIXELS, workers: int = READ_WORKERS,
               copy: bool = False, verbose: bool = False):
    """Sum the per-cell contact maps of each group of cells into one ICE-balanced map per group, linked to ``cd``.

    The pseudo-bulk map of a group is the sum over its cells of their contact maps (contacts of every cell
    counted once, as in the per-cell maps — a diploid cell's map already sums its homologs), written as a
    ``.cool`` at the per-cell resolution or a coarser one and balanced by iterative correction (ICE;
    Imakaev et al. 2012, Nat Methods 9:999, with the ``cooler balance`` defaults of Abdennur & Mirny 2020,
    Bioinformatics 36:311: genome-wide, the first two diagonals ignored, bins with < 10 non-zero pixels and
    MAD-max outliers masked).  Summing single-cell maps by cell type into pseudo-bulk maps follows e.g.
    Lee et al. 2019 (Nat Methods 16:999) and Tan et al. 2021 (Cell 184:741).

    Parameters
    ----------
    cd
        ``ChromData`` with per-cell maps linked (``cd.link_scool``): a local ``.scool``, or maps embedded in the
        store it was read from (an atlas store, also over HTTP).
    groupby
        A column of ``cd.cells``, or a ``Series`` / mapping cell id -> group.  ``None``: all cells, one group
        ``"all"``.  Cells without a group (NaN) are left out.
    contacts
        Key of the linked per-cell maps (``cd.uns['linked_scool']``), or the path of a ``.scool`` whose cell
        names are the cell ids.
    groups
        Make only these groups (in this order; default every group, category order for a categorical column).
    cells
        Use only these cells.
    min_cells
        Groups with fewer cells (that have per-cell maps) are skipped, with a warning.
    resolution
        Bin size of the pseudo-bulk maps (bp), a multiple of the per-cell maps' (default: theirs); bin edges at
        ``k * resolution`` and the chromosome ends, as ``cooler coarsen``.
    trans
        Keep the contacts between chromosomes (balanced genome-wide); ``False``: cis only (balanced per
        chromosome, ``cis_only``), which reads far less of an embedded map.
    balance
        ICE-balance the maps (``weight`` column).
    out_dir
        Where the ``.cool`` files go (see the module docstring for the default).  Files are named
        ``<key_prefix>.<group>.<resolution>.cool``.
    key_prefix
        The maps are linked under ``"<key_prefix>.<group>"``; the summary is stored as ``cd.results[key_prefix]``.
    overwrite
        Recompute maps that already exist with the same cells and parameters (default: reuse them).
    max_pixels
        Pixels per read (whole cells; memory of a read: ~24 bytes a pixel).
    workers
        Reads of embedded maps running at once (HTTP range reads overlap; memory: ``workers + 1`` reads).
    copy
        ``True``: link the maps to a copy of ``cd`` and return that.
    verbose
        Print progress.

    Returns
    -------
    DataFrame (``copy=False``)
        One row per group: ``group, n_cells, n_contacts, n_cis, n_pixels, key, path, balanced`` (whether ICE
        converged; None when not balanced), ``reused``.  Or the copy of ``cd`` (``copy=True``).

    Notes
    -----
    Memory: an embedded map is read one chromosome partition at a time, ``workers + 1`` reads of ``max_pixels``
    in flight; the sums of a partition are held per group (a dense array up to ``DENSE_MAX`` entries, sparse
    beyond), so memory is the pseudo-bulk maps plus the reads in flight plus one partition's sums (a ``.scool``
    keeps every partition's sums until its last cell; they share the dense budget).  Time on an atlas store
    over HTTP is the transfer of the per-cell maps (``trans=False`` reads the cis partitions only).
    """
    t_start = time.perf_counter()
    timing = {"read": 0.0, "add": 0.0, "write": 0.0, "balance": 0.0}
    source, src_desc, record = _source_of(cd, contacts, max_pixels)
    lab, order = _cell_groups(cd, groupby, cells, groups, source.cells)
    pos = {c: i for i, c in enumerate(source.cells)}
    has_map = lab.index.isin(list(pos))
    if not has_map.all():
        missing = list(lab.index[~has_map])
        warnings.warn(f"{len(missing)} cells have no per-cell map in {contacts!r} and are left out "
                      f"(e.g. {missing[:3]})", stacklevel=2)
        lab = lab[has_map]
    n_per = lab.value_counts()
    small = [g for g in order if n_per.get(g, 0) < int(min_cells)]
    if small:
        warnings.warn(f"groups with fewer than {min_cells} cells skipped: "
                      + ", ".join(f"{g} ({int(n_per.get(g, 0))})" for g in small), stacklevel=2)
    order = [g for g in order if g not in small]
    if not order:
        raise ValueError("no group of cells to sum")

    base = int(source.base)
    res = int(resolution) if resolution is not None else base
    grid = _Grid(source.chroms, source.sizes, base, res)
    source.check(grid)
    assembly = (record.get("genome_assembly") or source.assembly
                or (cd.uns.get("genome_assembly") if hasattr(cd, "uns") else None))
    if out_dir is None:
        out_dir, kept = _default_out_dir(cd)
    else:
        out_dir, kept = Path(out_dir).expanduser(), True
    out_dir = Path(out_dir)

    names: Dict[str, str] = {}
    for g in order:
        stem = _SAFE.sub("_", g).strip("_") or "group"
        while stem in names.values():
            stem += "_"
        names[g] = stem
    plan = []
    for g in order:
        members = sorted(lab.index[lab.to_numpy() == g])
        md5 = hashlib.md5("\n".join(members).encode()).hexdigest()
        path = out_dir / f"{key_prefix}.{names[g]}.{_resolution_label(res)}.cool"
        meta = {"group": g, "groupby": groupby if isinstance(groupby, str) or groupby is None else "given",
                "n_cells": len(members), "cells_md5": md5, "source": src_desc, "resolution": res,
                "base_resolution": base, "trans": bool(trans), "balance": bool(balance)}
        old = None if overwrite or not path.exists() else _cool_meta(path)
        same = old is not None and all(old.get(k) == v for k, v in meta.items())
        plan.append({"group": g, "members": members, "path": path, "meta": meta, "reuse": same, "old": old})

    todo = [p for p in plan if not p["reuse"]]
    results: Dict[str, dict] = {}
    if todo:
        code = {p["group"]: i for i, p in enumerate(todo)}
        group_of_cell = np.full(len(source.cells), -1, np.int64)
        for p in todo:
            group_of_cell[[pos[c] for c in p["members"]]] = code[p["group"]]
        if verbose:
            print(f"[pseudobulk] {len(todo)} groups, {int((group_of_cell >= 0).sum()):,} cells, "
                  f"{base} -> {res} bp", flush=True)
        parts = _sum_groups(source, grid, group_of_cell, len(todo), trans, timing, workers=int(workers))
        bins = grid.bins()
        for p in todo:
            t0 = time.perf_counter()
            b1, b2, c, n_cis = _group_pixels(parts, grid, code[p["group"]])
            meta = dict(p["meta"], n_contacts=int(c.sum()), n_cis=int(n_cis), n_pixels=int(len(c)),
                        uchrom_function="uchrom.fea.pseudobulk")
            t1 = time.perf_counter()
            conv, t_write, t_balance = _write_cool(p["path"], bins, b1, b2, c, assembly=assembly,
                                                   meta={"pseudobulk": meta}, balance=balance, cis_only=not trans)
            timing["add"] += t1 - t0
            timing["write"] += t_write
            timing["balance"] += t_balance
            results[p["group"]] = {"n_contacts": meta["n_contacts"], "n_cis": meta["n_cis"],
                                   "n_pixels": meta["n_pixels"], "balanced": conv}
            if verbose:
                print(f"[pseudobulk] {p['group']}: {meta['n_cells']:,} cells, {meta['n_contacts']:,} contacts "
                      f"-> {p['path']}", flush=True)
        del parts

    local, _ = _store_dir(cd)
    target = cd.copy() if copy else cd
    rows = []
    for p in plan:
        g = p["group"]
        if p["reuse"]:
            old = p["old"]
            info = {"n_contacts": old.get("n_contacts"), "n_cis": old.get("n_cis"), "n_pixels": old.get("n_pixels"),
                    "balanced": _converged(p["path"]) if balance else None}
        else:
            info = results[g]
        key = f"{key_prefix}.{g}"
        path = p["path"].resolve()
        link = str(path)
        if local is not None and kept:
            try:
                link = os.path.relpath(path, local)
            except ValueError:
                pass
            if link.startswith(".."):
                link = str(path)
        target.link_cool(link, key=key, label=f"Pseudo-bulk: {g} ({len(p['members']):,} cells)",
                         genome_assembly=assembly, bin_size=res,
                         pseudobulk_of=src_desc.get("contacts") or src_desc.get("path"),
                         groupby=p["meta"]["groupby"], group=g, n_cells=len(p["members"]),
                         n_contacts=info["n_contacts"], trans=bool(trans), balanced=bool(balance))
        rows.append({"group": g, "n_cells": len(p["members"]), "n_contacts": info["n_contacts"],
                     "n_cis": info["n_cis"], "n_pixels": info["n_pixels"], "key": key, "path": str(path),
                     "balanced": info["balanced"], "reused": bool(p["reuse"])})
    summary = pd.DataFrame(rows)
    params = {"groupby": groupby if isinstance(groupby, str) or groupby is None else "given",
              "contacts": contacts, "groups": None if groups is None else [str(g) for g in groups],
              "min_cells": int(min_cells), "resolution": res, "trans": bool(trans), "balance": bool(balance),
              "out_dir": str(out_dir), "key_prefix": key_prefix}
    inputs = {"per_cell_maps": src_desc, "n_cells": int(len(lab)), "base_resolution": base,
              "seconds": {k: round(v, 3) for k, v in {**timing, "total": time.perf_counter() - t_start}.items()}}
    target.results.set(key_prefix, summary, kind="table", function="uchrom.fea.pseudobulk", params=params,
                       inputs=inputs)
    if verbose:
        print(f"[pseudobulk] done in {time.perf_counter() - t_start:.1f} s ({inputs['seconds']})", flush=True)
    return target if copy else summary


def _converged(path: Path) -> Optional[bool]:
    try:
        import cooler

        with cooler.Cooler(str(path)).open("r") as h5:
            if "weight" not in h5["bins"]:
                return None
            return bool(np.all(h5["bins/weight"].attrs.get("converged")))
    except Exception:
        return None
