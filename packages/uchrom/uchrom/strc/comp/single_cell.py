"""Single-cell compartment values (scA/B): where each bin of one cell sits between A and B, from its contacts.

A single cell's contact map is far too sparse for the eigenvector of :func:`call_compartments_eig`, but the
contact partners of a bin still say whether it sits in A or B: A (active, GC- and CpG-rich) regions contact
CpG-rich regions, B regions CpG-poor ones.  The **scA/B value** of a bin in a cell is the mean CpG frequency of
the bins it contacts in that cell (Tan et al. 2018, *Science* 361:924; Tan et al. 2021, *Cell* 184:741):

    scA/B(cell, i) = sum_j n_ij(cell) * CpG(j) / sum_j n_ij(cell),  j != i, CpG(j) defined

with ``n_ij(cell)`` the cell's contacts between bins ``i`` and ``j`` (every contact counted once per leg, as in
Dip-C ``color2``: a contact between ``i`` and ``j`` adds ``CpG(j)`` to ``i`` and ``CpG(i)`` to ``j``).  The two
published forms differ in which contacts count and in the normalisation per cell:

* **Dip-C** (Tan et al. 2021: ``dip-c color2 -b1000000 -H -c mm10.cpg.1m.txt -s contacts.con.gz``, then
  ``scripts/color_to_rank.py``; github.com/tanlongzhi/dip-c): every contact, intra- and inter-chromosomal, of
  both homologs (``-H``), contacts within one bin left out; the values of each cell are replaced by their ranks
  scaled to 0-1 ("rank-normalized CpG density in its 3D neighborhood", 1-Mb bins, PCA → t-SNE of the
  cells × bins matrix: "structure typing").  ``ScABParams()`` (the defaults).
* **scHiCluster** ``comp-cpg-cell`` / ``hicluster compartment`` (Zhou et al. 2019, *PNAS* 116:14011;
  github.com/zhoujt1994/scHiCluster, "adopted from Tan, Xing et al. 2018"; the compartment scores of the
  snm3C-seq studies): each chromosome on its own (cis contacts), the diagonal removed, the row-normalised map
  times the CpG ratio of the bins, no normalisation across bins.  ``ScABParams(contacts="cis",
  normalize="none")``.

The CpG frequency is Dip-C's (``scripts/cpg.sh``): CG dinucleotides over the dinucleotides whose two bases are
A/C/G/T, from a genome FASTA (:func:`uchrom.fea.compute_sequence_features`, ``cpg_frequency``); any other track
on the bins works (GC content, the E1 of a bulk map of the same cell type).

The per-cell maps are those linked to the ``ChromData`` (``cd.link_scool``): a local ``.scool`` or maps embedded
in an atlas store (also over HTTP).  They are read in blocks of cells (one range read per chromosome partition
and block, as :func:`uchrom.fea.pseudobulk` reads them), and the sums are a sparse matrix-vector product per
cell (``numpy.bincount``): memory is one block's sums plus the result (cells × bins, float32).
"""

from __future__ import annotations

import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

__all__ = ["ScABParams", "single_cell_compartments", "scab_sums", "normalize_scab"]

#: bytes of the per-block sums (two float64 arrays of block cells × bins): sets the cells per block
BLOCK_BYTES = 256 << 20

_CONTACTS = ("all", "cis", "trans")
_NORMALIZE = ("rank", "zscore", "none")


@dataclass(frozen=True)
class ScABParams:
    """Knobs of :func:`single_cell_compartments` (defaults: Dip-C, Tan et al. 2021).

    ``contacts``: which contacts count — ``"all"`` (intra- and inter-chromosomal; Dip-C ``color2``), ``"cis"``
    (each chromosome on its own; scHiCluster) or ``"trans"``.  ``min_separation``: intra-chromosomal contacts
    between bins fewer than this many bins apart are left out (1: only contacts within one bin, as both
    implementations).  ``normalize``: per cell, over the bins returned — ``"rank"`` (ranks, ties averaged,
    scaled to 0-1: Dip-C ``color_to_rank.py``), ``"zscore"`` or ``"none"`` (the mean CpG frequency of the
    partners: scHiCluster).  ``min_contacts``: a bin gets a value in a cell when it has at least this many
    contacts with partners that have a track value (NaN otherwise).  ``sequence_feature``: the track computed
    when ``track`` is a FASTA (``"cpg_frequency"``: Dip-C; ``"cpg_density"``, ``"gc_fraction"``).
    """

    contacts: str = "all"
    min_separation: int = 1
    normalize: str = "rank"
    min_contacts: int = 1
    sequence_feature: str = "cpg_frequency"

    def check(self) -> None:
        if self.contacts not in _CONTACTS:
            raise ValueError(f"ScABParams.contacts={self.contacts!r}: one of {_CONTACTS}")
        if self.normalize not in _NORMALIZE:
            raise ValueError(f"ScABParams.normalize={self.normalize!r}: one of {_NORMALIZE}")
        if int(self.min_separation) < 1:
            raise ValueError("ScABParams.min_separation must be at least 1 (contacts within a bin never count)")
        if int(self.min_contacts) < 1:
            raise ValueError("ScABParams.min_contacts must be at least 1")


# ------------------------------------------------------------------ the kernel


class _Sums:
    """Per cell and bin: the contacts with partners that have a track value (``den``) and the sum of the
    partners' values (``num``), for ``n_rows`` cells; contacts are added as pixels ``(row, bin1, bin2,
    count)`` on genome-wide bins."""

    def __init__(self, n_rows: int, track: np.ndarray, chrom_of_bin: np.ndarray, params: ScABParams):
        self.n, self.nb = int(n_rows), len(track)
        ok = np.isfinite(track)
        self.ok = ok.astype(np.float64)
        self.t = np.where(ok, track, 0.0).astype(np.float64)          # 0 where undefined: adds nothing
        self.chrom = np.asarray(chrom_of_bin)
        self.p = params
        self.num = np.zeros((self.n, self.nb))
        self.den = np.zeros((self.n, self.nb))
        self.n_contacts = np.zeros(self.n)

    def add(self, rows: np.ndarray, b1: np.ndarray, b2: np.ndarray, count: np.ndarray,
            cis: Union[None, bool, np.ndarray] = None) -> None:
        """``cis``: whether each pixel is intra-chromosomal (an array, or one bool for a whole partition;
        None: from the bins)."""
        if not len(rows):
            return
        if cis is None:
            cis = self.chrom[b1] == self.chrom[b2]
        if isinstance(cis, (bool, np.bool_)):
            if (self.p.contacts == "cis" and not cis) or (self.p.contacts == "trans" and cis):
                return
            keep = (b1 != b2) if cis else None                       # trans pixels are never on the diagonal
            if cis and self.p.min_separation > 1:
                keep &= np.abs(b1 - b2) >= int(self.p.min_separation)
        else:
            keep = b1 != b2
            if self.p.contacts == "cis":
                keep &= cis
            elif self.p.contacts == "trans":
                keep &= ~cis
            if self.p.min_separation > 1:
                keep &= ~cis | (np.abs(b1 - b2) >= int(self.p.min_separation))
        # pixels left out weigh 0 (cheaper than dropping them)
        c = count.astype(np.float64) if keep is None else np.where(keep, count, 0).astype(np.float64)
        self.n_contacts += np.bincount(rows, weights=c, minlength=self.n)
        # the sums of this chunk on the cells and bins it touches only (a cis partition: one chromosome)
        lo, hi = int(rows.min()), int(rows.max()) + 1
        b0 = int(min(b1.min(), b2.min()))
        width = int(max(b1.max(), b2.max())) + 1 - b0
        span = (hi - lo) * width
        base = (rows - lo) * width - b0
        for a, b in ((b1, b2), (b2, b1)):                # each leg takes its partner's value
            idx = base + a
            self.den[lo:hi, b0:b0 + width] += np.bincount(idx, weights=c * self.ok[b],
                                                          minlength=span).reshape(hi - lo, width)
            self.num[lo:hi, b0:b0 + width] += np.bincount(idx, weights=c * self.t[b],
                                                          minlength=span).reshape(hi - lo, width)

    def values(self, columns: Optional[np.ndarray] = None) -> np.ndarray:
        num, den = (self.num, self.den) if columns is None else (self.num[:, columns], self.den[:, columns])
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(den >= self.p.min_contacts, num / den, np.nan)


def scab_sums(rows, bin1, bin2, count, track, *, n_rows: Optional[int] = None,
              chrom_of_bin: Optional[np.ndarray] = None,
              params: Optional[ScABParams] = None) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The raw scA/B values of in-memory pixels: the kernel of :func:`single_cell_compartments`.

    Parameters
    ----------
    rows, bin1, bin2, count : array-like
        One entry per pixel (or per contact): the cell (row of the result, ``0 .. n_rows-1``), its two bins
        (genome-wide indices into ``track``) and its count.  Each pixel counts once (give the upper triangle
        of a symmetric map).
    track : array-like (n_bins,)
        The value of every bin (CpG frequency); NaN: the bin is no partner.
    n_rows : int, optional
        Cells (default ``max(rows) + 1``).
    chrom_of_bin : array-like (n_bins,), optional
        Chromosome of each bin (any labels), for the cis / trans selection and ``min_separation``; default:
        one chromosome.
    params : ScABParams, optional
        ``contacts``, ``min_separation``, ``min_contacts`` apply; no normalisation (:func:`normalize_scab`).

    Returns
    -------
    values : ndarray (n_rows, n_bins)
        Mean track value of each bin's partners in each cell (NaN below ``min_contacts``).
    partner_contacts : ndarray (n_rows, n_bins)
        The contacts averaged over (those with a partner that has a track value).
    n_contacts : ndarray (n_rows,)
        The contacts counted per cell (after the cis / trans and separation filters).
    """
    params = params or ScABParams()
    params.check()
    rows = np.asarray(rows, np.int64)
    b1, b2 = np.asarray(bin1, np.int64), np.asarray(bin2, np.int64)
    track = np.asarray(track, np.float64)
    n = int(n_rows) if n_rows is not None else (int(rows.max()) + 1 if len(rows) else 0)
    chrom = np.zeros(len(track), np.int64) if chrom_of_bin is None else np.asarray(chrom_of_bin)
    s = _Sums(n, track, chrom, params)
    s.add(rows, b1, b2, np.asarray(count))
    return s.values(), s.den, s.n_contacts


def _row_ranks(x: np.ndarray) -> np.ndarray:
    """Ranks (1-based, ties averaged: ``scipy.stats.rankdata``) of every row of ``x``, vectorised."""
    n, m = x.shape
    if m == 0:
        return np.zeros_like(x, dtype=np.float64)
    order = np.argsort(x, axis=1, kind="stable")
    s = np.take_along_axis(x, order, axis=1)
    pos = np.broadcast_to(np.arange(m), (n, m))
    new = np.ones((n, m), bool)
    new[:, 1:] = s[:, 1:] != s[:, :-1]
    first = np.maximum.accumulate(np.where(new, pos, 0), axis=1)          # start of each run of ties
    last_mark = np.ones((n, m), bool)
    last_mark[:, :-1] = new[:, 1:]
    last = np.minimum.accumulate(np.where(last_mark, pos, m)[:, ::-1], axis=1)[:, ::-1]
    ranks = np.empty((n, m), np.float64)
    np.put_along_axis(ranks, order, (first + last) / 2.0 + 1.0, axis=1)
    return ranks


def normalize_scab(values: np.ndarray, method: str = "rank") -> np.ndarray:
    """Normalise raw scA/B values per cell (row), over the finite entries of the row.

    ``"rank"``: ranks (ties averaged) scaled to 0-1, ``(rank - 1) / (n - 1)`` (Dip-C ``color_to_rank.py``,
    Tan et al. 2021); ``"zscore"``: minus the row mean, over the row standard deviation; ``"none"``: unchanged.
    Rows with fewer than two finite values become NaN (except ``"none"``).
    """
    x = np.asarray(values, dtype=np.float64)
    if method == "none":
        return x
    finite = np.isfinite(x)
    n = finite.sum(axis=1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        if method == "rank":
            out = (_row_ranks(np.where(finite, x, np.inf)) - 1.0) / (n - 1.0)
        elif method == "zscore":
            mean = np.nansum(x, axis=1, keepdims=True) / n
            sd = np.sqrt(np.nansum((x - mean) ** 2, axis=1, keepdims=True) / n)
            out = (x - mean) / sd
        else:
            raise ValueError(f"normalize={method!r}: one of {_NORMALIZE}")
    out[~finite] = np.nan
    out[(n < 2)[:, 0]] = np.nan
    return out


# ------------------------------------------------------------------ inputs


def _track_values(cd, track, bins: pd.DataFrame, feature: str) -> Tuple[np.ndarray, str]:
    """The track on the map ``bins`` (all of them) and a description for provenance."""
    from .eig import _is_fasta, _phasing_values

    if track is None:
        raise ValueError("single_cell_compartments needs a track: a genome FASTA (the CpG frequency of every bin, "
                         "e.g. uchrom.datasets.fetch('mm10_genome')), a cd.bin_tracks column or a DataFrame "
                         "chrom, start, end, value")
    if isinstance(track, np.ndarray) or (isinstance(track, (list, tuple)) and len(track) == len(bins)):
        values = np.asarray(track, dtype=np.float64)
        if values.shape != (len(bins),):
            raise ValueError(f"a track array needs one value per map bin ({len(bins)}), got {values.shape}")
        return values, "array"
    if isinstance(track, (str, Path)) and _is_fasta(track):
        from uchrom.fea.sequence import compute_sequence_features

        path = Path(track).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"track FASTA {path} does not exist")
        values = compute_sequence_features(bins[["chrom", "start", "end"]], path, features=[feature],
                                           missing="ignore")[feature].to_numpy(dtype=np.float64)
        return values, f"{feature} of {path}"
    values, label = _phasing_values(cd, track, bins)
    return np.asarray(values, dtype=np.float64), label


def _select_cells(cd, cells, source_cells: Sequence[str]) -> Tuple[List[str], np.ndarray]:
    """(the cell ids of ``cd.cells``, sorted positions in the source of the selected cells that have maps)."""
    ids = [str(c) for c in cd.cells.index]
    if not ids:
        raise ValueError("cd.cells is empty: the result is one row per cell")
    want = ids if cells is None else [str(c) for c in cells]
    unknown = sorted(set(want) - set(ids))
    if unknown:
        raise KeyError(f"cells not in cd.cells: {unknown[:5]}")
    pos = {c: i for i, c in enumerate(source_cells)}
    missing = [c for c in want if c not in pos]
    if missing:
        warnings.warn(f"{len(missing)} cells have no per-cell map and get NaN (e.g. {missing[:3]})", stacklevel=3)
    src = np.unique(np.array([pos[c] for c in want if c in pos], dtype=np.int64))
    return ids, src


def _embedded_tasks(source, blocks: List[np.ndarray], parts: List[Tuple[int, str]]):
    """``(block, task)`` reads, block by block and within a block partition by partition: ``task`` as
    :meth:`_EmbeddedSource.read` takes it (cells of one range read adding up to about ``max_pixels``)."""
    e, r = source.e, source.base
    for k, idx in enumerate(blocks):
        for p, name in parts:
            off = e._offsets(r, name, "cell_offset")
            n = off[idx + 1] - off[idx]
            cells, n = idx[n > 0], n[n > 0]
            cum = np.cumsum(n)
            start = 0
            while start < len(cells):
                base = cum[start - 1] if start else 0
                end = max(int(np.searchsorted(cum, base + source.max_pixels, side="right")), start + 1)
                yield k, (p, name, cells[start:end], n[start:end])
                start = end


def _iter_block_pixels(source, grid, blocks: List[np.ndarray], params: ScABParams, workers: int,
                       timing: Dict[str, float]) -> Iterator[Tuple[int, np.ndarray, np.ndarray, np.ndarray,
                                                                    np.ndarray, Optional[bool]]]:
    """``(block, source cell of each pixel, bin1, bin2, count, cis)`` with genome-wide bins of the grid, the
    blocks in order; ``cis``: whether the chunk is a cis (True) or the trans (False) partition, None when it
    is to be derived from the bins."""
    from uchrom.fea.pseudobulk_maps import _prefetch

    f = grid.factor
    if source.sequential:                                            # embedded maps: partition reads
        parts = source.partitions(trans=params.contacts != "cis")
        if params.contacts == "trans":
            parts = [(p, n) for p, n in parts if p < 0]

        def read(item):
            k, task = item
            return k, source.read(task)

        t_read = time.perf_counter()
        for k, (p, cell, b1, b2, c) in _prefetch(read, _embedded_tasks(source, blocks, parts), workers):
            t0 = time.perf_counter()
            timing["read"] += t0 - t_read
            if p >= 0:
                off = int(grid.first_coarse[p])
                g1, g2 = (b1 // f if f > 1 else b1) + off, (b2 // f if f > 1 else b2) + off
                cis = True
            else:
                g1, g2 = (grid.f2c()[b1], grid.f2c()[b2]) if f > 1 else (np.ascontiguousarray(b1),
                                                                         np.ascontiguousarray(b2))
                cis = False
            timing["bin"] += time.perf_counter() - t0
            yield k, cell, g1, g2, c, cis
            t_read = time.perf_counter()
        return
    for k, idx in enumerate(blocks):                                 # a .scool: whole cells
        t_read = time.perf_counter()
        for cell, b1, b2, c in source.iter_cells(idx):
            t0 = time.perf_counter()
            timing["read"] += t0 - t_read
            g1, g2 = (grid.f2c()[b1], grid.f2c()[b2]) if f > 1 else (b1, b2)
            timing["bin"] += time.perf_counter() - t0
            yield k, cell, g1, g2, c, None
            t_read = time.perf_counter()


def _label(chrom, start, end) -> str:
    return f"{chrom}:{int(start)}-{int(end)}"


# ------------------------------------------------------------------ the caller


def single_cell_compartments(
    cd,
    *,
    contacts: str = "per_cell",
    track=None,
    cells: Optional[Sequence] = None,
    chrom=None,
    resolution: Optional[int] = None,
    params: Optional[ScABParams] = None,
    key_added: Optional[str] = "compartments.scab",
    copy: bool = False,
    max_pixels: Optional[int] = None,
    workers: Optional[int] = None,
    verbose: bool = False,
):
    """Single-cell compartment values (scA/B): per cell and bin, the mean CpG frequency of the bin's contact
    partners in that cell, normalised per cell.

    The definition of Tan et al. 2018 (*Science* 361:924) and 2021 (*Cell* 184:741; Dip-C ``color2`` +
    ``color_to_rank.py``): every contact of a cell between bins ``i != j`` adds the track value (CpG frequency)
    of ``j`` to ``i`` and that of ``i`` to ``j``; the value of a bin is the mean over its contacts; each cell's
    values are then replaced by their ranks scaled to 0-1.  ``ScABParams(contacts="cis", normalize="none")``
    gives the compartment score of scHiCluster ``comp-cpg-cell`` (Zhou et al. 2019, *PNAS* 116:14011): cis
    contacts only, no normalisation.  A bin's value is high (A-like) when it contacts CpG-rich regions.  The
    cells × bins matrix separates cell types (PCA → t-SNE: Tan et al. 2021's "structure typing") and, averaged
    over the cells of a type, follows the type's bulk compartment eigenvector.

    Parameters
    ----------
    cd : ChromData
        With ``cells`` and per-cell maps linked (``cd.link_scool``): a local ``.scool``, or maps embedded in
        the store it was read from (an atlas store, also over HTTP).
    contacts : str
        Key of the linked per-cell maps (``cd.uns['linked_scool']``), or the path of a ``.scool`` whose cell
        names are the cell ids.
    track : path, str, DataFrame or ndarray
        The value of every map bin: the path of a genome FASTA (``params.sequence_feature`` of each bin, Dip-C's
        CpG frequency by default; :func:`uchrom.fea.compute_sequence_features`; e.g.
        ``uchrom.datasets.fetch("mm10_genome")``), a ``cd.bin_tracks`` column, the key of a compartment table in
        ``cd.results`` (its ``E1``), a DataFrame ``chrom, start, end`` + one value column (each map bin takes the
        mean of the loci whose midpoint it holds), or an array with one value per map bin.  The values computed
        are kept in the result table (column ``track``): pass that table to skip the FASTA next time.
    cells : sequence of cell ids, optional
        Cells to compute (default: every cell of ``cd.cells`` with a map); the other rows are NaN.
    chrom : str, sequence of str, or None
        Chromosomes whose bins are returned (and ranked); default every chromosome of the maps.  Partners on
        every chromosome count (``params.contacts``).
    resolution : int, optional
        Bin size (bp), a multiple of the per-cell maps' (default: theirs).
    params : ScABParams, optional
        Which contacts, the normalisation, the minimum contacts per bin.
    key_added : str or None
        ``cd.results`` / ``cd.cellm`` key (default ``"compartments.scab"``); ``None`` does not store.
    copy : bool
        ``True`` → return a new ChromData holding the result.
    max_pixels, workers
        Pixels per read and reads in flight (embedded maps; defaults of :func:`uchrom.fea.pseudobulk`).
    verbose : bool
        Print progress.

    Returns
    -------
    DataFrame (``copy=False``) or ChromData (``copy=True``)
        Cells (the computed ones) × bins (``"chrom:start-end"``), float32; NaN where a bin has fewer than
        ``params.min_contacts`` contacts with partners that have a track value.  When stored: the matrix
        for every cell of ``cd.cells`` as ``cd.cellm[key_added]`` (NaN rows for cells not computed), the bins as
        the table ``cd.results[key_added]`` (``chrom, start, end, track, n_cells`` — cells with a value —,
        ``mean``, ``sd`` over the cells; row ``k`` = column ``k`` of the matrix) with the call's provenance, and
        per cell ``cd.cells[f"{key_added}.n_contacts"]`` (contacts counted) and ``cd.cells[f"{key_added}.n_bins"]``
        (bins with a value).

    Notes
    -----
    Bins: those of the per-cell maps (``[k * resolution, (k + 1) * resolution)``); Dip-C centres its bins on
    multiples of the bin size — the values differ by that half-bin shift only.  Memory: per block of cells the
    two sums (``BLOCK_BYTES``) plus the reads in flight, and the result (cells × bins, float32).  Time on an
    atlas store over HTTP is mostly the transfer of the per-cell maps (``contacts="cis"`` reads no trans
    partition).
    """
    from uchrom.fea.maps import _is_chromdata
    from uchrom.fea.pseudobulk_maps import BLOCK_PIXELS, READ_WORKERS, _Grid, _source_of

    t_start = time.perf_counter()
    params = params or ScABParams()
    params.check()
    if not _is_chromdata(cd):
        raise TypeError("single_cell_compartments needs a ChromData with per-cell maps linked")
    if copy and key_added is None:
        raise ValueError("single_cell_compartments(): copy=True needs a key_added")
    timing = {"track": 0.0, "read": 0.0, "bin": 0.0, "sum": 0.0, "normalize": 0.0}
    source, src_desc, record = _source_of(cd, contacts, int(max_pixels or BLOCK_PIXELS))
    ids, src_idx = _select_cells(cd, cells, source.cells)
    if not len(src_idx):
        raise ValueError("no selected cell has a per-cell map")

    base = int(source.base)
    res = int(resolution) if resolution is not None else base
    grid = _Grid(source.chroms, source.sizes, base, res)
    source.check(grid)
    gbins = grid.bins().reset_index(drop=True)
    gbins["chrom"] = gbins["chrom"].astype(str)
    chrom_of_bin = np.repeat(np.arange(len(grid.chroms)), grid.n_coarse)
    if chrom is None:
        chroms = list(grid.chroms)
    else:
        chroms = [chrom] if isinstance(chrom, str) else [str(c) for c in chrom]
        missing = [c for c in chroms if c not in grid.chroms]
        if missing:
            raise ValueError(f"not in the per-cell maps: {missing} (they have {grid.chroms})")
    columns = np.flatnonzero(np.isin(gbins["chrom"].to_numpy(), chroms))

    t0 = time.perf_counter()
    values_track, track_label = _track_values(cd, track, gbins[["chrom", "start", "end"]], params.sequence_feature)
    timing["track"] = time.perf_counter() - t0
    if not np.isfinite(values_track).any():
        raise ValueError(f"the track ({track_label}) has no value on the map bins (chromosome names?)")

    nb = len(gbins)
    per_block = max(1, int(BLOCK_BYTES // (16 * nb)))
    blocks = [src_idx[s:s + per_block] for s in range(0, len(src_idx), per_block)]
    pos_in_cd = pd.Index(ids).get_indexer([source.cells[i] for i in src_idx])
    out = np.full((len(src_idx), len(columns)), np.nan, dtype=np.float32)
    n_contacts = np.zeros(len(src_idx), np.int64)
    row_of_src = np.full(len(source.cells), -1, np.int64)
    row_of_src[src_idx] = np.arange(len(src_idx))
    if verbose:
        print(f"[scab] {len(src_idx):,} cells, {nb:,} bins at {res:,} bp ({len(columns):,} returned), "
              f"{len(blocks)} blocks of <= {per_block:,} cells, contacts={params.contacts}", flush=True)

    def finish(k: int, sums: _Sums) -> None:
        t1 = time.perf_counter()
        r0 = int(row_of_src[blocks[k][0]])
        vals = normalize_scab(sums.values(columns), params.normalize)
        out[r0:r0 + len(blocks[k])] = vals
        n_contacts[r0:r0 + len(blocks[k])] = np.rint(sums.n_contacts).astype(np.int64)
        timing["normalize"] += time.perf_counter() - t1
        if verbose:
            print(f"[scab] block {k + 1}/{len(blocks)}: {r0 + len(blocks[k]):,} cells done "
                  f"({time.perf_counter() - t_start:.1f} s)", flush=True)

    def new(k: int) -> _Sums:
        return _Sums(len(blocks[k]), values_track, chrom_of_bin, params)

    cur, sums = 0, new(0)
    for k, cell, g1, g2, c, cis in _iter_block_pixels(source, grid, blocks, params,
                                                      int(workers or READ_WORKERS), timing):
        t1 = time.perf_counter()
        while cur < k:                       # blocks come in order; one without any pixel is finished too
            finish(cur, sums)
            cur += 1
            sums = new(cur)
        rows = row_of_src[cell] - int(row_of_src[blocks[k][0]])
        sums.add(rows, g1.astype(np.int64, copy=False), g2.astype(np.int64, copy=False), c, cis)
        timing["sum"] += time.perf_counter() - t1
    finish(cur, sums)
    for k in range(cur + 1, len(blocks)):
        finish(k, new(k))

    out_bins = gbins.iloc[columns].reset_index(drop=True)
    labels = [_label(*row) for row in out_bins[["chrom", "start", "end"]].itertuples(index=False)]
    cell_ids = [source.cells[i] for i in src_idx]
    frame = pd.DataFrame(out, index=pd.Index(cell_ids, name="cell_id"), columns=labels, copy=False)
    if key_added is None:
        return frame

    finite = np.isfinite(out)
    with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        table = out_bins.assign(track=values_track[columns], n_cells=finite.sum(axis=0).astype(np.int64),
                                mean=np.nanmean(out, axis=0).astype(np.float64),
                                sd=np.nanstd(out, axis=0).astype(np.float64))
    matrix = np.full((len(ids), len(columns)), np.nan, dtype=np.float32)
    matrix[pos_in_cd] = out
    target = cd.copy() if copy else cd
    cells_tab = target.cells.copy()
    nc = np.full(len(ids), np.nan)
    nc[pos_in_cd] = n_contacts
    nbv = np.full(len(ids), np.nan)
    nbv[pos_in_cd] = finite.sum(axis=1)
    cells_tab[f"{key_added}.n_contacts"] = nc
    cells_tab[f"{key_added}.n_bins"] = nbv
    target.cells = cells_tab
    target.cellm[key_added] = matrix
    seconds = {k: round(v, 3) for k, v in {**timing, "total": time.perf_counter() - t_start}.items()}
    inputs = {"per_cell_maps": src_desc, "resolution": res, "base_resolution": base, "track": track_label,
              "chrom": list(chroms), "n_cells": int(len(src_idx)), "n_cells_requested":
              len(ids) if cells is None else len(list(cells)), "cellm": key_added,
              "genome_assembly": record.get("genome_assembly") or cd.uns.get("genome_assembly"),
              "seconds": seconds}
    target.results.set(key_added, table, kind="table", function="uchrom.strc.comp.single_cell_compartments",
                       params=params, inputs=inputs)
    if verbose:
        print(f"[scab] done in {seconds['total']:.1f} s ({seconds})", flush=True)
    return target if copy else frame
