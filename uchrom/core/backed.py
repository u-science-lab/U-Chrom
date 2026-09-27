"""Backed (out-of-core) ``ChromData`` over a ``.chromdata.zarr`` / ``.cdz`` store.

``ChromData.read(path, backed=True)`` returns a :class:`BackedChromData`:

* **eager** (read on open): ``bins``, ``bin_tracks``, ``binm``, ``cells``,
  ``cellm``, ``traces``, ``intervals``, ``points``, ``results``, ``uns`` and
  the ``index/`` offsets — all small;
* **lazy**: ``coords``, ``layers``, ``spots``, ``spot_tracks`` are proxies
  that read Parquet row groups on access.

Subsetting — ``get_cell`` / ``get_trace`` / ``get_chrom`` / ``cd[rows]`` /
``iter_traces`` / ``iter_cells`` — reads only the row ranges it needs (the
spots are sorted by cell, trace, bin; ``index/`` holds the offsets) and
returns an ordinary in-memory :class:`~uchrom.core.ChromData`.
:meth:`BackedChromData.to_memory` loads everything.

The backed object is read-only for the spot-aligned data (``coords``,
``spots``, ``spot_tracks``, ``layers``); the small tables are ordinary
in-memory objects that can be changed, and :meth:`write` (which loads the
data first) saves them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .bins import BIN_ID, LOCI, loci_of
from .cdata import ChromData, _empty_frame, resolve_batch, resolve_selection
from .intervals import IntervalStore
from . import _parallel as _par
from .zarrcd import Container, SpotRows, read_small_parts

_READ_ONLY = ("backed ChromData is read-only for spot-aligned data (coords, spots, "
              "spot_tracks, layers); call cd.to_memory() for an editable copy")


class BackedArray:
    """``(n_spots, 3)`` coordinates read from Parquet on access.

    Supports ``len``, ``shape`` / ``ndim`` / ``dtype``, row indexing (slices,
    integer or boolean arrays, optionally followed by a column index) and
    ``np.asarray`` (a full read).  Values are float64, like in-memory coords.
    """

    ndim = 2
    dtype = np.dtype(np.float64)

    def __init__(self, rows: SpotRows, name: str):
        self._rows = rows
        self._name = name

    @property
    def shape(self) -> Tuple[int, int]:
        return (self._rows.n, 3)

    @property
    def size(self) -> int:
        return self._rows.n * 3

    def __len__(self) -> int:
        return self._rows.n

    def _cols(self):
        return ("x", "y", "z")

    def _read_rows(self, key) -> np.ndarray:
        n = self._rows.n
        if isinstance(key, slice):
            start, stop, step = key.indices(n)
            if step == 1:
                t = self._rows.read_ranges(self._name, [(start, stop)], self._cols())
                return self._rows.coords_of(t)
            key = np.arange(start, stop, step)
        if isinstance(key, (int, np.integer)):
            k = int(key)
            if k < 0:
                k += n
            if not 0 <= k < n:
                raise IndexError(f"index {key} out of range for {n} spots")
            return self._read_rows(np.array([k]))[0]
        idx = np.asarray(key)
        if idx.dtype == bool:
            if len(idx) != n:
                raise IndexError(f"boolean index of length {len(idx)} for {n} spots")
            idx = np.flatnonzero(idx)
        idx = idx.astype(np.int64)
        idx = np.where(idx < 0, idx + n, idx)
        t = self._rows.take(self._name, idx, self._cols())
        return self._rows.coords_of(t)

    def __getitem__(self, key):
        if isinstance(key, tuple):
            out = self._read_rows(key[0])
            rest = key[1:]
            return out[rest] if out.ndim == 1 else out[(slice(None),) + rest]
        return self._read_rows(key)

    def __array__(self, dtype=None, copy=None):
        out = self._read_rows(slice(None))
        return out if dtype is None else out.astype(dtype, copy=False)

    def to_numpy(self) -> np.ndarray:
        return self.__array__()

    def __repr__(self) -> str:
        return f"<BackedArray {self._name} shape={self.shape}>"


class _ILoc:
    def __init__(self, frame: "BackedFrame"):
        self._frame = frame

    def __getitem__(self, key):
        if isinstance(key, tuple):
            rows, cols = key[0], key[1]
            return self[rows].iloc[:, cols]
        n = len(self._frame)
        if isinstance(key, (int, np.integer)):
            return self._frame._rows_frame(np.array([int(key) % n])).iloc[0]
        if isinstance(key, slice):
            start, stop, step = key.indices(n)
            if step == 1:
                return self._frame._range_frame(start, stop)
            key = np.arange(start, stop, step)
        idx = np.asarray(key)
        if idx.dtype == bool:
            idx = np.flatnonzero(idx)
        return self._frame._rows_frame(idx.astype(np.int64))


class BackedFrame:
    """A spot-aligned table (``spots`` or ``spot_tracks``) read on access.

    ``frame[col]`` reads one column (a ``pandas.Series``); ``frame[[cols]]``
    several; ``frame.iloc[rows]`` rows (a ``DataFrame``); ``to_pandas()``
    everything.  ``spots`` also serves the derived ``chrom`` / ``start`` /
    ``end`` columns (from ``bins`` via ``bin_id``).
    """

    def __init__(self, owner: "BackedChromData", name: str, columns: List[str]):
        self._owner = owner
        self._name = name
        self._columns = list(columns)

    @property
    def _rows(self) -> SpotRows:
        return self._owner._rows

    @property
    def columns(self) -> pd.Index:
        return pd.Index(self._columns)

    @property
    def shape(self) -> Tuple[int, int]:
        return (self._rows.n, len(self._columns))

    @property
    def index(self) -> pd.RangeIndex:
        return pd.RangeIndex(self._rows.n)

    @property
    def dtypes(self) -> pd.Series:
        """Column dtypes, from the Parquet schema (no data is read)."""
        empty = self._rows.empty(self._name)
        stored = self._rows.to_frame(self._name, empty).dtypes.to_dict()
        if self._name == "spots":
            stored.update({"chrom": self._owner._bins["chrom"].dtype,
                           "start": np.dtype(np.int64), "end": np.dtype(np.int64),
                           BIN_ID: np.dtype(np.int64)})
        return pd.Series({c: stored[c] for c in self._columns}, dtype=object)

    @property
    def empty(self) -> bool:
        return self._rows.n == 0 or not self._columns

    def __len__(self) -> int:
        return self._rows.n

    def __iter__(self):
        return iter(self._columns)

    def __contains__(self, col) -> bool:
        return col in self._columns

    @property
    def iloc(self) -> _ILoc:
        return _ILoc(self)

    def _stored(self, cols: Sequence[str]) -> List[str]:
        stored = [c for c in cols if c not in LOCI or self._name != "spots"]
        if self._name == "spots" and any(c in LOCI for c in cols) and BIN_ID not in stored:
            stored.append(BIN_ID)
        return stored

    def _finish(self, table, cols: Sequence[str]) -> pd.DataFrame:
        df = self._rows.to_frame(self._name, table)
        if self._name == "spots" and any(c in LOCI for c in cols):
            loci = loci_of(self._owner._bins, df[BIN_ID].to_numpy().astype(np.int64))
            for c in LOCI:
                if c in cols:
                    df[c] = loci[c]
        if BIN_ID in df.columns:
            df[BIN_ID] = df[BIN_ID].to_numpy().astype(np.int64)
        return df[list(cols)]

    def _range_frame(self, start: int, stop: int, cols: Optional[Sequence[str]] = None) -> pd.DataFrame:
        cols = list(cols) if cols is not None else self._columns
        t = self._rows.read_ranges(self._name, [(start, stop)], self._stored(cols))
        return self._finish(t, cols)

    def _rows_frame(self, idx: np.ndarray, cols: Optional[Sequence[str]] = None) -> pd.DataFrame:
        cols = list(cols) if cols is not None else self._columns
        t = self._rows.take(self._name, idx, self._stored(cols))
        return self._finish(t, cols)

    def __getitem__(self, key):
        if isinstance(key, str):
            if key not in self._columns:
                raise KeyError(key)
            return self._range_frame(0, self._rows.n, [key])[key]
        if isinstance(key, (list, tuple, pd.Index)):
            missing = [k for k in key if k not in self._columns]
            if missing:
                raise KeyError(missing)
            return self._range_frame(0, self._rows.n, list(key))
        return self.iloc[key]

    def head(self, n: int = 5) -> pd.DataFrame:
        return self._range_frame(0, min(n, self._rows.n))

    def to_pandas(self) -> pd.DataFrame:
        return self._range_frame(0, self._rows.n)

    def __repr__(self) -> str:
        return (f"<BackedFrame {self._name}: {self._rows.n} rows x {len(self._columns)} "
                f"columns {self._columns[:8]}{'…' if len(self._columns) > 8 else ''}>")


def _range_arrays(ranges) -> Tuple[np.ndarray, np.ndarray]:
    """``[(start, stop), …]`` → (starts, stops) int64 arrays."""
    if isinstance(ranges, tuple) and len(ranges) == 2 and isinstance(ranges[0], np.ndarray):
        return ranges
    if not len(ranges):
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
    a = np.asarray(ranges, dtype=np.int64).reshape(-1, 2)
    return a[:, 0].copy(), a[:, 1].copy()


def _coalesce(starts: np.ndarray, stops: np.ndarray) -> List[Tuple[int, int]]:
    """Ascending, disjoint ranges merged where they touch."""
    keep = stops > starts
    starts, stops = starts[keep], stops[keep]
    if not len(starts):
        return []
    brk = np.r_[True, starts[1:] != stops[:-1]]
    a = starts[brk]
    b = stops[np.r_[brk[1:], True]]
    return list(zip(a.tolist(), b.tolist()))


def _read_ordered(rows: SpotRows, name: str, starts: np.ndarray, stops: np.ndarray,
                  columns: Optional[Sequence[str]]):
    """Rows of the ranges ``starts[i]:stops[i]`` of one table, **in the
    given range order** (ranges are disjoint but may be in any order): read
    ascending, then reordered with one take."""
    import pyarrow as pa

    lens = stops - starts
    keep = lens > 0
    if not keep.all():
        starts, stops, lens = starts[keep], stops[keep], lens[keep]
    if not len(starts):
        return rows.empty(name, columns if columns is not None else rows.columns(name))
    if len(starts) == 1 or np.all(starts[1:] >= stops[:-1]):
        return rows.read_ranges(name, _coalesce(starts, stops), columns)
    o = np.argsort(starts, kind="stable")
    t = rows.read_ranges(name, _coalesce(starts[o], stops[o]), columns)
    pos_sorted = np.empty(len(o), dtype=np.int64)
    pos_sorted[o] = np.r_[0, np.cumsum(lens[o])[:-1]]
    out_pos = np.r_[0, np.cumsum(lens)[:-1]]
    idx = np.repeat(pos_sorted - out_pos, lens) + np.arange(int(lens.sum()), dtype=np.int64)
    return t.take(pa.array(idx))


def _map_ranges(starts: np.ndarray, stops: np.ndarray, off: np.ndarray, other_off: np.ndarray,
                run_map: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Row ranges of one side of a format 2.2 store → the matching row
    ranges of the other side, in the same order: runs ``k`` of ``off``
    (offsets) are runs ``run_map[k]`` of ``other_off``, with the same
    rows in the same order."""
    if not len(starts):
        return starts, stops
    k0 = np.searchsorted(off, starts, side="right") - 1
    k1 = np.searchsorted(off, stops, side="left")
    cnt = np.maximum(k1 - k0, 0)
    tot = int(cnt.sum())
    first = np.repeat(k0 - np.r_[0, np.cumsum(cnt)[:-1]], cnt)
    ks = first + np.arange(tot, dtype=np.int64)
    a = np.maximum(np.repeat(starts, cnt), off[ks])
    b = np.minimum(np.repeat(stops, cnt), off[ks + 1])
    base = other_off[run_map[ks]]
    return base + (a - off[ks]), base + (b - off[ks])


class _Coords22(BackedArray):
    """Coordinates of a format 2.2 store: rows are primary rows; values are
    read from the chromosome-partitioned coordinate table."""

    def __init__(self, owner: "BackedChromData"):
        super().__init__(owner._rows, "spots")
        self._owner = owner

    def _read_rows(self, key) -> np.ndarray:
        o = self._owner
        n = o.n_spots
        if isinstance(key, slice):
            start, stop, step = key.indices(n)
            if step == 1:
                if start == 0 and stop == n:
                    return o._full_coords()
                cs, ce = o._p2c(np.array([start]), np.array([max(start, stop)]))
                return o._crows.coords_of(_read_ordered(o._crows, "coords", cs, ce, list(_XYZ)))
            key = np.arange(start, stop, step)
        if isinstance(key, (int, np.integer)):
            k = int(key)
            if k < 0:
                k += n
            if not 0 <= k < n:
                raise IndexError(f"index {key} out of range for {n} spots")
            return self._read_rows(np.array([k]))[0]
        idx = np.asarray(key)
        if idx.dtype == bool:
            if len(idx) != n:
                raise IndexError(f"boolean index of length {len(idx)} for {n} spots")
            idx = np.flatnonzero(idx)
        idx = idx.astype(np.int64)
        idx = np.where(idx < 0, idx + n, idx)
        return o._crows.coords_of(o._crows.take("coords", o._p2c_rows(idx), list(_XYZ)))


class _SpotsFrame22(BackedFrame):
    """``spots`` of a format 2.2 store (keys from the coordinate table,
    other columns from the primary, derived columns from their keys)."""

    @property
    def dtypes(self) -> pd.Series:
        return self._range_frame(0, 0).dtypes

    def _range_frame(self, start: int, stop: int, cols: Optional[Sequence[str]] = None) -> pd.DataFrame:
        cols = list(cols) if cols is not None else self._columns
        o = self._owner
        if all(c == BIN_ID or c in LOCI for c in cols):
            # bin_id (and the loci): the coordinate table's key column only
            n = o.n_spots
            stop = max(start, stop)
            if start == 0 and stop == n:
                bid = o._full_coords(with_bins=True, with_xyz=False)[1]
            else:
                cs, ce = o._p2c(np.array([start]), np.array([stop]))
                bid = _read_ordered(o._crows, "coords", cs, ce, [BIN_ID]).column(BIN_ID).to_numpy()
            bid = np.asarray(bid, dtype=np.int64)
            df = pd.DataFrame({BIN_ID: bid})
            if any(c in LOCI for c in cols):
                loci = loci_of(o._bins, bid)
                for c in LOCI:
                    if c in cols:
                        df[c] = loci[c]
            return df[cols]
        sub = self._owner._build22(prim=[(int(start), int(max(start, stop)))], subset=False,
                                   columns=[c for c in cols if c not in LOCI], tracks=False)
        return sub.spots[cols]

    def _rows_frame(self, idx: np.ndarray, cols: Optional[Sequence[str]] = None) -> pd.DataFrame:
        cols = list(cols) if cols is not None else self._columns
        sub = self._owner._build22(rows=np.asarray(idx, dtype=np.int64), subset=False,
                                   columns=[c for c in cols if c not in LOCI], tracks=False)
        return sub.spots[cols]


_XYZ = ("x", "y", "z")


def _string_take(d, codes):
    """A derived pandas-string column: an Arrow gather of the per-key values."""
    import pyarrow as pa

    dt = d["dtype"]
    taken = d["arrow"].take(pa.array(np.asarray(codes, dtype=np.int64)))
    if dt.storage in ("pyarrow", "pyarrow_numpy"):
        return dt.__from_arrow__(taken)
    return pd.array(taken.to_numpy(zero_copy_only=False), dtype=dt)


def _par_serial() -> bool:
    import os
    return os.environ.get("UCHROM_ZARR_SERIAL_READ", "") == "1"


def _from_codes(codes, categories, ordered):
    try:
        return pd.Categorical.from_codes(codes, categories=categories, ordered=ordered, validate=False)
    except TypeError:  # pragma: no cover - pandas < 2.1
        return pd.Categorical.from_codes(codes, categories=categories, ordered=ordered)



class BackedChromData(ChromData):
    """A :class:`ChromData` whose spot-aligned data stays on disk.

    Created by ``ChromData.read(path, backed=True)`` on a
    ``.chromdata.zarr`` directory or ``.cdz`` file.  See the module
    docstring for what is eager and what is lazy.

    ``columns`` / ``tracks`` (see :meth:`ChromData.get_cell`) set the
    default column selection of ``get_*``, ``iter_*``, ``cd[rows]`` and
    :meth:`to_memory`; every one of those also takes them per call.
    """

    def __init__(self, path, *, columns=None, tracks=None, cache_bytes: Optional[int] = None,
                 _container: Optional[Container] = None):  # noqa: D401
        c = _container or Container(path)
        parts = read_small_parts(c)
        self._c = c
        self._parts = parts
        cache = {} if cache_bytes is None else {"cache_bytes": cache_bytes}
        self._rows = SpotRows(c, parts, **cache)
        self._index = parts["index"]
        # format 2.2: coordinates + keys in their own chromosome-partitioned
        # table (``_crows``); ``_rows`` are the cell-sorted primary tables
        self._v22 = parts.get("coords") is not None
        if self._v22:
            self._crows = SpotRows(c, parts, coords=True, **cache)
            self._cidx = parts["coords"]["index"]
            self._poff = np.asarray(self._index["trace_offsets"], dtype=np.int64)
            self._coff = np.asarray(self._cidx["trace_offsets"], dtype=np.int64)
            self._prun = np.asarray(self._cidx["primary_run"], dtype=np.int64)
            self._crun = np.empty_like(self._prun)
            self._crun[self._prun] = np.arange(len(self._prun), dtype=np.int64)
            self._derived = parts.get("derived") or {}
        self._backing_path = Path(path)
        self._source_path = Path(path)
        self._bins = parts["bins"]
        self.cells = parts["cells"] if parts["cells"] is not None else pd.DataFrame()
        self.cellm = parts["cellm"]
        self.traces = parts["traces"] if parts["traces"] is not None else pd.DataFrame()
        self.binm = parts["binm"]
        self._intervals = IntervalStore.coerce(parts["intervals"])
        self.results = parts["results"]
        self.uns = parts["uns"]
        self.points = parts["points"]
        self.cell_shapes = parts.get("cell_shapes") or {}
        self._linked_adata = None
        bt = parts["bin_tracks"]
        if bt is not None and len(bt.columns):
            bt.index = pd.RangeIndex(len(bt), name=BIN_ID)
            self._bin_tracks = bt
        else:
            self._bin_tracks = _empty_frame(len(self._bins), name=BIN_ID)
        tmeta = parts["tables_meta"]
        self._spot_view_order = (tmeta.get("spot_tracks", {}) or {}).get("spot_view_order") or None
        spot_meta = tmeta.get("spots", {})
        if self._v22:
            self._primary_spot_cols = list(spot_meta.get("columns") or [])
            keys = [c for c in tmeta["coords"]["columns"] if c not in spot_meta.get("coords", ())]
            stored = keys + self._primary_spot_cols + [c for c in self._derived]
        else:
            stored = [c for c in self._rows.columns("spots") if c not in spot_meta.get("coords", ())]
        order = [c for c in spot_meta.get("column_order", []) if c in stored or c in LOCI]
        cols = order + [c for c in stored if c not in order]
        for c in LOCI:
            if c not in cols:
                cols.insert(LOCI.index(c), c)
        if self._v22:
            self._spots_proxy = _SpotsFrame22(self, "spots", cols)
            self._coords_proxy = _Coords22(self)
        else:
            self._spots_proxy = BackedFrame(self, "spots", cols)
            self._coords_proxy = BackedArray(self._rows, "spots")
        if "spot_tracks" in self._rows.files:
            self._spot_tracks_proxy = BackedFrame(self, "spot_tracks", self._rows.columns("spot_tracks"))
        else:
            self._spot_tracks_proxy = None
        self.layers = {k: BackedArray(self._rows, f"layers/{k}")
                       for k in tmeta.get("layers", {})}
        self._default_selection = (columns, tracks)
        if columns is not None or tracks is not None:
            self._selection(columns, tracks)  # validate early

    # ------------------------------------------------------------------
    # Lazy attributes
    # ------------------------------------------------------------------

    @property
    def backed(self) -> bool:
        return True

    @property
    def format_version(self) -> str:
        return str(self._c.meta.get("format_version", "2.0"))

    @property
    def partitioned(self) -> bool:
        """``True`` for a format 2.1 store (spots partitioned by chromosome)."""
        return bool(self._parts.get("partitioned"))

    @property
    def has_coords_table(self) -> bool:
        """``True`` for a format 2.2 store: coordinates + keys partitioned by
        chromosome, the other spot-aligned columns in cell-sorted primary
        tables."""
        return self._v22

    @property
    def coords(self):  # type: ignore[override]
        return self._coords_proxy

    @coords.setter
    def coords(self, value) -> None:
        raise AttributeError(_READ_ONLY)

    @property
    def spots(self):  # type: ignore[override]
        return self._spots_proxy

    @spots.setter
    def spots(self, value) -> None:
        raise AttributeError(_READ_ONLY)

    @property
    def _spot_tracks(self):
        if self._spot_tracks_proxy is None:
            return _empty_frame(self.n_spots)
        return self._spot_tracks_proxy

    @_spot_tracks.setter
    def _spot_tracks(self, value) -> None:
        raise AttributeError(_READ_ONLY)

    @ChromData.spot_tracks.setter
    def spot_tracks(self, value) -> None:
        raise AttributeError(_READ_ONLY)

    @property
    def n_spots(self) -> int:
        return self._rows.n

    @property
    def n_traces(self) -> int:
        codes = np.asarray(self._index["trace_codes"])
        return int(len(np.unique(codes[codes >= 0])))

    @property
    def n_cells(self) -> int:
        if self._parts["spot_meta"].get("categorical", {}).get("cell_id") is not None and self.n_spots:
            codes = np.asarray(self._index["cell_codes"])
            return int(len(np.unique(codes[codes >= 0])))
        return len(self.cells) if len(self.cells) > 0 else 0

    def _has_cell_id(self) -> bool:
        return "cell_id" in self._spots_proxy.columns

    def _categories(self, col: str) -> Optional[pd.Index]:
        entry = self._rows.cats["spots"].get(col)
        return None if entry is None else entry[0]

    def _spot_cell_ids(self) -> pd.Index:
        if not self._has_cell_id():
            return pd.Index([], name="cell_id")
        cats = self._categories("cell_id")
        codes = np.unique(np.asarray(self._index["cell_codes"]))
        codes = codes[codes >= 0]
        return pd.Index([str(x) for x in np.asarray(cats)[codes]], name="cell_id")

    # ------------------------------------------------------------------
    # Column selection
    # ------------------------------------------------------------------

    def _selection(self, columns=None, tracks=None):
        """``(spot columns to read, spot tracks, layer keys)`` of a selection
        (``None`` / ``None`` → the default given to :meth:`ChromData.read`)."""
        if columns is None and tracks is None:
            columns, tracks = self._default_selection
        st_cols = list(self._spot_tracks_proxy.columns) if self._spot_tracks_proxy is not None else []
        spot_cols, track_cols, layer_keys = resolve_selection(
            list(self._spots_proxy.columns), st_cols, list(self.layers), columns, tracks)
        return spot_cols, track_cols, layer_keys

    # ------------------------------------------------------------------
    # Row access → in-memory ChromData
    # ------------------------------------------------------------------

    def _coords_only(self, columns=None, tracks=None) -> bool:
        """Whether a selection is served by the coordinate projection
        (coordinates + key columns, no spot tracks, extra columns or layers)."""
        spot_cols, track_cols, layer_keys = self._selection(columns, tracks)
        keys = {BIN_ID, "trace_id", "cell_id", *LOCI}
        return not track_cols and not layer_keys and all(c in keys for c in spot_cols)

    def _build(self, *, ranges: Optional[Sequence[Tuple[int, int]]] = None,
               rows: Optional[np.ndarray] = None, subset: bool = True,
               columns=None, tracks=None) -> ChromData:
        """In-memory ChromData of row ``ranges`` / ``rows`` (``None``: all)."""
        if self._v22:
            return self._build22(prim=ranges, rows=rows, full=rows is None and ranges is None,
                                 subset=subset, columns=columns, tracks=tracks)
        r = self._rows
        spot_name = "spots"
        spot_cols, track_cols, layer_keys = self._selection(columns, tracks)

        def read(name, cols=None):
            if rows is not None:
                return r.take(name, rows, cols)
            if ranges is None:
                return r.read_all(name, cols)
            return r.read_ranges(name, ranges, cols)

        coord_cols = list(self._parts["spot_meta"].get("coords", ("x", "y", "z")))
        stored = [c for c in spot_cols if c not in LOCI]
        full = rows is None and ranges is None
        want_st = "spot_tracks" in r.files and bool(track_cols)
        st_cols = None
        if want_st:
            all_st = list(self._spot_tracks_proxy.columns)
            st_cols = None if track_cols == all_st else track_cols
        if full:
            # full read: coordinates decoded straight into the (n, 3) array
            coords = np.empty((r.n, 3), dtype=np.float64)
            t = r.read_all(spot_name, stored + coord_cols,
                           dest={c: coords[:, j] for j, c in enumerate(coord_cols)})
        else:
            t = read(spot_name, stored + coord_cols)
            coords = r.coords_of(t, coord_cols)
            t = t.drop_columns(coord_cols)
        st_finish = None
        if want_st and full:
            # the spot tracks are read now; their float decoding runs in
            # threads (numpy, no GIL) while the spots are converted below
            # (string columns hold the GIL)
            st_finish = r.read_all("spot_tracks", st_cols, deferred=True)
        spots = r.to_frame(spot_name, t)
        del t
        spot_tracks = None
        if st_finish is not None:
            spot_tracks = r.to_frame("spot_tracks", st_finish())
        elif want_st:
            spot_tracks = r.to_frame("spot_tracks", read("spot_tracks", st_cols))
        def layer(k):
            if rows is None and ranges is None:
                a = np.empty((r.n, 3), dtype=np.float64)
                r.read_all(f"layers/{k}", ["x", "y", "z"], dest={c: a[:, j] for j, c in enumerate("xyz")})
                return a
            return r.coords_of(read(f"layers/{k}"))

        layers = {k: layer(k) for k in layer_keys}
        return self._finish_build(coords, spots, spot_tracks, layers, spot_cols, subset)

    def _finish_build(self, coords, spots, spot_tracks, layers, spot_cols, subset) -> ChromData:
        if subset:
            traces = self._filter_traces(spots)
            cells, cellm = self._filter_cells(spots)
            points = self._filter_points(spots)
            shapes = self._filter_cell_shapes(spots)
        else:
            traces, cells, cellm, points = self.traces, self.cells, self.cellm, self.points
            shapes = self.cell_shapes
        out = ChromData(
            coords, spots, bins=self._bins,
            cells=cells if len(cells) or len(cells.columns) else None,
            cellm=cellm or None, binm=self.binm or None, intervals=self._intervals,
            traces=traces if len(traces) or len(traces.columns) else None,
            layers=layers or None, results=self.results, uns=self.uns,
            points=points or None, cell_shapes=shapes or None, validate=False, _own_spots=True,
        )
        out._bin_tracks = self._bin_tracks
        if spot_tracks is not None:
            out._spot_tracks = spot_tracks
        view = [c for c in (self._spot_view_order or []) if c in out._bin_tracks.columns
                or (spot_tracks is not None and c in spot_tracks.columns)]
        out._spot_view_order = view or None
        order = [c for c in self._spots_proxy.columns if c in spot_cols]
        want = [c for c in order if c in out.spots.columns] + [c for c in out.spots.columns if c not in order]
        if want != list(out.spots.columns):
            out.spots = out.spots[want]
        return out

    # ------------------------------------------------------------------
    # Format 2.2: primary tables + chromosome-partitioned coordinates
    # ------------------------------------------------------------------

    def _p2c(self, starts: np.ndarray, stops: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Coordinate-table row ranges of primary row ranges (same order)."""
        return _map_ranges(starts, stops, self._poff, self._coff, self._crun)

    def _c2p(self, starts: np.ndarray, stops: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Primary row ranges of coordinate-table row ranges (same order)."""
        return _map_ranges(starts, stops, self._coff, self._poff, self._prun)

    def _p2c_rows(self, rows: np.ndarray) -> np.ndarray:
        """Coordinate-table row of every primary row."""
        k = np.searchsorted(self._poff, rows, side="right") - 1
        return self._coff[self._crun[k]] + (rows - self._poff[k])

    def _coords_scatter(self):
        """``(a, b)`` → the primary rows of coordinate-table rows ``a:b`` (a
        full read scatters the coordinate partitions into primary order with
        it, block by block in the reading threads)."""
        coff = self._coff
        shift = self._poff[self._prun] - coff[:-1]

        def rows(a: int, b: int) -> np.ndarray:
            k0 = int(np.searchsorted(coff, a, side="right")) - 1
            k1 = int(np.searchsorted(coff, b, side="left"))
            lens = np.minimum(coff[k0 + 1:k1 + 1], b) - np.maximum(coff[k0:k1], a)
            return np.repeat(shift[k0:k1], lens) + np.arange(a, b, dtype=np.int64)
        return rows

    def _full_coords(self, with_bins: bool = False, with_xyz: bool = True):
        """All coordinates (and / or ``bin_id``) in primary order: the
        coordinate partitions are read as they are stored (contiguous
        columns), then gathered into primary order block by block in threads
        (random reads, sequential writes: much faster than scattering into
        the strided ``(n, 3)`` array)."""
        n = self.n_spots
        coords = np.empty((n, 3) if with_xyz else (0, 3), dtype=np.float64)
        bid = np.empty(n, dtype=np.int64) if with_bins else None
        if not n:
            return (coords, bid) if with_bins else coords
        cols = ([BIN_ID] if with_bins else []) + (list(_XYZ) if with_xyz else [])
        src = {c: np.empty(n, dtype=np.int64 if c == BIN_ID else np.float64) for c in cols}
        self._crows.read_all("coords", cols, dest=src)
        poff = self._poff
        start = self._coff[self._crun] - poff[:-1]     # coordinate row - primary row, per primary run
        block = 1 << 18

        def one(a):
            b = min(n, a + block)
            k0 = int(np.searchsorted(poff, a, side="right")) - 1
            k1 = int(np.searchsorted(poff, b, side="left"))
            lens = np.minimum(poff[k0 + 1:k1 + 1], b) - np.maximum(poff[k0:k1], a)
            idx = np.repeat(start[k0:k1], lens) + np.arange(a, b, dtype=np.int64)
            for j, c in enumerate(_XYZ if with_xyz else ()):
                coords[a:b, j] = src[c][idx]
            if with_bins:
                bid[a:b] = src[BIN_ID][idx]

        if _par_serial():
            for a in range(0, n, block):
                one(a)
        else:
            list(_par.pool().map(one, range(0, n, block)))
        return (coords, bid) if with_bins else coords

    def _key_columns(self) -> List[str]:
        return [BIN_ID, "trace_id"] + (["cell_id"] if self._has_cell_id() else [])

    def _build22(self, *, prim=None, crd=None, rows: Optional[np.ndarray] = None, full: bool = False,
                 subset: bool = True, columns=None, tracks=None) -> ChromData:
        """In-memory ChromData of a format 2.2 store: ``prim`` (primary row
        ranges), ``crd`` (coordinate-table row ranges), ``rows`` (primary
        rows) or ``full`` — each in the order given (a full read: primary
        order)."""
        R, Cr = self._rows, self._crows
        spot_cols, track_cols, layer_keys = self._selection(columns, tracks)
        key_cols = self._key_columns()
        prim_cols = [c for c in self._primary_spot_cols if c in spot_cols]
        der_cols = [c for c in self._derived if c in spot_cols]
        want_st = "spot_tracks" in R.files and bool(track_cols)
        st_cols = None
        if want_st:
            st_cols = None if track_cols == list(self._spot_tracks_proxy.columns) else track_cols
        need_primary = bool(prim_cols) or want_st or bool(layer_keys)
        codes: Dict[str, np.ndarray] = {}
        st_finish = st_tab = ptab = None
        layers: Dict[str, np.ndarray] = {}
        if full:
            n = R.n
            coords, bid = self._full_coords(with_bins=True)
            lens = np.diff(self._poff)
            codes["trace_id"] = np.repeat(np.asarray(self._index["trace_codes"]), lens)
            if "cell_id" in key_cols:
                codes["cell_id"] = np.repeat(np.asarray(self._index["trace_cells"]), lens)
            if want_st:
                # decoded in threads while the spots are assembled below
                st_finish = R.read_all("spot_tracks", st_cols, deferred=True)
            if prim_cols:
                ptab = R.read_all("spots", prim_cols)
            for k in layer_keys:
                a = np.empty((n, 3), dtype=np.float64)
                R.read_all(f"layers/{k}", list(_XYZ), dest={c: a[:, j] for j, c in enumerate(_XYZ)})
                layers[k] = a
        else:
            if rows is not None:
                rows = np.asarray(rows, dtype=np.int64)
                ct = Cr.take("coords", self._p2c_rows(rows), key_cols + list(_XYZ))

                def pread(name, cols):
                    return R.take(name, rows, cols)
            else:
                if prim is not None:
                    ps, pe = _range_arrays(prim)
                    cs, ce = self._p2c(ps, pe)
                else:
                    cs, ce = _range_arrays(crd)
                    ps, pe = self._c2p(cs, ce) if need_primary else (None, None)
                ct = _read_ordered(Cr, "coords", cs, ce, key_cols + list(_XYZ))

                def pread(name, cols):
                    return _read_ordered(R, name, ps, pe, cols)
            coords = Cr.coords_of(ct)
            bid = ct.column(BIN_ID).to_numpy().astype(np.int64)
            for c in key_cols[1:]:
                codes[c] = ct.column(c).to_numpy()
            del ct
            if prim_cols:
                ptab = pread("spots", prim_cols)
            if want_st:
                st_tab = pread("spot_tracks", st_cols)
            for k in layer_keys:
                layers[k] = R.coords_of(pread(f"layers/{k}", list(_XYZ)))

        # -- spots: keys, derived columns, primary columns -----------------------
        cats = R.cats["spots"]
        data: Dict[str, object] = {BIN_ID: bid}
        for c in key_cols[1:]:
            categories, ordered = cats[c]
            data[c] = _from_codes(codes[c], categories, ordered)
        keycodes = {BIN_ID: bid, "trace_id": codes.get("trace_id"), "cell_id": codes.get("cell_id")}
        run_keys = ({"trace_id": np.asarray(self._index["trace_codes"]),
                     "cell_id": np.asarray(self._index["trace_cells"])} if full else {})
        for c in der_cols:
            d = self._derived[c]
            if d["kind"] == "string":   # a pandas string column (pandas 3 text)
                data[c] = _string_take(d, keycodes[d["key"]])
                continue
            if d["key"] in run_keys:     # constant over primary runs: one repeat
                vals = _par.repeat(d["values"][run_keys[d["key"]]], np.diff(self._poff))
            else:
                vals = _par.take(d["values"], keycodes[d["key"]])
            if d["kind"] == "category":
                categories, ordered = cats[c]
                data[c] = _from_codes(vals, categories, ordered)
            else:
                data[c] = vals
        if ptab is not None:
            pf = R.to_frame("spots", ptab)
            for c in prim_cols:
                col = pf[c]
                data[c] = col.to_numpy() if isinstance(col.dtype, np.dtype) else col.array
            del pf, ptab
        # one frame, columns in their stored order (no reordering copy)
        spots = pd.DataFrame({c: data[c] for c in self._spots_proxy.columns if c in data}, copy=False)
        del data
        spot_tracks = None
        if st_finish is not None:
            spot_tracks = R.to_frame("spot_tracks", st_finish())
        elif st_tab is not None:
            spot_tracks = R.to_frame("spot_tracks", st_tab)
        return self._finish_build(coords, spots, spot_tracks, layers, spot_cols, subset)

    def _chrom_coord_ranges(self, codes) -> List[Tuple[int, int]]:
        """Coordinate-table row ranges of the partitions of chromosome codes."""
        return self._segment_ranges(np.isin(np.asarray(self._cidx["partition_chrom"]), np.asarray(codes)),
                                    self._cidx["partition_offsets"])

    def to_memory(self, *, columns=None, tracks=None) -> ChromData:
        """Load everything (or the selected columns) into an in-memory
        :class:`ChromData` (the small tables are shared with this object,
        not copied)."""
        out = self._build(subset=False, columns=columns, tracks=tracks)
        out._source_path = self._source_path
        return out

    def _take(self, index, columns=None, tracks=None) -> ChromData:
        if isinstance(index, slice):
            start, stop, step = index.indices(self.n_spots)
            if step == 1:
                return self._build(ranges=[(start, stop)], columns=columns, tracks=tracks)
            index = np.arange(start, stop, step)
        if isinstance(index, (pd.Series, pd.Index)):
            index = index.to_numpy()
        idx = np.asarray(index)
        if idx.dtype == bool:
            if len(idx) != self.n_spots:
                raise IndexError("boolean index length != n_spots")
            idx = np.flatnonzero(idx)
        return self._build(rows=idx.astype(np.int64), columns=columns, tracks=tracks)

    def __getitem__(self, index) -> ChromData:
        return self._take(index)

    def _segment_ranges(self, mask: np.ndarray, offsets: np.ndarray) -> List[Tuple[int, int]]:
        sel = np.flatnonzero(mask)
        if not len(sel):
            return []
        offsets = np.asarray(offsets, dtype=np.int64)
        a, b = offsets[sel], offsets[sel + 1]
        # coalesce touching runs
        brk = np.r_[True, a[1:] != b[:-1]]
        starts = a[brk]
        ends = b[np.r_[brk[1:], True]]
        return list(zip(starts.tolist(), ends.tolist()))

    @staticmethod
    def _code_of(cats: Optional[pd.Index], value) -> Optional[int]:
        if cats is None:
            return None
        try:
            loc = cats.get_loc(value)
        except (KeyError, TypeError):
            return None
        return int(loc) if isinstance(loc, (int, np.integer)) else None

    def get_trace(self, trace_id, *, columns=None, tracks=None) -> ChromData:
        code = self._code_of(self._categories("trace_id"), trace_id)
        codes = np.asarray(self._index["trace_codes"])
        mask = codes == code if code is not None else np.zeros(len(codes), dtype=bool)
        return self._build(ranges=self._segment_ranges(mask, self._index["trace_offsets"]),
                           columns=columns, tracks=tracks)

    def get_cell(self, cell_id, *, columns=None, tracks=None) -> ChromData:
        if not self._has_cell_id():
            raise KeyError("spots has no 'cell_id' column")
        code = self._code_of(self._categories("cell_id"), cell_id)
        codes = np.asarray(self._index["cell_codes"])
        mask = codes == code if code is not None else np.zeros(len(codes), dtype=bool)
        return self._build(ranges=self._segment_ranges(mask, self._index["cell_offsets"]),
                           columns=columns, tracks=tracks)

    def _chrom_codes(self, chrom) -> np.ndarray:
        names = self._bins["chrom"].cat.categories.astype(str)
        return np.flatnonzero(np.asarray(names) == str(chrom))

    def _chrom_ranges(self, chrom) -> Tuple[List[Tuple[int, int]], bool]:
        """Row ranges holding the spots of ``chrom``, and whether they may
        also hold other chromosomes' spots (format 2.0 multi-chromosome runs)."""
        codes = self._chrom_codes(chrom)
        if self.partitioned:
            pc = np.asarray(self._index["partition_chrom"])
            return self._segment_ranges(np.isin(pc, codes), self._index["partition_offsets"]), False
        seg_chrom = np.asarray(self._index["chrom_trace"])
        pure = np.isin(seg_chrom, codes)
        mixed = seg_chrom < 0
        return self._segment_ranges(pure | mixed, self._index["trace_offsets"]), bool(mixed.any())

    def _keep_chrom(self, sub: ChromData, chrom) -> ChromData:
        ids = np.flatnonzero(self._bins["chrom"].astype(str).to_numpy() == str(chrom))
        keep = np.isin(sub.spots[BIN_ID].to_numpy(), ids)
        return sub if keep.all() else sub[keep]

    def _chroms_subset(self, codes, *, columns="coords", tracks=None) -> ChromData:
        """The spots of the chromosome codes ``codes`` (format 2.2: the
        coordinate partitions; otherwise the runs that may hold them, other
        chromosomes' spots of mixed runs included — the web browser filters
        them)."""
        codes = np.asarray(codes)
        if self._v22:
            return self._build22(crd=self._chrom_coord_ranges(codes), columns=columns, tracks=tracks)
        if self.partitioned:
            pc = np.asarray(self._index["partition_chrom"])
            return self._build(ranges=self._segment_ranges(np.isin(pc, codes), self._index["partition_offsets"]),
                               columns=columns, tracks=tracks)
        seg_chrom = np.asarray(self._index["chrom_trace"])
        mask = np.isin(seg_chrom, codes) | (seg_chrom < 0)
        return self._build(ranges=self._segment_ranges(mask, self._index["trace_offsets"]), columns=columns,
                           tracks=tracks)

    def get_chrom(self, chrom: str, *, columns=None, tracks=None) -> ChromData:
        if self._v22:
            # one coordinate partition (+ the chromosome's primary rows,
            # ascending, when other columns are selected)
            return self._build22(crd=self._chrom_coord_ranges(self._chrom_codes(chrom)),
                                 columns=columns, tracks=tracks)
        ranges, mixed = self._chrom_ranges(chrom)
        sub = self._build(ranges=ranges, columns=columns, tracks=tracks)
        return self._keep_chrom(sub, chrom) if mixed else sub

    # -- streaming -----------------------------------------------------------

    def _bytes_per_spot(self, columns=None, tracks=None) -> float:
        """Estimated in-memory bytes per spot of a selection (decoded Arrow +
        pandas + ChromData copies)."""
        spot_cols, track_cols, layer_keys = self._selection(columns, tracks)
        width = 8 * 3 + 8 * (len(spot_cols) + len(track_cols)) + 24 * len(layer_keys)
        return 3.0 * width

    def _run_batches(self, batch, chrom=None, columns=None, tracks=None):
        off = np.asarray(self._index["trace_offsets"], dtype=np.int64)
        n_seg = len(off) - 1
        lo, hi, mixed = 0, n_seg, False
        if chrom is not None:
            codes = self._chrom_codes(chrom)
            seg_chrom = np.asarray(self._index["chrom_trace"])
            sel = np.flatnonzero(np.isin(seg_chrom, codes) | (seg_chrom < 0))
            if not len(sel):
                return [], False
            if self.partitioned:
                lo, hi = int(sel[0]), int(sel[-1]) + 1
            else:
                mixed = bool((seg_chrom[sel] < 0).any())
                runs = sel
                size = resolve_batch(batch, (off[runs + 1] - off[runs]).mean() if len(runs) else 1,
                                     self._bytes_per_spot(columns, tracks))
                out = []
                for i in range(0, len(runs), size):
                    part = runs[i:i + size]
                    m = np.zeros(n_seg, dtype=bool)
                    m[part] = True
                    out.append(self._segment_ranges(m, off))
                return out, mixed
        n_runs = hi - lo
        mean_len = (off[hi] - off[lo]) / max(1, n_runs)
        size = resolve_batch(batch, mean_len, self._bytes_per_spot(columns, tracks))
        return [[(int(off[i]), int(off[min(i + size, hi)]))] for i in range(lo, hi, size)], mixed

    def _coord_run_batches(self, batch, chrom=None, columns=None, tracks=None):
        """Format 2.2: batches of (chromosome, cell, trace) runs of the
        coordinate table — the canonical stream order — as row ranges."""
        off = self._coff
        lo, hi = 0, len(off) - 1
        if chrom is not None:
            sel = np.flatnonzero(np.isin(np.asarray(self._cidx["chrom_trace"]), self._chrom_codes(chrom)))
            if not len(sel):
                return []
            lo, hi = int(sel[0]), int(sel[-1]) + 1
        n_runs = hi - lo
        mean_len = (off[hi] - off[lo]) / max(1, n_runs)
        size = resolve_batch(batch, mean_len, self._bytes_per_spot(columns, tracks))
        return [(int(off[i]), int(off[min(i + size, hi)])) for i in range(lo, hi, size)]

    def iter_traces(self, batch=1024, *, chrom=None, columns=None, tracks=None) -> Iterator[ChromData]:
        if self._v22:
            # the canonical order (chromosome › cell › trace): coordinate
            # runs; other columns from the matching primary runs
            for a, b in self._coord_run_batches(batch, chrom, columns, tracks):
                yield self._build22(crd=[(a, b)], columns=columns, tracks=tracks)
            return
        batches, mixed = self._run_batches(batch, chrom, columns, tracks)
        for ranges in batches:
            sub = self._build(ranges=ranges, columns=columns, tracks=tracks)
            yield self._keep_chrom(sub, chrom) if mixed else sub

    def iter_cells(self, batch=64, *, columns=None, tracks=None) -> Iterator[ChromData]:
        if not self._has_cell_id():
            raise KeyError("spots has no 'cell_id' column")
        idx = self._cidx if self._v22 else self._index
        codes = np.asarray(idx["cell_codes"], dtype=np.int64)
        off = np.asarray(idx["cell_offsets"], dtype=np.int64)
        part = np.asarray(idx["cell_partition"], dtype=np.int64)
        uniq = np.unique(codes[codes >= 0])
        if not len(uniq):
            return
        mean_cell = self.n_spots / len(uniq)
        size = resolve_batch(batch, mean_cell, self._bytes_per_spot(columns, tracks))
        bounds = np.r_[0, np.flatnonzero(part[1:] != part[:-1]) + 1, len(codes)]
        for i in range(0, len(uniq), size):
            c0, c1 = uniq[i], uniq[min(i + size, len(uniq)) - 1]
            ranges = []
            for a, b in zip(bounds[:-1], bounds[1:]):
                # cell runs of one partition are sorted by cell code
                k0 = a + int(np.searchsorted(codes[a:b], c0, side="left"))
                k1 = a + int(np.searchsorted(codes[a:b], c1, side="right"))
                if k1 > k0:
                    ranges.append((int(off[k0]), int(off[k1])))
            if self._v22:
                # coordinate-table order: chromosome › cell › trace, as in memory
                yield self._build22(crd=ranges, columns=columns, tracks=tracks)
            else:
                yield self._build(ranges=ranges, columns=columns, tracks=tracks)

    # ------------------------------------------------------------------
    # Whole-table operations (read the needed columns)
    # ------------------------------------------------------------------

    def spots_with_loci(self) -> pd.DataFrame:
        return self._spots_proxy.to_pandas()

    def tracks_spot_view(self, columns: Optional[List[str]] = None) -> pd.DataFrame:
        bt = self._bin_tracks
        st_cols = list(self._spot_tracks_proxy.columns) if self._spot_tracks_proxy is not None else []
        want = [str(c) for c in columns] if columns is not None else None
        if want is not None:
            missing = [c for c in want if c not in bt.columns and c not in st_cols]
            if missing:
                raise KeyError(f"unknown track(s): {missing}")
        b_cols = [c for c in bt.columns if want is None or c in want]
        s_cols = [c for c in st_cols if want is None or c in want]
        parts = []
        if b_cols:
            bid = self._spots_proxy[BIN_ID].to_numpy()
            parts.append(bt[b_cols].iloc[bid].reset_index(drop=True))
        if s_cols:
            parts.append(self._spot_tracks_proxy[s_cols])
        if not parts:
            return pd.DataFrame(index=pd.RangeIndex(self.n_spots))
        out = pd.concat(parts, axis=1) if len(parts) > 1 else parts[0]
        order = want if want is not None else self._spot_view_order
        if order:
            front = [c for c in order if c in out.columns]
            out = out[front + [c for c in out.columns if c not in front]]
        return out

    def to_dataframe(self, include_bin_id: bool = False) -> pd.DataFrame:
        return self.to_memory().to_dataframe(include_bin_id=include_bin_id)

    def compute_distances(self, trace_id=None) -> np.ndarray:
        if trace_id is not None:
            return self.get_trace(trace_id, columns="coords").compute_distances()
        return self.to_memory(columns="coords").compute_distances()

    def copy(self) -> ChromData:
        return self.to_memory().copy()

    def to_anndata(self):
        return self.to_memory().to_anndata()

    def write(self, path, **kwargs) -> None:
        """Write a copy (the data is loaded into memory first)."""
        self.to_memory().write(path, **kwargs)

    def rebuild_bins(self):
        raise AttributeError(_READ_ONLY)

    def _set_spot_aligned_tracks(self, value) -> None:
        raise AttributeError(_READ_ONLY)

    def _set_track_column(self, name, values) -> None:
        raise AttributeError(_READ_ONLY)

    def _check_bin_ids(self) -> None:
        return None

    def close(self) -> None:
        """Release the store (the object is unusable afterwards)."""
        self._c.close()

    def __repr__(self) -> str:
        return super().__repr__().replace("ChromData:", f"ChromData (backed: {self._backing_path.name}):", 1)


__all__ = ["BackedArray", "BackedChromData", "BackedFrame"]
