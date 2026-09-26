"""Streaming writer for ``.chromdata.zarr`` stores larger than memory.

::

    from uchrom import ChromData

    with ChromData.writer("big.chromdata.zarr", memory_budget="4GB") as w:
        for chunk in chunks:                  # ChromData objects, or arrays
            w.append(chunk)                   #   w.append(coords=..., spots=..., spot_tracks=...)
        w.finish(cells=cells, uns={...})      # optional small tables
    cd = ChromData.read("big.chromdata.zarr", backed=True)

How it works
------------
1. :meth:`ChromDataWriter.append` splits a chunk by chromosome and spills
   each piece to a temporary Parquet *run* (``<store>.spill/``), sorted by the
   partition's range key (the cell id, or the trace id without cells) —
   memory is one chunk.  Loci are registered as they come (provisional ids),
   trace / cell ids collected, per-chunk small tables (cells, traces, …) kept.
2. :meth:`ChromDataWriter.finish` fixes the bins (given, or derived from the
   loci exactly as ``ChromData`` derives them), the ``trace_id`` / ``cell_id``
   categories (sorted, as ``astype("category")`` makes them), and writes the
   store partition by partition: a chromosome's runs are merged in *pieces* of
   whole cells that fit the memory budget (each run is sorted by cell id, so a
   piece is one slice per run), sorted by (cell, trace, bin, input row) and
   handed to :class:`~uchrom.core.zarrcd.SpotPartitionWriter`.  The result is
   the store ``ChromData(...).write(path)`` writes for the concatenated input
   — same rows, order, index and row groups.

Memory: one chunk while appending; one piece (≤ ``memory_budget`` / 4 of
decoded rows) plus the loci / id registries while finishing.  Disk: the
spill runs (about the size of the store), removed at the end.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

from .bins import BIN_ID, LOCI, bins_from_loci, map_loci_to_bins, normalise_bins
from .zarrcd import (
    DEFAULT_ROW_GROUP_ROWS, DEFAULT_ZSTD_LEVEL, SpotPartitionWriter, ZARR_SUFFIX, _arrow_column,
    _code_dtype, _compressor, _is_chromdata_dir, _partition_meta, _rmtree, _safe_names,
    _write_frame, _write_root_meta, _write_small_parts, _zarr, _zarr_array, partition_dirs,
)

PathLike = Union[str, Path]

_CELL = "__cell"
_TRACE = "__trace"
_PID = "__pid"      # provisional locus id
_SEQ = "__seq"      # input row number
_SPILL_GROUP_ROWS = 1 << 16


def _as_values(s: pd.Series) -> np.ndarray:
    """Plain values of an id column (categoricals decoded)."""
    if isinstance(s.dtype, pd.CategoricalDtype):
        return np.asarray(s.astype(s.cat.categories.dtype if s.cat.categories.dtype != object else object))
    return s.to_numpy()


class ChromDataWriter:
    """Write a ``.chromdata.zarr`` store from chunks (see the module docstring).

    Parameters
    ----------
    path : path ending in ``.chromdata.zarr`` (``.cdz`` is not supported for
        streaming; zip the finished directory instead).
    bins : DataFrame, optional
        The locus table (``chrom``, ``start``, ``end`` + extra columns).  Chunk
        loci must be rows of it.  Default: derived from the loci seen, as
        ``ChromData`` derives them (chromosome, start, end order).  Can also
        be given to :meth:`finish`.
    coord_dtype, row_group_rows, compression_level, keep_source_order
        As for :meth:`ChromData.write`.
    memory_budget : int or str, optional
        Working-memory target of :meth:`finish` (default
        :data:`uchrom.settings.memory_budget`).
    """

    def __init__(self, path: PathLike, *, bins: Optional[pd.DataFrame] = None,
                 coord_dtype: str = "float64", row_group_rows: int = DEFAULT_ROW_GROUP_ROWS,
                 compression_level: int = DEFAULT_ZSTD_LEVEL, keep_source_order: bool = True,
                 memory_budget=None, spill_dir: Optional[PathLike] = None):
        from uchrom.settings import settings

        self.path = Path(path)
        if not self.path.name.lower().endswith(".zarr"):
            raise ValueError("the streaming writer writes a directory store: use a "
                             f"'<name>{ZARR_SUFFIX}' path")
        if self.path.exists() and self.path.is_dir() and not _is_chromdata_dir(self.path):
            raise FileExistsError(f"{self.path} exists and is not a ChromData store; refusing to replace it")
        self.coord_dtype = np.dtype(coord_dtype)
        if self.coord_dtype not in (np.dtype("float32"), np.dtype("float64")):
            raise ValueError("coord_dtype must be float32 or float64")
        self.row_group_rows = int(row_group_rows)
        self.level = int(compression_level)
        self.keep_source_order = bool(keep_source_order)
        self.memory_budget = settings.resolve_budget(memory_budget)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        base = Path(spill_dir) if spill_dir is not None else self.path.parent
        self.spill = base / f".{self.path.name}.{uuid.uuid4().hex[:8]}.spill"
        self.spill.mkdir(parents=True)
        self.bins = normalise_bins(bins) if bins is not None else None
        self._closed = False
        self.n = 0
        self._runs: Dict[str, List[Dict[str, Any]]] = {}
        self._schemas: List[Any] = []
        self._loci = pd.DataFrame({"chrom": pd.Series([], dtype=object), "start": pd.Series([], dtype=np.int64),
                                   "end": pd.Series([], dtype=np.int64)})
        self._loci_index = pd.MultiIndex.from_arrays([[], [], []])
        self._trace_vals: List[np.ndarray] = []
        self._cell_vals: List[np.ndarray] = []
        self._has_cells: Optional[bool] = None
        self._column_order: Optional[List[str]] = None
        self._spot_cols: Optional[List[str]] = None
        self._cat_cols: Dict[str, List[Any]] = {}
        self._track_cols: Optional[List[str]] = None
        self._layer_keys: Optional[List[str]] = None
        self._parts: Dict[str, List[Any]] = {"cells": [], "cellm": [], "traces": [], "points": []}
        self._uns: Dict[str, Any] = {}
        self._run_id = 0
        self._chunk_sorted = True

    # ------------------------------------------------------------------
    # appending
    # ------------------------------------------------------------------

    def __enter__(self) -> "ChromDataWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self.abort()
        elif not self._closed:
            self.finish()

    def abort(self) -> None:
        """Drop the spill files; no store is written."""
        _rmtree(self.spill)
        self._closed = True

    def append(self, chunk=None, *, coords=None, spots: Optional[pd.DataFrame] = None,
               spot_tracks: Optional[pd.DataFrame] = None,
               layers: Optional[Mapping[str, np.ndarray]] = None) -> None:
        """Add rows: a ``ChromData`` chunk, or ``coords`` + ``spots`` (with
        ``chrom``, ``start``, ``end``, ``trace_id`` [, ``cell_id``, …]) and
        optional per-spot ``spot_tracks`` / ``layers``.

        A ``ChromData`` chunk also contributes its ``cells`` / ``cellm`` /
        ``traces`` / ``points`` (concatenated on :meth:`finish` unless given
        there) and its bin-level tracks become spot-level columns of
        ``spot_tracks`` (streaming cannot tell a per-locus signal from its
        chunks; pass per-locus signals as ``finish(bin_tracks=...)``).
        """
        if self._closed:
            raise RuntimeError("writer is closed")
        if chunk is not None:
            if spots is not None or coords is not None:
                raise ValueError("pass a ChromData chunk or coords= / spots=, not both")
            spots = chunk.spots
            coords = np.asarray(chunk.coords)
            st = chunk.spot_tracks
            bt = chunk.bin_tracks
            if len(bt.columns):
                view = bt.iloc[spots[BIN_ID].to_numpy()].reset_index(drop=True)
                st = pd.concat([st.reset_index(drop=True), view], axis=1) if len(st.columns) else view
            spot_tracks = st if len(st.columns) else None
            layers = {k: np.asarray(v) for k, v in chunk.layers.items()}
            for key in ("cells", "traces"):
                df = getattr(chunk, key)
                if len(df) or len(df.columns):
                    self._parts[key].append(df)
            if chunk.cellm:
                self._parts["cellm"].append(dict(chunk.cellm))
            if chunk.points:
                self._parts["points"].append(dict(chunk.points))
            if not self._uns:
                self._uns = dict(chunk.uns)
        if spots is None or coords is None:
            raise ValueError("append needs coords and spots")
        coords = np.asarray(coords, dtype=np.float64)
        m = len(spots)
        if coords.shape != (m, 3):
            raise ValueError(f"coords shape {coords.shape} != ({m}, 3)")
        missing = [c for c in (*LOCI, "trace_id") if c not in spots.columns]
        if missing:
            raise ValueError(f"spots needs columns {missing}")
        has_cells = "cell_id" in spots.columns
        if self._has_cells is None:
            self._has_cells = has_cells
            order = [str(c) for c in spots.columns]
            if BIN_ID not in order:
                order.append(BIN_ID)
            self._column_order = order
            self._spot_cols = [c for c in order if c not in (*LOCI, BIN_ID, "trace_id", "cell_id")]
            self._track_cols = [str(c) for c in spot_tracks.columns] if spot_tracks is not None else []
            self._layer_keys = [str(k) for k in (layers or {})]
        elif has_cells != self._has_cells:
            raise ValueError("every chunk needs a cell_id column, or none")
        extra = [str(c) for c in spots.columns if c not in (*LOCI, BIN_ID, "trace_id", "cell_id")]
        if extra != self._spot_cols:
            raise ValueError(f"spot columns {extra} differ from the first chunk's {self._spot_cols}")
        tcols = [str(c) for c in spot_tracks.columns] if spot_tracks is not None else []
        if tcols != self._track_cols:
            raise ValueError(f"spot tracks {tcols} differ from the first chunk's {self._track_cols}")
        if sorted(layers or {}) != sorted(self._layer_keys):
            raise ValueError("every chunk needs the same layers")
        if m == 0:
            return

        chrom = spots["chrom"].astype(str).to_numpy()
        start = pd.to_numeric(spots["start"]).to_numpy().astype(np.int64)
        end = pd.to_numeric(spots["end"]).to_numpy().astype(np.int64)
        pid = self._register_loci(chrom, start, end)
        trace = _as_values(spots["trace_id"])
        self._trace_vals.append(pd.unique(trace))
        cell = _as_values(spots["cell_id"]) if has_cells else None
        if cell is not None:
            self._cell_vals.append(pd.unique(cell))
        if pd.isna(trace).any() or (cell is not None and pd.isna(cell).any()):
            raise ValueError("trace_id / cell_id must not be missing")

        import pyarrow as pa

        cols: Dict[str, Any] = {_TRACE: _arrow_column(pd.Series(trace), _TRACE),
                                _PID: pa.array(pid),
                                _SEQ: pa.array(np.arange(self.n, self.n + m, dtype=np.int64))}
        if cell is not None:
            cols[_CELL] = _arrow_column(pd.Series(cell), _CELL)
        for c in self._spot_cols:
            s = spots[c].reset_index(drop=True)
            if isinstance(s.dtype, pd.CategoricalDtype):
                self._cat_cols.setdefault(c, []).append(list(s.cat.categories))
                s = pd.Series(_as_values(s))
            cols[f"s:{c}"] = _arrow_column(s, c)
        for j, c in enumerate(("x", "y", "z")):
            cols[c] = pa.array(np.ascontiguousarray(coords[:, j]))
        if spot_tracks is not None:
            st = spot_tracks.reset_index(drop=True)
            for c in self._track_cols:
                s = st[c]
                if isinstance(s.dtype, pd.CategoricalDtype):
                    self._cat_cols.setdefault(f"t:{c}", []).append(list(s.cat.categories))
                    s = pd.Series(_as_values(s))
                cols[f"t:{c}"] = _arrow_column(s, c)
        for k in self._layer_keys:
            a = np.asarray(layers[k], dtype=np.float64)
            if a.shape != (m, 3):
                raise ValueError(f"layers[{k!r}] shape {a.shape} != ({m}, 3)")
            for j, c in enumerate(("x", "y", "z")):
                cols[f"l:{k}:{c}"] = pa.array(np.ascontiguousarray(a[:, j]))
        table = pa.table(cols)
        key = (cell if cell is not None else trace)
        self._spill(table, chrom, key)
        self.n += m

    def _register_loci(self, chrom, start, end) -> np.ndarray:
        if self.bins is not None:
            frame = pd.DataFrame({"chrom": chrom, "start": start, "end": end})
            bid = map_loci_to_bins(frame, self.bins)
            if (bid < 0).any():
                bad = frame[bid < 0].head(3).to_dict("records")
                raise ValueError(f"{int((bid < 0).sum())} spot locus/loci not in bins, e.g. {bad}")
            return bid
        key = pd.MultiIndex.from_arrays([chrom, start, end])
        pid = self._loci_index.get_indexer(key)
        new = pid < 0
        if new.any():
            fresh = pd.DataFrame({"chrom": chrom[new], "start": start[new], "end": end[new]}).drop_duplicates()
            self._loci = pd.concat([self._loci, fresh], ignore_index=True)
            self._loci_index = pd.MultiIndex.from_arrays(
                [self._loci["chrom"].to_numpy(), self._loci["start"].to_numpy(), self._loci["end"].to_numpy()])
            pid = self._loci_index.get_indexer(key)
        return pid.astype(np.int64)

    def _spill(self, table, chrom: np.ndarray, key: np.ndarray) -> None:
        """One run per chromosome of the chunk, sorted by the range key."""
        import pyarrow as pa
        import pyarrow.parquet as pq

        codes, names = pd.factorize(chrom)
        kcodes, kvals = pd.factorize(key, sort=True)
        order = np.lexsort((kcodes, codes))          # stable: chrom, then key
        codes_s = codes[order]
        bounds = np.r_[0, np.flatnonzero(codes_s[1:] != codes_s[:-1]) + 1, len(order)]
        for a, b in zip(bounds[:-1], bounds[1:]):
            name = str(names[codes_s[a]])
            rows = order[a:b]
            part = table.take(pa.array(rows))
            k = kcodes[rows]
            starts = np.r_[0, np.flatnonzero(k[1:] != k[:-1]) + 1]
            d = self.spill / f"run-{self._run_id:06d}.parquet"
            self._run_id += 1
            pq.write_table(part, d, compression="zstd", compression_level=1,
                           row_group_size=_SPILL_GROUP_ROWS)
            self._schemas.append(part.schema)
            self._runs.setdefault(name, []).append({
                "path": d, "n": int(b - a), "keys": np.asarray(kvals)[k[starts]],
                "starts": np.r_[starts, b - a].astype(np.int64)})

    # ------------------------------------------------------------------
    # registries
    # ------------------------------------------------------------------

    def loci(self) -> pd.DataFrame:
        """The distinct ``chrom`` / ``start`` / ``end`` appended so far (a
        stand-in for the spots when a loader derives its bins from them)."""
        if self.bins is not None:
            return self.bins[list(LOCI)].reset_index(drop=True)
        return self._loci.copy()

    def unique(self, column: str) -> np.ndarray:
        """Distinct values of ``trace_id`` / ``cell_id`` appended so far."""
        vals = {"trace_id": self._trace_vals, "cell_id": self._cell_vals}[column]
        return pd.unique(np.concatenate(vals)) if vals else np.zeros(0, dtype=object)

    @property
    def n_spots(self) -> int:
        return self.n

    # ------------------------------------------------------------------
    # finishing
    # ------------------------------------------------------------------

    def finish(self, *, bins: Optional[pd.DataFrame] = None, cells: Optional[pd.DataFrame] = None,
               cellm: Optional[Mapping[str, np.ndarray]] = None,
               traces: Optional[pd.DataFrame] = None, bin_tracks: Optional[pd.DataFrame] = None,
               binm: Optional[Mapping[str, np.ndarray]] = None, intervals=None, points=None,
               results=None, uns: Optional[Mapping[str, Any]] = None) -> Path:
        """Write the store (atomically) and remove the spill files.  Small
        tables given here replace the ones collected from the chunks."""
        if self._closed:
            raise RuntimeError("writer is closed")
        import tempfile

        from .intervals import IntervalStore
        from .results import ResultsStore

        try:
            final_bins, pmap = self._final_bins(bins)
            cats = self._categories()
            cells = cells if cells is not None else _concat_frames(self._parts["cells"])
            traces = traces if traces is not None else _concat_frames(self._parts["traces"])
            if cellm is None:
                cellm = ({k: np.concatenate([d[k] for d in self._parts["cellm"]])
                          for k in self._parts["cellm"][0]} if self._parts["cellm"] else {})
            if points is None:
                points = ({k: pd.concat([d[k] for d in self._parts["points"]], ignore_index=True)
                           for k in self._parts["points"][0]} if self._parts["points"] else {})
            uns = dict(uns) if uns is not None else dict(self._uns)
            if bin_tracks is None:
                bin_tracks = pd.DataFrame(index=pd.RangeIndex(len(final_bins), name=BIN_ID))
            else:
                if len(bin_tracks) != len(final_bins):
                    raise ValueError(f"bin_tracks has {len(bin_tracks)} rows, bins {len(final_bins)}")
                bin_tracks = bin_tracks.reset_index(drop=True)
                bin_tracks.index = pd.RangeIndex(len(final_bins), name=BIN_ID)
            tmp = Path(tempfile.mkdtemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent))
            try:
                self._write(tmp, final_bins, pmap, cats, cells=cells if cells is not None else pd.DataFrame(),
                            traces=traces if traces is not None else pd.DataFrame(), cellm=dict(cellm),
                            bin_tracks=bin_tracks, binm=dict(binm or {}),
                            intervals=IntervalStore.coerce(intervals or {}), points=dict(points),
                            results=results if results is not None else ResultsStore(), uns=uns)
                import os
                if self.path.exists():
                    old = self.path.parent / f".{self.path.name}.{uuid.uuid4().hex}.old"
                    os.replace(self.path, old)
                    os.replace(tmp, self.path)
                    _rmtree(old)
                else:
                    os.replace(tmp, self.path)
            finally:
                if tmp.exists():
                    _rmtree(tmp)
        finally:
            _rmtree(self.spill)
            self._closed = True
        return self.path

    close = finish

    def _final_bins(self, bins) -> Tuple[pd.DataFrame, np.ndarray]:
        """(bins, provisional id → bin_id)."""
        if bins is not None and self.bins is not None:
            raise ValueError("bins were given to the writer already")
        if self.bins is not None:
            return self.bins, np.arange(len(self.bins), dtype=np.int64)
        loci = self._loci
        if bins is not None:
            bins = normalise_bins(bins)
            pmap = map_loci_to_bins(loci, bins)
            if (pmap < 0).any():
                bad = loci[pmap < 0].head(3).to_dict("records")
                raise ValueError(f"{int((pmap < 0).sum())} spot locus/loci not in bins, e.g. {bad}")
            return bins, pmap
        if not len(loci):
            from .bins import empty_bins
            return empty_bins(), np.zeros(0, dtype=np.int64)
        return bins_from_loci(loci)

    def _categories(self) -> Dict[str, pd.Index]:
        """Sorted distinct trace / cell ids — the categories ``astype("category")`` makes."""
        out = {}
        for col, vals in (("trace_id", self._trace_vals), ("cell_id", self._cell_vals)):
            if vals:
                out[col] = pd.Categorical(pd.unique(np.concatenate(vals))).categories
        return out

    def _unified_schema(self):
        """One Arrow type per spill column over all runs (int → float when
        some chunk had floats; a numeric / string mix → string)."""
        import pyarrow as pa
        import pyarrow.types as pat

        if not self._schemas:
            return None
        fields = {}
        for sch in self._schemas:
            for f in sch:
                fields.setdefault(f.name, []).append(f.type)
        out = []
        for name in self._schemas[0].names:
            types = [t for t in fields[name] if not pat.is_null(t)]
            if not types:
                out.append(pa.field(name, pa.null()))
                continue
            if all(t == types[0] for t in types):
                typ = types[0]
            elif all(pat.is_integer(t) or pat.is_floating(t) for t in types):
                typ = pa.float64() if any(pat.is_floating(t) for t in types) else pa.int64()
            elif all(pat.is_boolean(t) for t in types):
                typ = pa.bool_()
            else:
                typ = pa.string()
            out.append(pa.field(name, typ))
        return pa.schema(out)

    def _row_bytes(self, schema) -> float:
        import pyarrow.types as pat

        w = 0
        for f in schema:
            w += (f.type.bit_width // 8) if pat.is_integer(f.type) or pat.is_floating(f.type) else 32
        return float(max(w, 8))

    def _write(self, root_path: Path, bins: pd.DataFrame, pmap: np.ndarray, cats: Dict[str, pd.Index],
               **small) -> None:
        import pyarrow as pa
        import pyarrow.parquet as pq

        zarr = _zarr()
        comp = _compressor(self.level)
        root = zarr.open_group(str(root_path), mode="w", zarr_format=3)
        tpath = root_path / "tables"
        tables_meta: Dict[str, Any] = {}
        has_cells = bool(self._has_cells)
        n_bins = len(bins)
        schema = self._unified_schema()
        cat_dir = tpath / "categories"

        # categories of the coded spot columns
        spot_cat: Dict[str, Any] = {}
        track_cat: Dict[str, Any] = {}
        code_cats: Dict[str, pd.Index] = {}
        for col in ("trace_id", "cell_id"):
            if col in cats:
                code_cats[f"__{col}"] = cats[col]
        extra_cats: Dict[str, pd.Index] = {}
        for key, lists in self._cat_cols.items():
            same = all(lst == lists[0] for lst in lists)
            extra_cats[key] = pd.Index(lists[0]) if same else pd.Categorical(
                pd.unique(np.concatenate([np.asarray(lst, dtype=object) for lst in lists]))).categories

        def write_cats(meta, table, col, index, i):
            fname = f"{table}.{col}" if _SAFE(col) else f"{table}._{i}"
            _write_frame(pd.DataFrame({"value": np.asarray(index)}) if len(index) else
                         pd.DataFrame({"value": pd.Series([], dtype=object)}),
                         cat_dir / f"{fname}.parquet", self.level)
            meta[col] = {"file": f"categories/{fname}.parquet", "ordered": False}

        stored_spot_cols = [c for c in self._column_order if c not in LOCI]
        for i, col in enumerate(stored_spot_cols):
            if col in cats:
                write_cats(spot_cat, "spots", col, cats[col], i)
            elif col in extra_cats:
                write_cats(spot_cat, "spots", col, extra_cats[col], i)
        for i, col in enumerate(self._track_cols):
            if f"t:{col}" in extra_cats:
                write_cats(track_cat, "spot_tracks", col, extra_cats[f"t:{col}"], i)

        tables_meta["spots"] = {"n_rows": self.n, "categorical": spot_cat, "coords": ["x", "y", "z"],
                                "coord_dtype": self.coord_dtype.name, "column_order": list(self._column_order)}
        names = ["spots"]
        if self._track_cols:
            tables_meta["spot_tracks"] = {"n_rows": self.n, "categorical": track_cat,
                                          "spot_view_order": None}
            names.append("spot_tracks")
        layer_names = _safe_names(list(self._layer_keys))
        names += [f"layers/{k}" for k in self._layer_keys]
        w = SpotPartitionWriter(tpath, names, level=self.level, row_group_rows=self.row_group_rows,
                                has_cells=has_cells, layer_names=layer_names)

        chrom_names = [str(c) for c in bins["chrom"].cat.categories]
        # chromosome of every spill partition, in the final chromosome order
        run_chrom = {name: chrom_names.index(name) if name in chrom_names else None
                     for name in self._runs}
        for name, code in run_chrom.items():
            if code is None:
                raise ValueError(f"chromosome {name!r} of the spots is not in bins")
        order = sorted(self._runs, key=lambda nm: run_chrom[nm])
        dirs = partition_dirs(order)
        budget_rows = max(1, int(self.memory_budget // (4 * self._row_bytes(schema)))) if schema else 1
        seq_parts: List[np.ndarray] = []
        key_cats = cats.get("cell_id" if has_cells else "trace_id")
        for p, name in enumerate(order):
            runs = self._runs[name]
            w.begin(run_chrom[name], name, dirs[p])
            # piece plan: key codes of each run, rows per key code
            run_codes = [key_cats.get_indexer(r["keys"]) for r in runs]
            all_codes = np.unique(np.concatenate(run_codes))
            counts = np.zeros(len(all_codes), dtype=np.int64)
            for r, rc in zip(runs, run_codes):
                counts[np.searchsorted(all_codes, rc)] += np.diff(r["starts"])
            csum = np.cumsum(counts)
            cuts = [0]
            while cuts[-1] < len(all_codes):
                base = csum[cuts[-1] - 1] if cuts[-1] else 0
                k = int(np.searchsorted(csum, base + budget_rows, side="right"))
                cuts.append(max(k, cuts[-1] + 1))
            for c0, c1 in zip(cuts[:-1], cuts[1:]):
                lo_code, hi_code = all_codes[c0], all_codes[c1 - 1]
                pieces = []
                for r, rc in zip(runs, run_codes):
                    k0 = int(np.searchsorted(rc, lo_code, side="left"))
                    k1 = int(np.searchsorted(rc, hi_code, side="right"))
                    if k1 > k0:
                        pieces.append(_read_slice(r["path"], int(r["starts"][k0]), int(r["starts"][k1]),
                                                  schema))
                piece = pieces[0] if len(pieces) == 1 else pa.concat_tables(pieces)
                del pieces
                out, cell_c, trace_c, seq = self._encode(piece, pmap, cats, extra_cats, n_bins)
                del piece
                w.add(out, cell_c, trace_c)
                seq_parts.append(seq)
                del out
            w.end()
        if not order:
            w.begin(-1, None, "empty")
            w.write_empty(self._empty_tables(n_bins, cats))
            w.end()
        _partition_meta(tables_meta, w, layer_names)
        index = w.index()
        ig = root.create_group("index")
        for nm, data in index.items():
            _zarr_array(ig, nm, data, comp)
        seq = np.concatenate(seq_parts) if seq_parts else np.zeros(0, dtype=np.int64)
        sorted_already = bool(np.all(seq[1:] > seq[:-1])) if len(seq) else True
        if not sorted_already and self.keep_source_order:
            _zarr_array(ig, "source_row", seq.astype(np.int64), comp)
        _write_small_parts(root, root_path, tables_meta, level=self.level, bins=bins, **small)
        meta = {
            "n_spots": int(self.n), "n_bins": int(n_bins),
            "n_traces": int(len(np.unique(index["trace_codes"]))) if self.n else 0,
            "n_cells": int(len(np.unique(index["cell_codes"]))) if has_cells else 0,
            "n_row_groups": int(len(index["row_groups"]) - 1),
            "has_source_row": bool(not sorted_already and self.keep_source_order),
            "has_cell_id": has_cells, "n_partitions": len(w.partitions),
            "written_by": "uchrom.core.stream.ChromDataWriter",
        }
        _write_root_meta(root, meta, layout="2.1")

    def _encode(self, piece, pmap, cats, extra_cats, n_bins):
        """Spill rows → the stored tables (sorted by cell, trace, bin, input row)."""
        import pyarrow as pa

        has_cells = bool(self._has_cells)
        trace_c = cats["trace_id"].get_indexer(_col_values(piece, _TRACE))
        cell_c = (cats["cell_id"].get_indexer(_col_values(piece, _CELL)) if has_cells
                  else np.full(piece.num_rows, -1, dtype=np.int64))
        bin_id = pmap[piece.column(_PID).to_numpy()]
        seq = piece.column(_SEQ).to_numpy()
        order = np.lexsort((seq, bin_id, trace_c, cell_c))
        take = pa.array(order)
        cell_c, trace_c, bin_id, seq = cell_c[order], trace_c[order], bin_id[order], seq[order]
        spot_arrays = []
        spot_names = []
        for col in [c for c in self._column_order if c not in LOCI]:
            if col == BIN_ID:
                arr = pa.array(bin_id.astype(np.int32 if n_bins < 2 ** 31 else np.int64))
            elif col == "trace_id":
                arr = pa.array(trace_c.astype(_code_dtype(len(cats["trace_id"]))))
            elif col == "cell_id":
                arr = pa.array(cell_c.astype(_code_dtype(len(cats["cell_id"]))))
            elif col in extra_cats:
                vals = _col_values(piece, f"s:{col}")[order]
                arr = pa.array(extra_cats[col].get_indexer(vals).astype(_code_dtype(len(extra_cats[col]))))
            else:
                arr = piece.column(f"s:{col}").take(take).combine_chunks()
            spot_arrays.append(arr)
            spot_names.append(col)
        for c in ("x", "y", "z"):
            a = piece.column(c).take(take).to_numpy()
            spot_arrays.append(pa.array(a.astype(self.coord_dtype, copy=False)))
            spot_names.append(c)
        out = {"spots": pa.Table.from_arrays(spot_arrays, names=spot_names)}
        if self._track_cols:
            arrays = []
            for col in self._track_cols:
                if f"t:{col}" in extra_cats:
                    vals = _col_values(piece, f"t:{col}")[order]
                    idx = extra_cats[f"t:{col}"]
                    arrays.append(pa.array(idx.get_indexer(vals).astype(_code_dtype(len(idx)))))
                else:
                    arrays.append(piece.column(f"t:{col}").take(take).combine_chunks())
            out["spot_tracks"] = pa.Table.from_arrays(arrays, names=list(self._track_cols))
        for k in self._layer_keys:
            out[f"layers/{k}"] = pa.Table.from_arrays(
                [pa.array(piece.column(f"l:{k}:{c}").take(take).to_numpy().astype(self.coord_dtype, copy=False))
                 for c in ("x", "y", "z")], names=["x", "y", "z"])
        return out, cell_c, trace_c, seq

    def _empty_tables(self, n_bins, cats):
        import pyarrow as pa

        spot = {}
        for col in [c for c in (self._column_order or ["trace_id", BIN_ID]) if c not in LOCI]:
            if col == BIN_ID:
                spot[col] = pa.array(np.zeros(0, np.int32))
            elif col in ("trace_id", "cell_id"):
                spot[col] = pa.array(np.zeros(0, np.int16))
            else:
                spot[col] = pa.array([], type=pa.string())
        for c in ("x", "y", "z"):
            spot[c] = pa.array(np.zeros(0, self.coord_dtype))
        out = {"spots": pa.table(spot)}
        if self._track_cols:
            out["spot_tracks"] = pa.table({c: pa.array(np.zeros(0)) for c in self._track_cols})
        for k in self._layer_keys or []:
            out[f"layers/{k}"] = pa.table({c: pa.array(np.zeros(0, self.coord_dtype)) for c in "xyz"})
        return out


def _SAFE(name: str) -> bool:
    from .zarrcd import _SAFE_NAME
    return bool(_SAFE_NAME.match(name))


def _col_values(table, name: str) -> np.ndarray:
    col = table.column(name)
    try:
        return col.to_numpy()
    except Exception:  # pragma: no cover - chunked strings
        return np.asarray(col.to_pylist(), dtype=object)


def _read_slice(path: Path, a: int, b: int, schema):
    """Rows ``[a, b)`` of a spill run, cast to the unified schema."""
    import pyarrow.parquet as pq

    pf = pq.ParquetFile(str(path))
    g0, g1 = a // _SPILL_GROUP_ROWS, (b - 1) // _SPILL_GROUP_ROWS
    t = pf.read_row_groups(list(range(g0, g1 + 1)))
    t = t.slice(a - g0 * _SPILL_GROUP_ROWS, b - a)
    if schema is not None and t.schema != schema:
        t = t.cast(schema)
    return t


def _concat_frames(frames: List[pd.DataFrame]) -> Optional[pd.DataFrame]:
    if not frames:
        return None
    return frames[0] if len(frames) == 1 else pd.concat(frames)


__all__ = ["ChromDataWriter"]
