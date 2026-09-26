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
from .cdata import ChromData, _empty_frame
from .intervals import IntervalStore
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
        empty = self._rows.pf(self._name).schema_arrow.empty_table()
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


class BackedChromData(ChromData):
    """A :class:`ChromData` whose spot-aligned data stays on disk.

    Created by ``ChromData.read(path, backed=True)`` on a
    ``.chromdata.zarr`` directory or ``.cdz`` file.  See the module
    docstring for what is eager and what is lazy.
    """

    def __init__(self, path, *, _container: Optional[Container] = None):  # noqa: D401
        c = _container or Container(path)
        parts = read_small_parts(c)
        self._c = c
        self._parts = parts
        self._rows = SpotRows(c, parts)
        self._index = parts["index"]
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
        stored = [c for c in self._rows.columns("spots") if c not in spot_meta.get("coords", ())]
        order = [c for c in spot_meta.get("column_order", []) if c in stored or c in LOCI]
        cols = order + [c for c in stored if c not in order]
        for c in LOCI:
            if c not in cols:
                cols.insert(LOCI.index(c), c)
        self._spots_proxy = BackedFrame(self, "spots", cols)
        self._coords_proxy = BackedArray(self._rows, "spots")
        if "spot_tracks" in self._rows.files:
            self._spot_tracks_proxy = BackedFrame(self, "spot_tracks", self._rows.columns("spot_tracks"))
        else:
            self._spot_tracks_proxy = None
        self.layers = {k: BackedArray(self._rows, f"layers/{k}")
                       for k in tmeta.get("layers", {})}

    # ------------------------------------------------------------------
    # Lazy attributes
    # ------------------------------------------------------------------

    @property
    def backed(self) -> bool:
        return True

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
        codes = np.asarray(self._index["cell_codes"])
        codes = codes[codes >= 0]
        return pd.Index([str(x) for x in np.asarray(cats)[codes]], name="cell_id")

    # ------------------------------------------------------------------
    # Row access → in-memory ChromData
    # ------------------------------------------------------------------

    def _build(self, *, ranges: Optional[Sequence[Tuple[int, int]]] = None,
               rows: Optional[np.ndarray] = None, subset: bool = True) -> ChromData:
        r = self._rows

        def read(name, cols=None):
            if rows is not None:
                return r.take(name, rows, cols)
            if ranges is None:
                return r.read_all(name, cols)
            return r.read_ranges(name, ranges, cols)

        t = read("spots")
        coord_cols = list(self._parts["spot_meta"].get("coords", ("x", "y", "z")))
        coords = r.coords_of(t, coord_cols)
        t = t.drop_columns(coord_cols)
        spots = r.to_frame("spots", t)
        del t
        spot_tracks = None
        if "spot_tracks" in r.files:
            spot_tracks = r.to_frame("spot_tracks", read("spot_tracks"))
        layers = {k: r.coords_of(read(f"layers/{k}")) for k in self.layers}
        if subset:
            traces = self._filter_traces(spots)
            cells, cellm = self._filter_cells(spots)
            points = self._filter_points(spots)
        else:
            traces, cells, cellm, points = self.traces, self.cells, self.cellm, self.points
        out = ChromData(
            coords, spots, bins=self._bins,
            cells=cells if len(cells) or len(cells.columns) else None,
            cellm=cellm or None, binm=self.binm or None, intervals=self._intervals,
            traces=traces if len(traces) or len(traces.columns) else None,
            layers=layers or None, results=self.results, uns=self.uns,
            points=points or None, validate=False, _own_spots=True,
        )
        out._bin_tracks = self._bin_tracks
        if spot_tracks is not None:
            out._spot_tracks = spot_tracks
        out._spot_view_order = list(self._spot_view_order) if self._spot_view_order else None
        order = list(self._spots_proxy.columns)
        out.spots = out.spots[[c for c in order if c in out.spots.columns]
                              + [c for c in out.spots.columns if c not in order]]
        return out

    def to_memory(self) -> ChromData:
        """Load everything into an in-memory :class:`ChromData` (the small
        tables are shared with this object, not copied)."""
        out = self._build(subset=False)
        out._source_path = self._source_path
        return out

    def __getitem__(self, index) -> ChromData:
        if isinstance(index, slice):
            start, stop, step = index.indices(self.n_spots)
            if step == 1:
                return self._build(ranges=[(start, stop)])
            index = np.arange(start, stop, step)
        if isinstance(index, (pd.Series, pd.Index)):
            index = index.to_numpy()
        idx = np.asarray(index)
        if idx.dtype == bool:
            if len(idx) != self.n_spots:
                raise IndexError("boolean index length != n_spots")
            idx = np.flatnonzero(idx)
        return self._build(rows=idx.astype(np.int64))

    def _segment_ranges(self, mask: np.ndarray, offsets: np.ndarray) -> List[Tuple[int, int]]:
        sel = np.flatnonzero(mask)
        ranges: List[Tuple[int, int]] = []
        for i in sel:
            a, b = int(offsets[i]), int(offsets[i + 1])
            if ranges and ranges[-1][1] == a:
                ranges[-1] = (ranges[-1][0], b)
            else:
                ranges.append((a, b))
        return ranges

    @staticmethod
    def _code_of(cats: Optional[pd.Index], value) -> Optional[int]:
        if cats is None:
            return None
        try:
            loc = cats.get_loc(value)
        except (KeyError, TypeError):
            return None
        return int(loc) if isinstance(loc, (int, np.integer)) else None

    def get_trace(self, trace_id) -> ChromData:
        code = self._code_of(self._categories("trace_id"), trace_id)
        codes = np.asarray(self._index["trace_codes"])
        mask = codes == code if code is not None else np.zeros(len(codes), dtype=bool)
        return self._build(ranges=self._segment_ranges(mask, self._index["trace_offsets"]))

    def get_cell(self, cell_id) -> ChromData:
        if not self._has_cell_id():
            raise KeyError("spots has no 'cell_id' column")
        code = self._code_of(self._categories("cell_id"), cell_id)
        codes = np.asarray(self._index["cell_codes"])
        mask = codes == code if code is not None else np.zeros(len(codes), dtype=bool)
        return self._build(ranges=self._segment_ranges(mask, self._index["cell_offsets"]))

    def get_chrom(self, chrom: str) -> ChromData:
        names = self._bins["chrom"].cat.categories.astype(str)
        codes = np.flatnonzero(np.asarray(names) == str(chrom))
        seg_chrom = np.asarray(self._index["chrom_trace"])
        pure = np.isin(seg_chrom, codes)
        mixed = seg_chrom < 0
        sub = self._build(ranges=self._segment_ranges(pure | mixed, self._index["trace_offsets"]))
        if mixed.any():
            ids = np.flatnonzero(self._bins["chrom"].astype(str).to_numpy() == str(chrom))
            keep = np.isin(sub.spots[BIN_ID].to_numpy(), ids)
            if not keep.all():
                sub = sub[keep]
        return sub

    def iter_traces(self, batch: int = 1024) -> Iterator[ChromData]:
        off = np.asarray(self._index["trace_offsets"], dtype=np.int64)
        n_seg = len(off) - 1
        for i in range(0, n_seg, max(1, int(batch))):
            j = min(i + int(batch), n_seg)
            yield self._build(ranges=[(int(off[i]), int(off[j]))])

    def iter_cells(self, batch: int = 64) -> Iterator[ChromData]:
        if not self._has_cell_id():
            raise KeyError("spots has no 'cell_id' column")
        off = np.asarray(self._index["cell_offsets"], dtype=np.int64)
        n = len(off) - 1
        for i in range(0, n, max(1, int(batch))):
            j = min(i + int(batch), n)
            yield self._build(ranges=[(int(off[i]), int(off[j]))])

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
            return self.get_trace(trace_id).compute_distances()
        return self.to_memory().compute_distances()

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
