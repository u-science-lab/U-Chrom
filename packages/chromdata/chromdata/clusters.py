"""Multi-way contacts: clusters of genomic fragments (``ChromData.clusters``, format 2.4).

A *cluster* is a set of genomic fragments observed together — a SPRITE barcode cluster, a Pore-C read, a
ChIA-Drop GEM, a GAM nuclear profile: a hyperedge whose nodes are fragments (chrom, start, end).  Pairwise
contacts are one view of it; the clusters are what is stored.

A :class:`ClusterTable` keeps them in compressed sparse rows (CSR)::

    members         (3, n_members)  chrom code, start, end: every cluster's fragments end to end
    member_offsets  (n_clusters + 1) cluster k = members[:, member_offsets[k]:member_offsets[k + 1]]
    cell_offsets    (n_cells + 1)    cell i = clusters cell_offsets[i]:cell_offsets[i + 1] (per-cell data)

Clusters are sorted by (cell, first fragment), the fragments of a cluster by (chrom, start, end).  For region
queries every chromosome has a second copy, the *locus index*: one row per fragment on that chromosome, sorted
by start, carrying its cluster's context (cluster id, size, fragments on this chromosome, span on this
chromosome, cell).  The fragments of a window and everything needed to draw their clusters are therefore one
contiguous read; a small *fence* (the first start of every chunk) finds that range without reading the index.
The layout on disk is in ``packages/chromdata/spec.md`` (*Clusters*).
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

PathLike = Union[str, Path]

GROUP = "clusters"
CHUNK = 1 << 14    # columns per chunk of the cluster-order arrays (the unit of a range read)
LOCUS_CHUNK = 1 << 14   # columns per chunk of a locus index (a window reads whole chunks); its fence has one start
                        # per chunk, and readers take the value a table was written with (attrs ``locus_chunk``)
SHARD = 1 << 22    # columns per shard (one object on S3)
ZSTD_LEVEL = 9
MEMBER_ROWS = ("chrom", "start", "end")
#: rows of a chromosome's locus index; bulk tables (no cells) leave out "cell"
LOCUS_ROWS = ("start", "end", "cluster", "size", "chrom_size", "span_start", "span_end", "cell")
CLUSTER_TABLE = "clusters.parquet"


def _zarr():
    import zarr

    return zarr


def _uint_dtype(*arrays: np.ndarray) -> np.dtype:
    hi = max((int(a.max()) for a in arrays if a.size), default=0)
    return np.dtype(np.uint32) if hi < 2 ** 32 else np.dtype(np.uint64)


def _rows_array(group, name: str, data: np.ndarray, *, chunk: int = CHUNK, compressor=None) -> None:
    """A ``(rows, n)`` array chunked ``(rows, chunk)`` and sharded: a chunk holds every row of the same
    columns, each row contiguous (as the contact pixels of :mod:`chromdata.embedded`).  ``compressor``: a zarr
    codec (default zstd 9); readers take the codecs from the array's metadata."""
    zarr = _zarr()
    data = np.asarray(data)
    r, n = data.shape
    ch = max(1, min(int(chunk), n))
    sh = max(ch, min(SHARD - SHARD % ch, -(-n // ch) * ch))
    z = group.create_array(name, shape=(r, n), chunks=(r, ch), shards=(r, sh), dtype=data.dtype,
                           compressors=compressor if compressor is not None else zarr.codecs.ZstdCodec(level=ZSTD_LEVEL))
    if n:
        z[:] = data


def _vector(group, name: str, data: np.ndarray, *, small: bool = False) -> None:
    zarr = _zarr()
    data = np.ascontiguousarray(data)
    n = len(data)
    if small:
        z = group.create_array(name, shape=(n,), chunks=(max(1, min(n, 1 << 20)),), dtype=data.dtype,
                               compressors=zarr.codecs.ZstdCodec(level=ZSTD_LEVEL))
    else:
        ch = max(1, min(CHUNK, n))
        sh = max(ch, min(SHARD, -(-n // ch) * ch))
        z = group.create_array(name, shape=(n,), chunks=(ch,), shards=(sh,), dtype=data.dtype,
                               compressors=zarr.codecs.ZstdCodec(level=ZSTD_LEVEL))
    if n:
        z[:] = data


def _safe_nodes(names: Sequence[str]) -> Dict[str, str]:
    from .zarrcd import _safe_names

    return _safe_names([str(n) for n in names])


def _check_json(value: Any, what: str) -> None:
    try:
        json.dumps(value)
    except (TypeError, ValueError) as e:
        raise TypeError(f"{what} must be JSON-serialisable: {e}") from None


class ClusterTable:
    """Clusters of genomic fragments (multi-way contacts) in CSR form; see the module docstring.

    Build one with :meth:`from_frame` (one row per fragment); a table read from a store backed
    (``ChromData.read(..., backed=True)``) reads its arrays on access.  Tables are not edited in place:
    :meth:`select_cells` and :meth:`from_frame` make new ones.

    Attributes
    ----------
    chroms : list of str
        Chromosome names; ``members`` row 0 holds codes into it.
    cells : pandas.Index or None
        Cell ids (strings) of a per-cell table, in the order of ``cell_offsets``; ``None`` for bulk data.
    attrs : dict
        Free JSON metadata (assay, source, filters, …).
    """

    def __init__(self, members, member_offsets, chroms: Sequence[str], *, cell_offsets=None,
                 cells: Optional[Sequence] = None, member_columns: Optional[Mapping[str, Any]] = None,
                 cluster_columns: Optional[pd.DataFrame] = None, attrs: Optional[Mapping[str, Any]] = None,
                 validate: bool = True):
        self.chroms: List[str] = [str(c) for c in chroms]
        self._members = members
        self._member_offsets = member_offsets
        self._cell_offsets = None if cell_offsets is None else np.asarray(cell_offsets, dtype=np.int64)
        self.cells: Optional[pd.Index] = (None if cells is None else
                                          pd.Index([str(c) for c in cells], dtype=object, name="cell_id"))
        self.member_columns: Dict[str, Any] = dict(member_columns or {})
        self._cluster_columns = cluster_columns
        self.attrs: Dict[str, Any] = dict(attrs or {})
        self._group = None                     # backed: the zarr group
        self._meta: Dict[str, Any] = {}        # backed: attrs["uchrom_clusters"]
        self._cluster_reader: Optional[Callable[[], pd.DataFrame]] = None
        self._locus: Dict[int, Tuple[np.ndarray, int]] = {}
        self._fence: Dict[int, np.ndarray] = {}
        if (self._cell_offsets is None) != (self.cells is None):
            raise ValueError("cell_offsets and cells go together (per-cell data) or are both absent (bulk)")
        if validate:
            self._validate()

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------

    @classmethod
    def from_frame(cls, df: pd.DataFrame, *, cluster: str = "cluster", chrom: str = "chrom",
                   start: str = "start", end: str = "end", cell: Optional[str] = None,
                   chroms: Optional[Sequence[str]] = None, cells: Optional[Sequence] = None,
                   member_columns: Sequence[str] = (), keep_names: bool = True,
                   attrs: Optional[Mapping[str, Any]] = None) -> "ClusterTable":
        """A table from one row per fragment.

        Parameters
        ----------
        df : DataFrame
            Fragments: a cluster label, ``chrom``, ``start``, ``end`` (0-based, end-exclusive, ``end > start``)
            and, for per-cell data, a cell id.
        cluster, chrom, start, end, cell : str
            Column names.  ``cell=None``: bulk data (no cells).
        chroms : sequence of str, optional
            Chromosome order (e.g. the categories of ``cd.bins["chrom"]``); default the column's categories
            when it is categorical, else the sorted names.
        cells : sequence, optional
            Cell order (e.g. ``cd.cells.index``); cells without clusters are kept.  Default: the column's
            categories when it is categorical, else the sorted ids.
        member_columns : sequence of str
            Numeric per-fragment columns to keep (strand, mapping quality, DNA / RNA read, …).
        keep_names : bool
            Keep the cluster labels (barcodes, read ids) as the per-cluster column ``name``.  Clusters are
            renumbered: cluster ids are positions in the stored order (cell, first fragment).
        attrs : dict, optional
            JSON metadata.
        """
        from .bins import _chrom_categorical

        for c in [cluster, chrom, start, end] + ([cell] if cell else []) + list(member_columns):
            if c not in df.columns:
                raise KeyError(f"column {c!r} not in the frame")
        n = len(df)
        labels_col = df[cluster]
        if labels_col.isna().any():
            raise ValueError("cluster labels must not be missing")
        ccode, labels = pd.factorize(labels_col, sort=False)
        ccode = ccode.astype(np.int64)
        k = len(labels)
        if chroms is not None:
            missing = sorted(set(df[chrom].astype(str)) - {str(c) for c in chroms})
            if missing:
                raise ValueError(f"chromosomes not in chroms: {missing[:5]}")
        cat = _chrom_categorical(df[chrom], chroms)
        mchrom = np.asarray(cat.codes, dtype=np.int64)
        if (mchrom < 0).any():
            bad = sorted(set(df[chrom].astype(str)[mchrom < 0]))[:5]
            raise ValueError(f"chromosomes not in chroms: {bad}")
        chrom_names = [str(c) for c in cat.categories]
        mstart = np.asarray(df[start], dtype=np.int64)
        mend = np.asarray(df[end], dtype=np.int64)
        if n and mstart.min() < 0:
            raise ValueError("fragment starts must be >= 0")
        if (mend <= mstart).any():
            raise ValueError("fragments need end > start (0-based, end-exclusive)")
        mcell = None
        cell_index = None
        if cell is not None:
            cv = df[cell]
            if cv.isna().any():
                raise ValueError("cell ids must not be missing")
            if cells is not None:
                cell_index = pd.Index([str(c) for c in cells], dtype=object)
            elif isinstance(cv.dtype, pd.CategoricalDtype):
                cell_index = pd.Index([str(c) for c in cv.cat.categories], dtype=object)
            else:
                cell_index = pd.Index(sorted({str(c) for c in pd.unique(cv)}), dtype=object)
            if not cell_index.is_unique:
                raise ValueError("cell ids must be unique")
            mcell = cell_index.get_indexer(cv.astype(str)).astype(np.int64)
            if (mcell < 0).any():
                raise ValueError(f"cells not in cells=: {sorted(set(cv.astype(str)[mcell < 0]))[:5]}")
        # fragments grouped by cluster (first-appearance codes), sorted within
        order = np.lexsort((mend, mstart, mchrom, ccode))
        ccode_s, mchrom, mstart, mend = ccode[order], mchrom[order], mstart[order], mend[order]
        sizes = np.bincount(ccode_s, minlength=k).astype(np.int64)
        off0 = np.zeros(k + 1, dtype=np.int64)
        np.cumsum(sizes, out=off0[1:])
        first = off0[:-1]
        keys = [np.arange(k), sizes, mend[first], mstart[first], mchrom[first]] if k else [np.arange(0)]
        ccell = None
        if mcell is not None:
            mcell = mcell[order]
            if k:
                lo = np.minimum.reduceat(mcell, first)
                hi = np.maximum.reduceat(mcell, first)
                if (lo != hi).any():
                    bad = labels[np.flatnonzero(lo != hi)[:3]]
                    raise ValueError(f"a cluster belongs to one cell; clusters with several: {list(bad)}")
                ccell = lo
            else:
                ccell = np.zeros(0, dtype=np.int64)
            keys.append(ccell)
        perm = np.lexsort(keys) if k else np.zeros(0, dtype=np.int64)
        lens = sizes[perm]
        offsets = np.zeros(k + 1, dtype=np.int64)
        np.cumsum(lens, out=offsets[1:])
        idx = np.arange(n, dtype=np.int64) - np.repeat(offsets[:-1], lens) + np.repeat(off0[perm], lens)
        mdt = _uint_dtype(mchrom, mstart, mend)
        members = np.stack([mchrom[idx], mstart[idx], mend[idx]]).astype(mdt)
        mcols = {}
        for c in member_columns:
            v = np.asarray(df[c])
            if v.dtype.kind not in "biuf":
                raise TypeError(f"member column {c!r} must be numeric or boolean (dtype {v.dtype})")
            mcols[str(c)] = v[order][idx]
        cell_offsets = None
        if ccell is not None:
            counts = np.bincount(ccell[perm], minlength=len(cell_index)).astype(np.int64)
            cell_offsets = np.zeros(len(cell_index) + 1, dtype=np.int64)
            np.cumsum(counts, out=cell_offsets[1:])
        ctab = None
        if keep_names:
            names = np.asarray(labels)[perm]
            ctab = pd.DataFrame({"name": names if names.dtype.kind in "iu" else names.astype(str)})
        return cls(members, offsets, chrom_names, cell_offsets=cell_offsets, cells=cell_index,
                   member_columns=mcols, cluster_columns=ctab, attrs=attrs)

    # ------------------------------------------------------------------
    # shape
    # ------------------------------------------------------------------

    @property
    def backed(self) -> bool:
        return self._group is not None

    @property
    def kind(self) -> str:
        """``"per_cell"`` (clusters belong to cells / spots) or ``"bulk"``."""
        return "bulk" if self.cells is None else "per_cell"

    @property
    def n_clusters(self) -> int:
        return int(self._member_offsets.shape[0]) - 1

    @property
    def n_members(self) -> int:
        return int(self._members.shape[1])

    @property
    def n_cells(self) -> int:
        return 0 if self.cells is None else len(self.cells)

    @property
    def member_offsets(self) -> np.ndarray:
        return np.asarray(self._member_offsets[:], dtype=np.int64)

    @property
    def cell_offsets(self) -> Optional[np.ndarray]:
        return self._cell_offsets

    @property
    def members_array(self) -> np.ndarray:
        """The ``(3, n_members)`` member array (chrom code, start, end), loaded."""
        return np.asarray(self._members[:, :])

    @property
    def cluster_columns(self) -> Optional[pd.DataFrame]:
        """Per-cluster table (one row per cluster id, e.g. ``name``), or ``None``."""
        if self._cluster_columns is None and self._cluster_reader is not None:
            self._cluster_columns = self._cluster_reader().reset_index(drop=True)
        return self._cluster_columns

    def sizes(self) -> np.ndarray:
        """Fragments per cluster."""
        return np.diff(self.member_offsets)

    def cell_codes(self, clusters: Union[Sequence[int], np.ndarray]) -> np.ndarray:
        """Cell code (position in :attr:`cells`) of each cluster id."""
        if self._cell_offsets is None:
            raise ValueError("a bulk table has no cells")
        return np.searchsorted(self._cell_offsets, np.asarray(clusters, dtype=np.int64), side="right") - 1

    def __len__(self) -> int:
        return self.n_clusters

    def __repr__(self) -> str:
        cells = f", {self.n_cells:,} cells" if self.cells is not None else ""
        return (f"ClusterTable({self.kind}, {self.n_clusters:,} clusters, {self.n_members:,} fragments{cells}, "
                f"{len(self.chroms)} chromosomes{', backed' if self.backed else ''})")

    def _validate(self) -> None:
        off = self.member_offsets
        if off.ndim != 1 or len(off) < 1 or off[0] != 0 or off[-1] != self.n_members or (np.diff(off) < 0).any():
            raise ValueError("member_offsets must rise from 0 to n_members")
        if self._members.ndim != 2 or self._members.shape[0] != len(MEMBER_ROWS):
            raise ValueError("members must be a (3, n_members) array: chrom code, start, end")
        if self._cell_offsets is not None:
            co = self._cell_offsets
            if len(co) != len(self.cells) + 1 or co[0] != 0 or co[-1] != self.n_clusters or (np.diff(co) < 0).any():
                raise ValueError("cell_offsets must rise from 0 to n_clusters, one more than cells")
            if not self.cells.is_unique:
                raise ValueError("cell ids must be unique")
        if not self.backed and self.n_members:
            m = np.asarray(self._members)
            if int(m[0].max()) >= len(self.chroms):
                raise ValueError("chrom codes out of range")
            if (m[2] <= m[1]).any():
                raise ValueError("fragments need end > start")
        for k, v in self.member_columns.items():
            if len(v) != self.n_members:
                raise ValueError(f"member column {k!r} has {len(v)} values, not {self.n_members}")
        if self._cluster_columns is not None and len(self._cluster_columns) != self.n_clusters:
            raise ValueError("cluster_columns needs one row per cluster")
        _check_json(self.attrs, "ClusterTable.attrs")

    # ------------------------------------------------------------------
    # reading clusters
    # ------------------------------------------------------------------

    def _cluster_ranges(self, clusters: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        off = self._member_offsets
        if isinstance(off, np.ndarray):
            return off[clusters], off[clusters + 1]
        if not len(clusters):
            return np.zeros(0, np.int64), np.zeros(0, np.int64)
        lo, hi = int(clusters.min()), int(clusters.max()) + 2
        if hi - lo <= 4 * CHUNK or len(clusters) * CHUNK >= hi - lo:
            part = np.asarray(off[lo:hi], dtype=np.int64)
            return part[clusters - lo], part[clusters + 1 - lo]
        both = np.asarray(off.get_coordinate_selection(np.concatenate([clusters, clusters + 1])), dtype=np.int64)
        return both[:len(clusters)], both[len(clusters):]

    def _read_member_ranges(self, a: np.ndarray, b: np.ndarray) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        """Members (3, m) and member columns of the ranges a[k]:b[k] (ranges closer than a chunk are read
        as one)."""
        if not len(a):
            return np.zeros((3, 0), np.int64), {k: np.zeros(0, np.asarray(v[:0]).dtype)
                                                 for k, v in self.member_columns.items()}
        if isinstance(self._members, np.ndarray):
            idx = np.concatenate([np.arange(x, y) for x, y in zip(a, b)]) if len(a) else np.zeros(0, np.int64)
            return (self._members[:, idx].astype(np.int64),
                    {k: np.asarray(v)[idx] for k, v in self.member_columns.items()})
        order = np.argsort(a, kind="stable")
        sa, sb = a[order], b[order]
        blocks: List[Tuple[int, int, List[Tuple[int, int, int]]]] = []
        i = 0
        while i < len(sa):
            j, top = i, sb[i]
            while j + 1 < len(sa) and sa[j + 1] - top <= CHUNK:
                j += 1
                top = max(top, sb[j])
            blocks.append((int(sa[i]), int(top), [(int(order[t]), int(sa[t]), int(sb[t])) for t in range(i, j + 1)]))
            i = j + 1
        pieces: Dict[int, Tuple[np.ndarray, Dict[str, np.ndarray]]] = {}
        for lo, hi, items in blocks:
            mem = np.asarray(self._members[:, lo:hi], dtype=np.int64)
            cols = {k: np.asarray(v[lo:hi]) for k, v in self.member_columns.items()}
            for pos, x, y in items:
                pieces[pos] = (mem[:, x - lo:y - lo], {k: c[x - lo:y - lo] for k, c in cols.items()})
        mems = [pieces[p][0] for p in range(len(a))]
        cols = {k: np.concatenate([pieces[p][1][k] for p in range(len(a))]) for k in self.member_columns}
        return np.concatenate(mems, axis=1), cols

    def members(self, clusters: Union[int, Sequence[int], np.ndarray]) -> pd.DataFrame:
        """The fragments of the given cluster ids, one row each: ``cluster``, [``cell_id``], ``chrom``,
        ``start``, ``end`` + member columns (clusters in the order given)."""
        ids = np.atleast_1d(np.asarray(clusters, dtype=np.int64))
        if len(ids) and (ids.min() < 0 or ids.max() >= self.n_clusters):
            raise IndexError("cluster id out of range")
        a, b = self._cluster_ranges(ids)
        mem, cols = self._read_member_ranges(a, b)
        return self._frame(np.repeat(ids, b - a), mem, cols)

    def _frame(self, cl: np.ndarray, mem: np.ndarray, cols: Mapping[str, np.ndarray]) -> pd.DataFrame:
        out = {"cluster": cl.astype(np.int64)}
        if self.cells is not None:
            out["cell_id"] = pd.Categorical.from_codes(self.cell_codes(cl), categories=self.cells)
        out["chrom"] = pd.Categorical.from_codes(mem[0].astype(np.int64), categories=self.chroms)
        out["start"] = mem[1].astype(np.int64)
        out["end"] = mem[2].astype(np.int64)
        out.update({k: np.asarray(v) for k, v in cols.items()})
        return pd.DataFrame(out)

    def to_frame(self) -> pd.DataFrame:
        """Every fragment, one row each (see :meth:`members`); ``from_frame(t.to_frame(), cell="cell_id")``
        gives the same table back (with ``keep_names=False``)."""
        off = self.member_offsets
        cl = np.repeat(np.arange(self.n_clusters, dtype=np.int64), np.diff(off))
        return self._frame(cl, np.asarray(self._members[:, :], dtype=np.int64),
                           {k: np.asarray(v[:]) for k, v in self.member_columns.items()})

    def _cell_code(self, cell_id) -> int:
        if self.cells is None:
            raise ValueError("a bulk table has no cells")
        loc = self.cells.get_indexer([str(cell_id)])[0]
        if loc < 0:
            raise KeyError(f"no cell {cell_id!r}")
        return int(loc)

    def cell_clusters(self, cell_id) -> range:
        """Cluster ids of one cell (a contiguous range)."""
        i = self._cell_code(cell_id)
        return range(int(self._cell_offsets[i]), int(self._cell_offsets[i + 1]))

    def get_cell(self, cell_id) -> pd.DataFrame:
        """The fragments of one cell's clusters (one contiguous read)."""
        r = self.cell_clusters(cell_id)
        off = np.asarray(self._member_offsets[r.start:r.stop + 1], dtype=np.int64)
        if not len(r):
            return self._frame(np.zeros(0, np.int64), np.zeros((3, 0), np.int64),
                               {k: np.zeros(0, np.asarray(v[:0]).dtype) for k, v in self.member_columns.items()})
        mem = np.asarray(self._members[:, off[0]:off[-1]], dtype=np.int64)
        cols = {k: np.asarray(v[off[0]:off[-1]]) for k, v in self.member_columns.items()}
        cl = np.repeat(np.arange(r.start, r.stop, dtype=np.int64), np.diff(off))
        return self._frame(cl, mem, cols)

    def select_cells(self, cell_ids: Iterable) -> "ClusterTable":
        """A new (in-memory) table with the clusters of these cells, in the stored cell order."""
        codes = np.unique([self._cell_code(c) for c in cell_ids]).astype(np.int64)
        co = self._cell_offsets
        ids = (np.concatenate([np.arange(co[i], co[i + 1]) for i in codes]) if len(codes)
               else np.zeros(0, np.int64))
        a, b = self._cluster_ranges(ids)
        mem, cols = self._read_member_ranges(a, b)
        offsets = np.zeros(len(ids) + 1, dtype=np.int64)
        np.cumsum(b - a, out=offsets[1:])
        counts = co[codes + 1] - co[codes]
        cell_offsets = np.zeros(len(codes) + 1, dtype=np.int64)
        np.cumsum(counts, out=cell_offsets[1:])
        ctab = self.cluster_columns
        if ctab is not None:
            ctab = ctab.iloc[ids].reset_index(drop=True)
        return ClusterTable(mem.astype(self._members.dtype), offsets, self.chroms, cell_offsets=cell_offsets,
                            cells=self.cells[codes], member_columns=cols, cluster_columns=ctab,
                            attrs=self.attrs)

    def to_memory(self) -> "ClusterTable":
        """An in-memory copy (a table already in memory is returned as is)."""
        if not self.backed:
            return self
        return ClusterTable(np.asarray(self._members[:, :]), self.member_offsets, self.chroms,
                            cell_offsets=self._cell_offsets, cells=self.cells,
                            member_columns={k: np.asarray(v[:]) for k, v in self.member_columns.items()},
                            cluster_columns=self.cluster_columns, attrs=self.attrs, validate=False)

    def copy(self) -> "ClusterTable":
        if self.backed:
            return self
        ctab = self._cluster_columns.copy() if self._cluster_columns is not None else None
        return ClusterTable(np.array(self._members, copy=True), self.member_offsets.copy(), self.chroms,
                            cell_offsets=None if self._cell_offsets is None else self._cell_offsets.copy(),
                            cells=self.cells, member_columns={k: np.array(v, copy=True)
                                                              for k, v in self.member_columns.items()},
                            cluster_columns=ctab, attrs=json.loads(json.dumps(self.attrs)), validate=False)

    # ------------------------------------------------------------------
    # locus index and region queries
    # ------------------------------------------------------------------

    @property
    def locus_rows(self) -> Tuple[str, ...]:
        return LOCUS_ROWS if self.cells is not None else LOCUS_ROWS[:-1]

    def _chrom_code(self, chrom: str) -> int:
        try:
            return self.chroms.index(str(chrom))
        except ValueError:
            return -1

    def _build_locus(self, code: int) -> Tuple[np.ndarray, int]:
        """The locus index of a chromosome from the members: ``(rows, max fragment length)``."""
        m = self._members if isinstance(self._members, np.ndarray) else np.asarray(self._members[:, :])
        off = self.member_offsets
        sel = np.flatnonzero(m[0] == code)
        r = len(self.locus_rows)
        if not len(sel):
            return np.zeros((r, 0), dtype=np.uint32), 0
        cl = np.searchsorted(off, sel, side="right") - 1
        st = m[1, sel].astype(np.int64)
        en = m[2, sel].astype(np.int64)
        brk = np.r_[True, cl[1:] != cl[:-1]]
        rs = np.flatnonzero(brk)
        run = np.cumsum(brk) - 1
        span_start = st[rs][run]
        span_end = np.maximum.reduceat(en, rs)[run]
        chrom_size = np.diff(np.r_[rs, len(sel)])[run]
        size = (off[cl + 1] - off[cl])
        rows = [st, en, cl, size, chrom_size, span_start, span_end]
        if self.cells is not None:
            rows.append(self.cell_codes(cl))
        order = np.lexsort((cl, en, st))
        data = np.stack([x[order] for x in rows])
        return data.astype(_uint_dtype(data)), int((en - st).max())

    def _locus_rows(self, code: int, lo_value: int, hi_value: int) -> np.ndarray:
        """Rows of the locus index of chromosome ``code`` whose start is in ``(lo_value, hi_value)``."""
        if self.backed:
            info = self._meta["locus"].get(self.chroms[code])
            if info is None:
                return np.zeros((len(self.locus_rows), 0), np.int64)
            g = self._group[f"by_locus/{info['node']}"]
            if code not in self._fence:
                self._fence[code] = np.asarray(g["fence"][:], dtype=np.int64)
            fence = self._fence[code]
            lc = int(self._meta.get("locus_chunk", self._meta.get("chunk", CHUNK)))
            c0 = max(int(np.searchsorted(fence, lo_value, side="right")) - 1, 0)
            c1 = int(np.searchsorted(fence, hi_value, side="left"))
            n = int(info["n"])
            a, b = c0 * lc, min(c1 * lc, n)
            if b <= a:
                return np.zeros((len(self.locus_rows), 0), np.int64)
            block = np.asarray(g["rows"][:, a:b], dtype=np.int64)
        else:
            if code not in self._locus:
                self._locus[code] = self._build_locus(code)
            block = self._locus[code][0]
        s = block[0]
        i0 = _search(s, lo_value, "right")
        i1 = _search(s, hi_value, "left")
        return np.asarray(block[:, i0:i1], dtype=np.int64)

    def max_fragment_length(self, chrom: str) -> int:
        code = self._chrom_code(chrom)
        if code < 0:
            return 0
        if self.backed:
            return int((self._meta["locus"].get(self.chroms[code]) or {}).get("max_length", 0))
        if code not in self._locus:
            self._locus[code] = self._build_locus(code)
        return self._locus[code][1]

    def region(self, chrom: str, start: int, end: int, *, min_size: Optional[int] = None,
               max_size: Optional[int] = None, cells: Optional[Iterable] = None) -> pd.DataFrame:
        """The fragments overlapping ``chrom:start-end`` (0-based, end-exclusive) with their clusters' context,
        one row per fragment, sorted by start:

        ``cluster``, [``cell_id``], ``start``, ``end``, ``size`` (fragments of the cluster, all chromosomes),
        ``chrom_size`` (its fragments on this chromosome), ``span_start`` / ``span_end`` (its first and last
        fragment on this chromosome; a cluster with fragments elsewhere has ``size > chrom_size``).

        This is what a cluster track draws: group by ``cluster``, a line from ``span_start`` to ``span_end``
        (clipped to the window), a box per fragment.  ``min_size`` / ``max_size`` filter on ``size``,
        ``cells`` keeps the clusters of these cells.  A backed table reads the fence (once per chromosome)
        and one contiguous range of the chromosome's locus index.
        """
        code = self._chrom_code(chrom)
        cols = list(self.locus_rows)
        if code < 0 or end <= start:
            rows = np.zeros((len(cols), 0), np.int64)
        else:
            lmax = self.max_fragment_length(chrom)
            rows = self._locus_rows(code, int(start) - lmax, int(end))
            rows = rows[:, rows[1] > int(start)]
        keep = np.ones(rows.shape[1], dtype=bool)
        if min_size is not None:
            keep &= rows[3] >= int(min_size)
        if max_size is not None:
            keep &= rows[3] <= int(max_size)
        if cells is not None:
            want = np.asarray([self._cell_code(c) for c in cells], dtype=np.int64)
            keep &= np.isin(rows[cols.index("cell")], want)
        rows = rows[:, keep]
        out: Dict[str, Any] = {"cluster": rows[2]}
        if self.cells is not None:
            out["cell_id"] = pd.Categorical.from_codes(rows[cols.index("cell")], categories=self.cells)
        for i, name in enumerate(cols):
            if name not in ("cluster", "cell"):
                out[name] = rows[i]
        return pd.DataFrame(out)

    # ------------------------------------------------------------------
    # storage
    # ------------------------------------------------------------------

    def _write(self, parent, node: str, key: str, *, frame_writer: Optional[Callable[[pd.DataFrame, str], None]],
               locus_chunk: int = LOCUS_CHUNK, locus_compressor=None) -> None:
        """Write this table as the group ``parent/node`` (see spec.md, *Clusters*).  ``frame_writer(df, rel)``
        writes the per-cluster Parquet table at ``rel`` below the group; ``locus_chunk`` / ``locus_compressor``
        set the chunks and codec of the locus index."""
        t = self.to_memory()
        t._validate()
        g = parent.create_group(node)
        mem = np.asarray(t._members)
        mem = mem.astype(_uint_dtype(mem)) if mem.dtype.kind not in "u" else mem
        _rows_array(g, "members", mem)
        _vector(g, "member_offsets", t.member_offsets)
        if t.cells is not None:
            _vector(g, "cell_offsets", t._cell_offsets, small=True)
            g.create_array("cells", data=np.asarray(list(t.cells), dtype=str))
        mnodes = _safe_nodes(list(t.member_columns))
        if t.member_columns:
            mg = g.create_group("member_columns")
            for k, v in t.member_columns.items():
                _vector(mg, mnodes[k], np.asarray(v))
        locus: Dict[str, Any] = {}
        present = np.unique(mem[0]).astype(np.int64) if mem.shape[1] else np.zeros(0, np.int64)
        cnodes = _safe_nodes([t.chroms[c] for c in present])
        if len(present):
            lg = g.create_group("by_locus")
            for c in present:
                name = t.chroms[c]
                rows, lmax = t._build_locus(int(c))
                sub = lg.create_group(cnodes[name])
                _rows_array(sub, "rows", rows, chunk=locus_chunk, compressor=locus_compressor)
                _vector(sub, "fence", rows[0, ::int(locus_chunk)].astype(np.int64), small=True)
                locus[name] = {"node": cnodes[name], "n": int(rows.shape[1]), "max_length": int(lmax)}
        ctab = t.cluster_columns
        if ctab is not None and len(ctab.columns):
            if frame_writer is None:
                raise ValueError("no writer for the per-cluster table")
            frame_writer(ctab.reset_index(drop=True), CLUSTER_TABLE)
        g.attrs.update({"uchrom_clusters": {
            "key": str(key), "kind": t.kind, "chroms": t.chroms, "n_cells": t.n_cells,
            "n_clusters": t.n_clusters, "n_members": t.n_members, "member_rows": list(MEMBER_ROWS),
            "locus_rows": list(t.locus_rows), "chunk": CHUNK, "locus_chunk": int(locus_chunk), "locus": locus,
            "member_columns": {k: mnodes[k] for k in t.member_columns},
            "cluster_columns": CLUSTER_TABLE if ctab is not None and len(ctab.columns) else None,
            "attrs": t.attrs}})

    @classmethod
    def _open(cls, group, *, frame_reader: Optional[Callable[[str], pd.DataFrame]] = None) -> "ClusterTable":
        """A backed table over a zarr group written by :meth:`_write`."""
        meta = dict(group.attrs["uchrom_clusters"])
        cells = cell_offsets = None
        if meta["kind"] == "per_cell":
            cells = [str(c) for c in np.asarray(group["cells"][:])]
            cell_offsets = np.asarray(group["cell_offsets"][:], dtype=np.int64)
        mcols = {k: group[f"member_columns/{node}"] for k, node in (meta.get("member_columns") or {}).items()}
        t = cls(group["members"], group["member_offsets"], meta["chroms"], cell_offsets=cell_offsets, cells=cells,
                member_columns=mcols, attrs=meta.get("attrs") or {}, validate=False)
        t._group = group
        t._meta = meta
        if meta.get("cluster_columns") and frame_reader is not None:
            rel = meta["cluster_columns"]
            t._cluster_reader = lambda: frame_reader(rel)
        return t


def _search(s: np.ndarray, value: int, side: str) -> int:
    """``searchsorted`` of an integer in an unsigned array without converting the array (a value out of the
    dtype's range would make numpy cast the whole array on every query)."""
    if s.dtype.kind == "u":
        if value < 0:
            return 0
        if value > np.iinfo(s.dtype).max:
            return len(s)
        value = s.dtype.type(value)
    return int(np.searchsorted(s, value, side=side))


# ======================================================================
# store-level helpers
# ======================================================================

def write_clusters(root, root_path: Path, clusters: Mapping[str, ClusterTable], level: int = 3, **layout) -> None:
    """Write ``clusters`` into the store being written (``root``: its zarr group, ``root_path``: its
    directory) as ``clusters/<node>/``, with ``clusters`` attrs ``keys`` = {key: node}."""
    from .zarrcd import _write_frame

    if not clusters:
        return
    names = _safe_nodes(list(clusters))
    grp = root.create_group(GROUP)
    for key, table in clusters.items():
        if not isinstance(table, ClusterTable):
            raise TypeError(f"clusters[{key!r}] must be a ClusterTable, not {type(table).__name__}")
        if not str(key) or "/" in str(key):
            raise ValueError(f"clusters key must be non-empty without '/': {key!r}")
        node = names[str(key)]
        table._write(grp, node, str(key),
                     frame_writer=lambda df, rel, node=node: _write_frame(df, root_path / GROUP / node / rel, level),
                     **layout)
    grp.attrs.update({"keys": {str(k): names[str(k)] for k in clusters}})


def read_clusters(c) -> Dict[str, ClusterTable]:
    """Backed tables of every cluster group of a store (``c``: a :class:`chromdata.zarrcd.Container`); the
    arrays are read on access."""
    keys = c.group_attrs(GROUP).get("keys") or {}
    out = {}
    for key, node in keys.items():
        rel = f"{GROUP}/{node}"
        out[str(key)] = ClusterTable._open(c.root[rel], frame_reader=lambda r, rel=rel: c.read_frame(f"{rel}/{r}"))
    return out


def add_clusters(store_path: PathLike, key: str, table: ClusterTable, *, overwrite: bool = False,
                 locus_chunk: int = LOCUS_CHUNK, locus_compressor=None) -> None:
    """Add (or with ``overwrite=True`` replace) ``clusters[key]`` in an existing ``.chromdata.zarr`` directory
    without rewriting the rest — for tables built after the store, e.g. from a large cluster file.  The store
    is marked format 2.4 and its metadata re-consolidated.  ``locus_chunk`` (columns per chunk: a window reads
    whole chunks) and ``locus_compressor`` (a zarr codec) set the layout of the locus index; readers follow what
    was written."""
    import os
    import shutil
    import tempfile

    from .zarrcd import ZARR_FORMAT_VERSION, _consolidate_root, _write_frame, container_kind

    path = Path(store_path)
    if container_kind(path) != "zarr" or not path.is_dir():
        raise ValueError(f"{path}: add_clusters needs a .chromdata.zarr directory (a .cdz is rewritten whole)")
    if not str(key) or "/" in str(key):
        raise ValueError(f"clusters key must be non-empty without '/': {key!r}")
    zarr = _zarr()
    root = zarr.open_group(str(path), mode="r+", zarr_format=3, use_consolidated=False)
    if "uchrom" not in root.attrs:
        raise ValueError(f"{path}: not a ChromData store")
    grp = root.require_group(GROUP)
    keys = dict(grp.attrs.get("keys") or {})
    if str(key) in keys and not overwrite:
        raise FileExistsError(f"clusters[{key!r}] exists in {path} (overwrite=True replaces it)")
    node = keys.get(str(key)) or _safe_nodes(list(keys) + [str(key)])[str(key)]
    final = path / GROUP / node
    tmp = Path(tempfile.mkdtemp(prefix=f".{node}.partial-", dir=path / GROUP))
    try:
        tgrp = zarr.open_group(str(tmp), mode="w", zarr_format=3)
        table._write(tgrp, "t", str(key), frame_writer=lambda df, rel: _write_frame(df, tmp / "t" / rel, 3),
                     locus_chunk=locus_chunk, locus_compressor=locus_compressor)
        if final.exists():
            shutil.rmtree(final)
        os.replace(tmp / "t", final)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    keys[str(key)] = node
    grp.attrs.update({"keys": keys})
    meta = dict(root.attrs["uchrom"])
    from .cdata import _parse_version

    if _parse_version(str(meta.get("format_version", "2.0"))) < _parse_version(ZARR_FORMAT_VERSION):
        meta["format_version"] = ZARR_FORMAT_VERSION
        root.attrs.update({"uchrom": meta, "uchrom_format_version": ZARR_FORMAT_VERSION})
    _consolidate_root(path)


__all__ = ["ClusterTable", "add_clusters", "read_clusters", "write_clusters", "CHUNK", "LOCUS_CHUNK", "LOCUS_ROWS",
           "MEMBER_ROWS"]
