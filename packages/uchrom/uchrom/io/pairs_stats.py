"""Per-cell statistics of contact pairs: how far apart the two ends of each cis contact are (a histogram over
log-spaced distances, per chromosome and per read orientation) and how many contacts are trans.

The distance bins are those of scHiCluster's ``hicluster contact-distance`` (Zhou et al. 2019), which Guo et
al. 2026 used for the short / long-range contact ratio of spatial Hi-C spots: edges
``base * 2 ** (k / per_octave)`` for k = 0 … n, n = floor(per_octave * log2(longest chromosome / base)), 2.5 kb and
8 bins per octave by default.  A contact at distance d = |pos2 - pos1| falls into the bin with
``edges[k] <= d < edges[k + 1]`` (the last bin closed), as in ``numpy.histogram``.  Two more bins keep what
scHiCluster leaves out — d < edges[0] (column 0) and d > edges[-1] (the last column) — so
``histogram[..., 1:-1]`` is scHiCluster's decay vector, bin for bin.

The orientation of a cis contact is that of its reads in genome order (the leg at the smaller position
first): ``++``, ``+-`` (inward), ``-+`` (outward), ``--``.  At short distances the inward and outward pairs
are mostly undigested and self-ligated fragments; the four agree above a few kilobases in good libraries.

:class:`ContactStats` accumulates chunks of contacts for many cells (a spatial Hi-C library: one pairs file,
the cell in the read name); :func:`pairs_contact_stats` reads one pairs file per cell.  The features derived
from the histograms (short / long ratio, contact-decay slope, cis fraction) are
:func:`uchrom.fea.contact_features`.

References
----------
Zhou, J. et al. (2019) Robust single-cell Hi-C clustering by convolution- and random-walk-based imputation.
*PNAS* 116:14011-14018.  Guo, P. et al. (2026) Spatial Hi-C-RNA. *Cell*, doi:10.1016/j.cell.2026.07.039.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Optional, Sequence, Union

import numpy as np

__all__ = ["ORIENTATIONS", "distance_edges", "ContactStats", "pairs_contact_stats"]

#: read orientations of a cis contact in genome order (index = 2 * upstream_minus + downstream_minus)
ORIENTATIONS = ("++", "+-", "-+", "--")


def distance_edges(chromsizes: Optional[Mapping] = None, *, max_distance: Optional[float] = None,
                   base: float = 2500.0, per_octave: int = 8) -> np.ndarray:
    """The edges of the contact-distance bins (bp): ``base * 2 ** (k / per_octave)``, k = 0 … n, with
    n = floor(per_octave * log2(max_distance / base)) and ``max_distance`` the longest chromosome of
    ``chromsizes`` by default.  With the defaults these are scHiCluster's edges, bit for bit."""
    if max_distance is None:
        if not chromsizes:
            raise ValueError("give chromsizes or max_distance")
        max_distance = max(int(v) for v in chromsizes.values())
    n = int(np.floor(np.log2(float(max_distance) / base) / (1.0 / per_octave)))
    return base * np.exp2((1.0 / per_octave) * np.arange(n + 1))


def _strand_minus(strand) -> np.ndarray:
    s = np.asarray(strand)
    if s.dtype == bool:
        return s
    return s.astype(str) == "-"


class ContactStats:
    """Contact-distance histograms and trans counts of many cells, accumulated over chunks of contacts.

    Parameters
    ----------
    cells
        The cell ids (the rows of every array).
    chroms
        The chromosomes counted (contacts with a leg elsewhere are left out and counted in ``n_other``).
    edges
        Distance-bin edges (:func:`distance_edges`).
    orientation
        Keep the histogram per read orientation as well (needs the strands in :meth:`add`).

    Attributes
    ----------
    distance : ndarray (n_cells, n_chroms, n_edges + 1), int64
        Cis contacts per cell, chromosome and distance bin; column 0 is d < edges[0], the last d > edges[-1].
    orientation : ndarray (n_cells, 4, n_edges + 1), int64, or None
        Cis contacts per cell, orientation (:data:`ORIENTATIONS`) and distance bin, summed over chromosomes.
    trans : ndarray (n_cells, n_chroms), int64
        Trans contacts per cell with a leg on each chromosome (a trans contact counts on both of its
        chromosomes; ``trans.sum(1) / 2`` is the number of trans contacts).
    """

    def __init__(self, cells: Sequence, chroms: Sequence[str], edges: np.ndarray, *, orientation: bool = True):
        self.cells = np.asarray([str(c) for c in cells], dtype=object)
        self.chroms = [str(c) for c in chroms]
        self.edges = np.asarray(edges, dtype=float)
        nb = len(self.edges) + 1
        n, m = len(self.cells), len(self.chroms)
        self.distance = np.zeros((n, m, nb), np.int64)
        self.orientation = np.zeros((n, 4, nb), np.int64) if orientation else None
        self.trans = np.zeros((n, m), np.int64)
        self.n_other = 0

    @property
    def n_cis(self) -> np.ndarray:
        return self.distance.sum(axis=(1, 2))

    @property
    def n_trans(self) -> np.ndarray:
        return self.trans.sum(axis=1) // 2

    def distance_bin(self, d: np.ndarray) -> np.ndarray:
        """The histogram column of each distance (0: below the first edge; n_edges: above the last)."""
        j = np.searchsorted(self.edges, d, side="right")
        j[d == self.edges[-1]] = len(self.edges) - 1          # numpy.histogram: the last bin is closed
        return j

    def add(self, cell, chrom1, pos1, chrom2, pos2, strand1=None, strand2=None) -> None:
        """Count a chunk of contacts.

        ``cell`` is the row of each contact (-1: not counted), ``chrom1`` / ``chrom2`` the index of its
        chromosomes in ``chroms`` (-1: another chromosome), ``pos1`` / ``pos2`` its positions;
        ``strand1`` / ``strand2`` ('+' / '-' or booleans for '-') are needed when ``orientation`` is kept.
        """
        cell = np.asarray(cell, np.int64)
        c1 = np.asarray(chrom1, np.int64)
        c2 = np.asarray(chrom2, np.int64)
        p1 = np.asarray(pos1, np.int64)
        p2 = np.asarray(pos2, np.int64)
        has = cell >= 0
        ok = has & (c1 >= 0) & (c2 >= 0)
        self.n_other += int((has & ~ok).sum())
        n, m, nb = self.distance.shape
        cis = ok & (c1 == c2)
        cc, ch = cell[cis], c1[cis]
        d = np.abs(p2[cis] - p1[cis])
        j = self.distance_bin(d)
        self.distance += np.bincount((cc * m + ch) * nb + j, minlength=n * m * nb).reshape(n, m, nb)
        if self.orientation is not None:
            if strand1 is None or strand2 is None:
                raise ValueError("orientation=True needs strand1 / strand2")
            m1 = _strand_minus(strand1)[cis]
            m2 = _strand_minus(strand2)[cis]
            swap = p1[cis] > p2[cis]                            # read the legs in genome order
            up, down = np.where(swap, m2, m1), np.where(swap, m1, m2)
            o = 2 * up.astype(np.int64) + down.astype(np.int64)
            self.orientation += np.bincount((cc * 4 + o) * nb + j, minlength=n * 4 * nb).reshape(n, 4, nb)
        tr = ok & (c1 != c2)
        legs = np.r_[cell[tr] * m + c1[tr], cell[tr] * m + c2[tr]]
        self.trans += np.bincount(legs, minlength=n * m).reshape(n, m)

    def merge(self, other: "ContactStats") -> "ContactStats":
        """Add another accumulator over the same cells, chromosomes and edges (e.g. of another file)."""
        if (list(other.cells) != list(self.cells) or other.chroms != self.chroms
                or not np.array_equal(other.edges, self.edges)):
            raise ValueError("ContactStats.merge: cells, chromosomes and edges must match")
        self.distance += other.distance
        self.trans += other.trans
        if self.orientation is not None and other.orientation is not None:
            self.orientation += other.orientation
        self.n_other += other.n_other
        return self

    def save(self, path: Union[str, os.PathLike], **meta) -> None:
        """Write the arrays to one ``.npz`` (``meta``: JSON-able notes, e.g. the filters applied)."""
        arrays = {"cells": self.cells.astype(str), "chroms": np.asarray(self.chroms, dtype=str),
                  "edges": self.edges, "distance": self.distance, "trans": self.trans,
                  "n_other": np.int64(self.n_other), "meta": np.asarray(json.dumps(meta))}
        if self.orientation is not None:
            arrays["orientation"] = self.orientation
        np.savez_compressed(path, **arrays)

    @classmethod
    def load(cls, path: Union[str, os.PathLike]) -> "ContactStats":
        with np.load(path, allow_pickle=False) as z:
            out = cls(z["cells"], list(z["chroms"]), z["edges"], orientation="orientation" in z.files)
            out.distance = z["distance"].astype(np.int64)
            out.trans = z["trans"].astype(np.int64)
            if out.orientation is not None:
                out.orientation = z["orientation"].astype(np.int64)
            out.n_other = int(z["n_other"])
            out.meta = json.loads(str(z["meta"])) if "meta" in z.files else {}
        return out

    def write(self, cd, *, key: str = "contacts", source: Optional[str] = None, per_chromosome: bool = True,
              dtype=np.int64) -> None:
        """Store the histograms on ``cd``, aligned to ``cd.cells`` by cell id (cells without counts get zeros).

        ``cd.cellm["<key>.distance"]``: (n_cells, n_chroms, n_bins), or (n_cells, n_bins) summed over the
        chromosomes with ``per_chromosome=False`` (an atlas store: 21-24x smaller); ``["<key>.orientation"]``
        (n_cells, 4, n_bins); ``["<key>.cis"]`` and ``["<key>.trans"]`` (n_cells, n_chroms; trans: legs on each
        chromosome); the columns ``<key>.n_cis`` / ``<key>.n_trans`` of ``cd.cells``; the record
        ``cd.uns["contact_stats"][key]`` (edges, chromosomes, orientations, columns).  ``dtype``: of the arrays
        (int32 holds any spot's counts)."""
        ids = np.asarray([str(c) for c in _cell_ids(cd)], dtype=object)
        row = {c: i for i, c in enumerate(self.cells)}
        take = np.array([row.get(c, -1) for c in ids], np.int64)

        def aligned(arr):
            out = np.zeros((len(ids),) + arr.shape[1:], dtype)
            out[take >= 0] = arr[take[take >= 0]]
            return out

        dist = aligned(self.distance if per_chromosome else self.distance.sum(axis=1))
        cd.cellm[f"{key}.distance"] = dist
        cd.cellm[f"{key}.cis"] = aligned(self.distance.sum(axis=2))
        cd.cellm[f"{key}.trans"] = aligned(self.trans)
        if self.orientation is not None:
            cd.cellm[f"{key}.orientation"] = aligned(self.orientation)
        cells = cd.cells.copy()
        cells[f"{key}.n_cis"] = cd.cellm[f"{key}.cis"].sum(axis=1).astype(np.int64)
        cells[f"{key}.n_trans"] = cd.cellm[f"{key}.trans"].sum(axis=1).astype(np.int64) // 2
        cd.cells = cells
        rec = dict(cd.uns.get("contact_stats", {}))
        rec[key] = {"edges": [float(e) for e in self.edges], "chroms": list(self.chroms),
                    "per_chromosome": bool(per_chromosome),
                    "orientations": list(ORIENTATIONS) if self.orientation is not None else None,
                    "columns": "column 0: d < edges[0]; column k: edges[k-1] <= d < edges[k]; last: d > edges[-1]",
                    "n_cells_counted": int((take >= 0).sum()), "source": source,
                    **{k: v for k, v in getattr(self, "meta", {}).items() if k not in ("edges", "chroms")}}
        cd.uns["contact_stats"] = rec


def _cell_ids(cd) -> np.ndarray:
    """The ids of the rows of ``cd.cells`` (as ``cd.cell_positions`` indexes them)."""
    return np.asarray(cd._cell_ids_axis(), dtype=str)


def pairs_contact_stats(cells: Mapping, *, chromsizes: Mapping, edges: Optional[np.ndarray] = None,
                        chunk_lines: Optional[int] = None) -> ContactStats:
    """:class:`ContactStats` of per-cell contact files (``{cell: path}``, the inputs of
    :func:`~uchrom.io.pairs_to_scool`).  The files' strands are not read, so ``orientation`` is None;
    chromosome names match with or without a ``chr`` prefix."""
    from .pairs_maps import CHUNK_LINES, _chrom_codes, _strip, iter_pairs

    names = [str(c) for c in chromsizes]
    lookup = {c: i for i, c in enumerate(names)}
    lookup.update({_strip(c): i for i, c in enumerate(names)})
    stats = ContactStats(list(cells), names, distance_edges(chromsizes) if edges is None else edges,
                         orientation=False)
    for row, src in enumerate(cells.values()):
        for chunk in iter_pairs(src, chunk_lines=chunk_lines or CHUNK_LINES):
            n = len(chunk)
            stats.add(np.full(n, row), _chrom_codes(chunk["chrom1"], lookup), chunk["pos1"].to_numpy(),
                      _chrom_codes(chunk["chrom2"], lookup), chunk["pos2"].to_numpy())
    return stats
