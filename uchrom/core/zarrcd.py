"""The ``.chromdata.zarr`` container (format 2.1): Zarr + Parquet.

A ChromData store is a Zarr v3 group whose large tables are Parquet files
(the SpatialData approach): Parquet for anything with rows (spots, tracks,
cells, traces, bins, intervals, points, result tables), Zarr for
n-dimensional arrays (``cellm``, ``binm``, the ``index/`` offsets, result
arrays) and JSON attributes for metadata (format version, ``uns``,
provenance, linked files).  Layout (2.1)::

    x.chromdata.zarr/
    ├── zarr.json                 root group; attrs["uchrom"] = format metadata
    ├── tables/                   zarr group (attrs: table metadata)
    │   ├── spots/chrom=<name>/part-0.parquet
    │   │                         one partition per chromosome, sorted by
    │   │                         (cell, trace, bin); bin_id, trace_id, cell_id
    │   │                         (integer codes), x, y, z, extra columns
    │   ├── spot_tracks/chrom=<name>/part-0.parquet   row-aligned with spots
    │   ├── layers/<key>/chrom=<name>/part-0.parquet  row-aligned x, y, z
    │   ├── categories/<table>.<column>.parquet   values of the coded columns
    │   ├── bins.parquet  bin_tracks.parquet  traces.parquet  cells.parquet
    │   ├── intervals/<key>.parquet
    │   └── points/<key>.parquet
    ├── index/                    zarr arrays: trace_offsets, trace_codes,
    │                             trace_cells, chrom_trace, cell_offsets,
    │                             cell_codes, cell_partition, row_groups,
    │                             partition_offsets, partition_groups,
    │                             partition_chrom, [source_row]
    ├── cellm/<key>  binm/<key>   zarr arrays (zstd)
    ├── results/<key>             zarr groups / arrays; attrs = provenance;
    │                             tables as <key>/table.parquet
    ├── uns/                      attrs (JSON) + arrays
    ├── contacts/                 attrs: linked .cool / .scool records
    └── links/                    attrs: linked .h5ad / .h5mu records

The spot-aligned tables are **partitioned by chromosome** (hive-style
``chrom=<name>`` directories; a trace observes one chromosome, so a
partition never splits a single-chromosome trace).  Rows are numbered
globally in partition order (chromosome category order), and within a
partition sorted by (cell, trace, bin): the stored order is
chrom › cell › trace › bin.  ``index/`` offsets use the global row
numbers; ``cell_offsets`` has one entry per (chromosome, cell) run, so a
cell is one slice per chromosome it has.  ``get_chrom`` reads one
partition, ``get_trace`` one slice of one partition.

Format 2.0 stores (one ``tables/spots.parquet`` etc., sorted by
(cell, trace, bin)) stay readable: they are read as a single partition.

``<name>.cdz`` is the same tree in one uncompressed (``ZIP_STORED``) zip
archive, so every member can be read in place (Parquet through a byte
range of the archive, Zarr through :class:`zarr.storage.ZipStore`).

The full specification is in ``uchrom/core/spec.md``; the design
rationale in ``docs/source/guide/chromdata_2_0_design.md`` (section 4).
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import struct
import tempfile
import threading
import uuid
import warnings
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

from .bins import BIN_ID, LOCI
from .intervals import IntervalTable
from .results import ResultRecord, ResultsStore, jsonable as _results_jsonable

PathLike = Union[str, Path]

ZARR_SUFFIX = ".chromdata.zarr"
ZIP_SUFFIX = ".cdz"
CONTAINER = "chromdata.zarr"
ZARR_FORMAT_VERSION = "2.1"
#: MINOR versions of the container this reader understands (2.0: one file per
#: spot-aligned table, sorted by cell › trace › bin; 2.1: partitioned by chromosome)
ZARR_LAYOUTS = {"2.0": "flat", "2.1": "partitioned"}

#: target rows per Parquet row group of the spot-aligned tables (row groups
#: end on cell boundaries within a chromosome partition)
DEFAULT_ROW_GROUP_ROWS = 16_384
#: decoded row groups kept by backed readers (LRU, bytes)
DEFAULT_CACHE_BYTES = 256 << 20
#: zstd level for Parquet and Zarr
DEFAULT_ZSTD_LEVEL = 3

_SPOT_TABLES = ("spots", "spot_tracks")
_COORD_COLUMNS = ("x", "y", "z")
_LINK_FAMILIES = {"linked_cool": "contacts", "linked_scool": "contacts",
                  "linked_anndata": "links", "linked_mudata": "links"}
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,120}$")


# ======================================================================
# Path dispatch
# ======================================================================

def container_kind(path: PathLike) -> Optional[str]:
    """``"zarr"`` / ``"cdz"`` / ``"h5cd"`` for a ChromData path, else ``None``.

    Suffix first (``.chromdata.zarr`` or any ``.zarr`` directory, ``.cdz``,
    ``.h5cd``); an existing path without a known suffix is sniffed
    (a directory with ``zarr.json``, a zip archive, an HDF5 file).
    """
    p = Path(path)
    name = p.name.lower()
    if name.endswith(".zarr"):
        return "zarr"
    if name.endswith(ZIP_SUFFIX):
        return "cdz"
    if name.endswith(".h5cd"):
        return "h5cd"
    if p.is_dir() and (p / "zarr.json").exists():
        return "zarr"
    if p.is_file():
        with open(p, "rb") as fh:
            magic = fh.read(8)
        if magic.startswith(b"PK\x03\x04"):
            return "cdz"
        if magic == b"\x89HDF\r\n\x1a\n":
            return "h5cd"
    return None


# ======================================================================
# Low-level helpers
# ======================================================================

def _zarr():
    import zarr  # noqa: F401  (zarr >= 3)
    return zarr


def _compressor(level: int):
    return _zarr().codecs.ZstdCodec(level=int(level))


def _safe_names(keys: Sequence[str]) -> Dict[str, str]:
    """On-disk node / file name of every key: the key itself when it is a
    portable name that is unique case-insensitively, else ``_<i>``."""
    out: Dict[str, str] = {}
    seen: set = set()
    for i, key in enumerate(keys):
        name = str(key)
        if not _SAFE_NAME.match(name) or name.lower() in seen or name.startswith("_"):
            name = f"_{i}"
        seen.add(name.lower())
        out[str(key)] = name
    return out


def _json_default(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, Path):
        return str(o)
    raise TypeError(type(o).__name__)


def _to_json_value(value: Any) -> Any:
    """``value`` as a JSON document for zarr attrs; tuples and non-numeric
    ndarrays carry a small type marker so they round-trip.  Raises
    ``TypeError`` for values that are not JSON-representable."""
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, tuple):
        return {"__tuple__": [_to_json_value(v) for v in value]}
    if isinstance(value, list):
        return [_to_json_value(v) for v in value]
    if isinstance(value, Mapping):
        out = {}
        for k, v in value.items():
            out[str(k)] = _to_json_value(v)
        return out
    if isinstance(value, np.ndarray):
        if value.dtype.kind in "USb" or value.dtype.kind in "iuf":
            return {"__ndarray__": value.tolist() if value.dtype.kind != "S" else
                    [b.decode("utf-8", "replace") for b in value.ravel().tolist()],
                    "dtype": value.dtype.str, "shape": list(value.shape)}
        raise TypeError(f"ndarray of dtype {value.dtype}")
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError(type(value).__name__)


def _from_json_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_from_json_value(v) for v in value]
    if isinstance(value, dict):
        if set(value) == {"__tuple__"}:
            return tuple(_from_json_value(v) for v in value["__tuple__"])
        if set(value) == {"__ndarray__", "dtype", "shape"}:
            dt = np.dtype(value["dtype"])
            flat = value["__ndarray__"]
            if dt.kind == "S":
                arr = np.array([s.encode("utf-8") for s in flat], dtype=dt)
            else:
                arr = np.array(flat, dtype=dt)
            return arr.reshape(value["shape"])
        return {k: _from_json_value(v) for k, v in value.items()}
    return value


def _contains_array(value: Any) -> bool:
    if isinstance(value, np.ndarray):
        return value.dtype.kind not in "USb" and value.ndim > 0 and value.size > 64
    if isinstance(value, Mapping):
        return any(_contains_array(v) for v in value.values())
    return False


# ----------------------------------------------------------------------
# Parquet: small (generic) tables
# ----------------------------------------------------------------------

def _frame_to_arrow(df: pd.DataFrame):
    """A DataFrame as an Arrow table with pandas metadata (index, dtypes,
    categories).  Object columns Arrow cannot type (mixed values) are stored
    as strings — the same rule as the HDF5 writer."""
    import pyarrow as pa

    df = df.copy(deep=False)
    df.columns = [str(c) for c in df.columns]
    for col in df.columns:
        if df[col].dtype == object:
            try:
                pa.array(df[col], from_pandas=True)
            except (pa.ArrowInvalid, pa.ArrowTypeError, TypeError, ValueError):
                df[col] = df[col].astype(str)
    idx = df.index
    trivial = isinstance(idx, pd.RangeIndex) and idx.start == 0 and idx.step == 1 and idx.name is None
    if not trivial and idx.dtype == object:
        try:
            pa.array(idx, from_pandas=True)
        except (pa.ArrowInvalid, pa.ArrowTypeError, TypeError, ValueError):
            df.index = idx.astype(str)
    return pa.Table.from_pandas(df, preserve_index=None if trivial or isinstance(idx, pd.RangeIndex) else True)


def _write_frame(df: pd.DataFrame, path: Path, level: int) -> None:
    import pyarrow.parquet as pq

    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(_frame_to_arrow(df), path, compression="zstd", compression_level=level)


def _arrow_to_frame(table) -> pd.DataFrame:
    return table.to_pandas()


# ======================================================================
# Writer
# ======================================================================

def _spot_keys(cd) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(cell codes, trace codes, bin_id) of every spot (cell codes = -1 when
    there is no ``cell_id`` column)."""
    spots = cd.spots
    n = len(spots)
    cell = (np.asarray(spots["cell_id"].cat.codes, dtype=np.int64)
            if "cell_id" in spots.columns else np.full(n, -1, dtype=np.int64))
    trace = np.asarray(spots["trace_id"].cat.codes, dtype=np.int64)
    bin_id = spots[BIN_ID].to_numpy().astype(np.int64)
    return cell, trace, bin_id


def sort_order(cell: np.ndarray, trace: np.ndarray, bin_id: np.ndarray,
               chrom: Optional[np.ndarray] = None) -> Optional[np.ndarray]:
    """Stable permutation sorting spots by ([chrom,] cell, trace, bin), or
    ``None`` when they already are sorted.  ``chrom`` (the chromosome code
    of every spot) is the format 2.1 partition key; without it the order is
    the 2.0 one."""
    n = len(bin_id)
    if n == 0:
        return None
    nc = int(cell.max()) + 2
    nt = int(trace.max()) + 2
    nb = int(bin_id.max()) + 1
    nch = int(chrom.max()) + 2 if chrom is not None else 1
    if nch * nc * nt * nb < 2 ** 62:
        key = ((cell + 1) * nt + (trace + 1)) * nb + bin_id
        if chrom is not None:
            key = key + (chrom + 1) * (nc * nt * nb)
        if np.all(key[1:] >= key[:-1]):
            return None
        return np.argsort(key, kind="stable")
    keys = (bin_id, trace, cell) if chrom is None else (bin_id, trace, cell, chrom)
    order = np.lexsort(keys)
    if np.array_equal(order, np.arange(n)):
        return None
    return order


def _segments(cell: np.ndarray, trace: np.ndarray,
              chrom: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
    """Offsets of the ([chrom,] cell, trace) runs and of the ([chrom,] cell)
    runs of sorted spots."""
    n = len(trace)
    if n == 0:
        return np.zeros(1, dtype=np.int64), np.zeros(1, dtype=np.int64)
    new_cell = np.r_[True, cell[1:] != cell[:-1]]
    if chrom is not None:
        new_cell |= np.r_[True, chrom[1:] != chrom[:-1]]
    new_seg = new_cell | np.r_[True, trace[1:] != trace[:-1]]
    seg = np.r_[np.flatnonzero(new_seg), n].astype(np.int64)
    cel = np.r_[np.flatnonzero(new_cell), n].astype(np.int64)
    return seg, cel


def _row_groups(bounds: np.ndarray, n: int, target: int) -> np.ndarray:
    """Row-group offsets: greedy runs of whole units (``bounds`` are the unit
    offsets, e.g. cells) of about ``target`` rows."""
    if n == 0:
        return np.zeros(1, dtype=np.int64)
    out = [0]
    for b in bounds[1:]:
        if b - out[-1] >= target:
            out.append(int(b))
    if out[-1] != n:
        out.append(int(n))
    return np.asarray(out, dtype=np.int64)


def _code_dtype(n_categories: int):
    return np.int16 if n_categories < 2 ** 15 else np.int32


class _SpotTableWriter:
    """Writes one spot-aligned table as Parquet, one row group per range."""

    def __init__(self, path: Path, level: int):
        self.path = path
        self.level = level
        self.writer = None

    def write(self, table) -> None:
        import pyarrow.parquet as pq

        if self.writer is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            dict_cols = [f.name for f in table.schema
                         if f.type.id in _INT_TYPE_IDS() or str(f.type) in ("string", "large_string")]
            self.writer = pq.ParquetWriter(
                self.path, table.schema, compression="zstd", compression_level=self.level,
                use_dictionary=dict_cols or False, write_statistics=True,
            )
        self.writer.write_table(table, row_group_size=max(1, table.num_rows))

    def close(self) -> None:
        if self.writer is not None:
            self.writer.close()


def _INT_TYPE_IDS():
    import pyarrow as pa
    return {pa.int8().id, pa.int16().id, pa.int32().id, pa.int64().id,
            pa.uint8().id, pa.uint16().id, pa.uint32().id, pa.uint64().id}


def _arrow_column(values, name: str):
    """One column as an Arrow array (zero-copy for plain numeric numpy)."""
    import pyarrow as pa

    if isinstance(values, pd.Series):
        s = values
    else:
        s = pd.Series(values)
    dt = s.dtype
    if isinstance(dt, np.dtype) and dt.kind in "biufM":
        return pa.array(s.to_numpy())
    try:
        return pa.array(s, from_pandas=True)
    except (pa.ArrowInvalid, pa.ArrowTypeError, TypeError, ValueError):
        return pa.array(s.astype(str), from_pandas=True)


def _spot_frame_columns(df: pd.DataFrame, table: str, cat_meta: dict, cat_dir: Path,
                        level: int) -> List[Tuple[str, Any]]:
    """Arrow arrays of every column of a spot-aligned frame, with categorical
    columns replaced by their integer codes (the categories are written to
    ``tables/categories/<table>.<col>.parquet``)."""
    import pyarrow as pa

    cols = []
    for i, col in enumerate(df.columns):
        s = df[col]
        name = str(col)
        if isinstance(s.dtype, pd.CategoricalDtype):
            cats = s.cat.categories
            codes = np.asarray(s.cat.codes).astype(_code_dtype(len(cats)))
            fname = f"{table}.{name}" if _SAFE_NAME.match(name) else f"{table}._{i}"
            _write_frame(pd.DataFrame({"value": np.asarray(cats)}) if len(cats) else
                         pd.DataFrame({"value": pd.Series([], dtype=cats.dtype if cats.dtype != object else object)}),
                         cat_dir / f"{fname}.parquet", level)
            cat_meta[name] = {"file": f"categories/{fname}.parquet", "ordered": bool(s.cat.ordered)}
            cols.append((name, pa.array(codes)))
        else:
            cols.append((name, _arrow_column(s, name)))
    return cols


def partition_dirs(names: Sequence[Optional[str]]) -> List[str]:
    """``chrom=<name>`` directory of every partition (portable names; others,
    and case-insensitive clashes, become ``chrom=_<i>``)."""
    safe = _safe_names([str(n) for n in names])
    return [f"chrom={safe[str(n)]}" for n in names]


class SpotPartitionWriter:
    """Writes the spot-aligned tables of a format 2.1 store, one chromosome
    partition at a time, and builds ``index/`` as it goes.

    Rows are handed over already sorted by (cell, trace, bin) within the
    partition, in any number of :meth:`add` calls.  Row groups end on unit
    boundaries (cell runs; (cell, trace) runs without ``cell_id``): a group is
    cut at the first unit boundary where it holds at least ``row_group_rows``
    rows — the same groups however the rows are split into calls, so the
    in-memory writer and the streaming writer produce identical files.
    """

    def __init__(self, tpath: Path, tables: Sequence[str], *, level: int, row_group_rows: int,
                 has_cells: bool, layer_names: Mapping[str, str]):
        self.tpath = Path(tpath)
        self.tables = list(tables)
        self.level = int(level)
        self.target = max(1, int(row_group_rows))
        self.has_cells = bool(has_cells)
        self.layer_names = dict(layer_names)
        self.partitions: List[Dict[str, Any]] = []
        self.n = 0
        self.rg = [0]
        self.part_offsets = [0]
        self.part_groups = [0]
        self.part_chrom: List[int] = []
        self._seg: List[np.ndarray] = []
        self._seg_trace: List[np.ndarray] = []
        self._seg_cell: List[np.ndarray] = []
        self._seg_chrom: List[np.ndarray] = []
        self._cel: List[np.ndarray] = []
        self._cel_code: List[np.ndarray] = []
        self._cel_part: List[np.ndarray] = []
        self._cur: Optional[Dict[str, Any]] = None

    def rel_path(self, name: str, pdir: str) -> str:
        if name in _SPOT_TABLES:
            return f"{name}/{pdir}/part-0.parquet"
        key = name.split("/", 1)[1]
        return f"layers/{self.layer_names[key]}/{pdir}/part-0.parquet"

    def begin(self, chrom_code: int, chrom_name: Optional[str], pdir: str) -> None:
        if self._cur is not None:
            raise RuntimeError("previous partition not ended")
        files = {name: self.rel_path(name, pdir) for name in self.tables}
        self._cur = {"chrom": chrom_name, "code": int(chrom_code), "dir": pdir, "n_rows": 0,
                     "files": files}
        self._writers = {name: _SpotTableWriter(self.tpath / rel, self.level) for name, rel in files.items()}
        self._pending: Dict[str, List[Any]] = {name: [] for name in self.tables}
        self._pend_n = 0
        self._pend_bounds: List[int] = []
        self._last: Optional[Tuple[int, int]] = None

    def write_empty(self, tables: Mapping[str, Any]) -> None:
        """Create the files of the current partition with the schema of
        ``tables`` and no rows (a store without spots)."""
        for name in self.tables:
            self._writers[name].write(tables[name].slice(0, 0))

    def add(self, tables: Mapping[str, Any], cell: np.ndarray, trace: np.ndarray) -> None:
        """Append sorted rows: ``tables[name]`` (Arrow tables of equal length)
        with the cell / trace codes of the rows (cell = -1 without cell_id)."""
        cur = self._cur
        m = len(trace)
        if m == 0:
            return
        cell = np.asarray(cell, dtype=np.int64)
        trace = np.asarray(trace, dtype=np.int64)
        new_cell = np.empty(m, dtype=bool)
        new_seg = np.empty(m, dtype=bool)
        if self._last is None:
            new_cell[0] = new_seg[0] = True
        else:
            new_cell[0] = cell[0] != self._last[0]
            new_seg[0] = new_cell[0] or trace[0] != self._last[1]
        new_cell[1:] = cell[1:] != cell[:-1]
        new_seg[1:] = new_cell[1:] | (trace[1:] != trace[:-1])
        s = np.flatnonzero(new_seg)
        self._seg.append(self.n + s)
        self._seg_trace.append(trace[s])
        self._seg_cell.append(cell[s])
        self._seg_chrom.append(np.full(len(s), cur["code"], dtype=np.int64))
        c = np.flatnonzero(new_cell)
        self._cel.append(self.n + c)
        self._cel_code.append(cell[c])
        self._cel_part.append(np.full(len(c), len(self.partitions), dtype=np.int64))
        unit = new_cell if self.has_cells else new_seg
        self._pend_bounds.extend((self._pend_n + np.flatnonzero(unit)).tolist())
        for name in self.tables:
            t = tables[name]
            if t.num_rows != m:
                raise ValueError(f"{name}: {t.num_rows} rows, expected {m}")
            self._pending[name].append(t)
        self._pend_n += m
        self.n += m
        cur["n_rows"] += m
        self._last = (int(cell[-1]), int(trace[-1]))
        self._cut(final=False)

    def _cut(self, final: bool) -> None:
        import pyarrow as pa

        while self._pend_n:
            cut = next((b for b in self._pend_bounds if b >= self.target), None)
            if cut is None:
                if not final:
                    return
                cut = self._pend_n
            for name in self.tables:
                parts = self._pending[name]
                t = parts[0] if len(parts) == 1 else pa.concat_tables(parts)
                self._writers[name].write(t.slice(0, cut))
                self._pending[name] = [t.slice(cut)] if cut < t.num_rows else []
            self._pend_bounds = [b - cut for b in self._pend_bounds if b > cut]
            self._pend_n -= cut
            self.rg.append(self.rg[-1] + cut)

    def end(self) -> Dict[str, Any]:
        self._cut(final=True)
        for w in self._writers.values():
            w.close()
        cur = self._cur
        self._cur = None
        self.partitions.append(cur)
        self.part_offsets.append(self.n)
        self.part_groups.append(len(self.rg) - 1)
        self.part_chrom.append(cur["code"])
        return cur

    def index(self) -> Dict[str, np.ndarray]:
        def cat(parts, dtype):
            return np.concatenate(parts).astype(dtype) if parts else np.zeros(0, dtype=dtype)

        return {
            "trace_offsets": np.r_[cat(self._seg, np.int64), self.n].astype(np.int64),
            "trace_codes": cat(self._seg_trace, np.int32),
            "trace_cells": cat(self._seg_cell, np.int32),
            "chrom_trace": cat(self._seg_chrom, np.int32),
            "cell_offsets": (np.r_[cat(self._cel, np.int64), self.n].astype(np.int64)
                             if self.has_cells else np.zeros(1, dtype=np.int64)),
            "cell_codes": cat(self._cel_code, np.int32) if self.has_cells else np.zeros(0, dtype=np.int32),
            "cell_partition": cat(self._cel_part, np.int32) if self.has_cells else np.zeros(0, dtype=np.int32),
            "row_groups": np.asarray(self.rg, dtype=np.int64),
            "partition_offsets": np.asarray(self.part_offsets, dtype=np.int64),
            "partition_groups": np.asarray(self.part_groups, dtype=np.int64),
            "partition_chrom": np.asarray(self.part_chrom, dtype=np.int32),
        }


def write_zarr(cd, path: PathLike, *, coord_dtype: Union[str, np.dtype] = "float64",
               row_group_rows: int = DEFAULT_ROW_GROUP_ROWS,
               compression_level: int = DEFAULT_ZSTD_LEVEL,
               keep_source_order: bool = True, _layout: str = "2.1") -> None:
    """Write ``cd`` as a ``.chromdata.zarr`` directory, or a ``.cdz`` zip
    when ``path`` ends with ``.cdz``.  See :meth:`ChromData.write`.

    ``_layout="2.0"`` writes the previous, unpartitioned layout (format 2.0;
    kept for compatibility tests)."""
    if _layout not in ZARR_LAYOUTS:
        raise ValueError(f"unknown layout {_layout!r}")
    path = Path(path)
    kind = "cdz" if path.name.lower().endswith(ZIP_SUFFIX) else "zarr"
    src = getattr(cd, "_backing_path", None)
    if src is not None and Path(src).resolve() == path.resolve():
        raise ValueError(f"cannot write a backed ChromData onto its own source {path}; "
                         f"write to another path or call to_memory() first")
    if path.exists():
        if path.is_dir() and not _is_chromdata_dir(path):
            raise FileExistsError(f"{path} exists and is not a ChromData store; refusing to replace it")
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{path.name}.", suffix=".tmp", dir=parent))
    try:
        if kind == "zarr":
            _write_tree(cd, tmp, coord_dtype=coord_dtype, row_group_rows=row_group_rows,
                        level=compression_level, keep_source_order=keep_source_order,
                        layout=_layout)
            if path.exists():
                old = parent / f".{path.name}.{uuid.uuid4().hex}.old"
                os.replace(path, old)
                os.replace(tmp, path)
                _rmtree(old)
            else:
                os.replace(tmp, path)
        else:
            tree = tmp / "tree"
            _write_tree(cd, tree, coord_dtype=coord_dtype, row_group_rows=row_group_rows,
                        level=compression_level, keep_source_order=keep_source_order,
                        layout=_layout)
            zpath = tmp / "store.cdz"
            _zip_tree(tree, zpath)
            os.replace(zpath, path)
    finally:
        if tmp.exists():
            _rmtree(tmp)


def _rmtree(p: Path) -> None:
    shutil.rmtree(p, ignore_errors=True)


def _is_chromdata_dir(path: Path) -> bool:
    meta = path / "zarr.json"
    if not meta.exists():
        return not any(path.iterdir())
    try:
        attrs = json.loads(meta.read_text()).get("attributes", {})
    except Exception:
        return False
    return "uchrom" in attrs


def _zip_tree(tree: Path, zpath: Path) -> None:
    """Zip a directory tree uncompressed (members are already compressed and
    must be readable in place)."""
    files = sorted(p for p in tree.rglob("*") if p.is_file())
    # zarr.json first, so a reader finds the root metadata quickly
    files.sort(key=lambda p: (p.relative_to(tree).as_posix() != "zarr.json",))
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
        for f in files:
            zf.write(f, f.relative_to(tree).as_posix())


def _uchrom_version() -> str:
    try:
        from uchrom import __version__ as v
    except Exception:  # pragma: no cover
        v = "unknown"
    return str(v)


def _zarr_array(group, name, data, comp) -> None:
    data = np.ascontiguousarray(data)
    chunks = ((max(1, min(data.shape[0], 1 << 20)),) + tuple(max(1, s) for s in data.shape[1:])
              if data.ndim else "auto")
    group.create_array(name, data=data, chunks=chunks, compressors=comp)


def _coord_arrays(coords, coord_dtype) -> List[Tuple[str, Any]]:
    import pyarrow as pa

    coords = np.asarray(coords)
    return [(c, pa.array(np.ascontiguousarray(coords[:, j]).astype(coord_dtype, copy=False)))
            for j, c in enumerate(_COORD_COLUMNS)]


def _write_tree(cd, root_path: Path, *, coord_dtype, row_group_rows: int, level: int,
                keep_source_order: bool, layout: str = "2.1") -> None:
    import pyarrow as pa

    zarr = _zarr()
    cd._check_bin_ids()
    coord_dtype = np.dtype(coord_dtype)
    if coord_dtype not in (np.dtype("float32"), np.dtype("float64")):
        raise ValueError("coord_dtype must be float32 or float64")
    comp = _compressor(level)
    root = zarr.open_group(str(root_path), mode="w", zarr_format=3)
    tpath = root_path / "tables"
    tables_meta: Dict[str, Any] = {}

    # -- spot order ---------------------------------------------------------
    n = int(cd.n_spots)
    cell, trace, bin_id = _spot_keys(cd)
    chrom_codes = np.asarray(cd.bins["chrom"].cat.codes, dtype=np.int64)
    spot_chrom = chrom_codes[bin_id] if n else np.zeros(0, dtype=np.int64)
    has_cells = "cell_id" in cd.spots.columns
    order = sort_order(cell, trace, bin_id, chrom=None if layout == "2.0" else spot_chrom)
    if order is not None:
        cell, trace, bin_id, spot_chrom = cell[order], trace[order], bin_id[order], spot_chrom[order]

    # -- spot-aligned columns (Arrow, in the object's row order) -------------
    spots = cd.spots.drop(columns=[c for c in LOCI if c in cd.spots.columns])
    spots[BIN_ID] = spots[BIN_ID].to_numpy().astype(np.int32 if cd.n_bins < 2 ** 31 else np.int64)
    cat_dir = tpath / "categories"
    spot_meta: Dict[str, Any] = {}
    columns: Dict[str, List[Tuple[str, Any]]] = {
        "spots": _spot_frame_columns(spots, "spots", spot_meta, cat_dir, level)
        + _coord_arrays(cd.coords, coord_dtype)}
    del spots
    tables_meta["spots"] = {"n_rows": n, "categorical": spot_meta,
                            "coords": list(_COORD_COLUMNS), "coord_dtype": coord_dtype.name,
                            "column_order": [str(c) for c in cd.spots.columns]}
    st = cd.spot_tracks
    if len(st.columns):
        st_meta: Dict[str, Any] = {}
        columns["spot_tracks"] = _spot_frame_columns(st, "spot_tracks", st_meta, cat_dir, level)
        tables_meta["spot_tracks"] = {"n_rows": n, "categorical": st_meta,
                                      "spot_view_order": cd._spot_view_order}
    layer_names = _safe_names(list(cd.layers))
    for key, a in cd.layers.items():
        columns[f"layers/{key}"] = _coord_arrays(a, coord_dtype)

    if layout == "2.0":
        index, extra = _write_spots_flat(columns, tpath, tables_meta, layer_names, n=n, cell=cell,
                                         trace=trace, spot_chrom=spot_chrom, order=order,
                                         has_cells=has_cells, row_group_rows=row_group_rows,
                                         level=level)
    else:
        index, extra = _write_spots_partitioned(
            columns, tpath, tables_meta, layer_names, cell=cell, trace=trace,
            spot_chrom=spot_chrom, order=order, has_cells=has_cells,
            chrom_names=[str(c) for c in cd.bins["chrom"].cat.categories],
            row_group_rows=row_group_rows, level=level)
    del columns
    ig = root.create_group("index")
    for name, data in index.items():
        _zarr_array(ig, name, data, comp)
    if order is not None and keep_source_order:
        _zarr_array(ig, "source_row", order.astype(np.int64), comp)

    _write_small_parts(root, root_path, tables_meta, level=level, bins=cd.bins,
                       bin_tracks=cd.bin_tracks, cells=cd.cells, traces=cd.traces,
                       intervals=cd.intervals, points=cd.points, cellm=cd.cellm, binm=cd.binm,
                       results=cd.results, uns=cd.uns)
    seg_trace = index["trace_codes"]
    meta = {
        "n_spots": n,
        "n_bins": int(cd.n_bins),
        "n_traces": int(len(np.unique(seg_trace))) if n else 0,
        "n_cells": int(len(np.unique(index["cell_codes"]))) if has_cells else 0,
        "n_row_groups": int(len(index["row_groups"]) - 1),
        "has_source_row": bool(order is not None and keep_source_order),
        "has_cell_id": bool(has_cells),
        **extra,
    }
    _write_root_meta(root, meta, layout=layout)


def _write_root_meta(root, meta: Dict[str, Any], *, layout: str = "2.1") -> None:
    version = layout
    full = {"format": CONTAINER, "format_version": version, "uchrom_version": _uchrom_version(),
            "spot_order": "chrom,cell,trace,bin" if layout != "2.0" else "cell,trace,bin",
            "layout": ZARR_LAYOUTS[layout], **meta}
    root.attrs.update({"uchrom": full, "uchrom_format_version": version,
                       "uchrom_version": full["uchrom_version"]})


def _write_spots_flat(columns, tpath: Path, tables_meta, layer_names, *, n, cell, trace, spot_chrom,
                      order, has_cells, row_group_rows, level):
    """The format 2.0 layout: one file per spot-aligned table."""
    import pyarrow as pa

    seg, cel = _segments(cell, trace)
    rg = _row_groups(cel if has_cells else seg, n, max(1, int(row_group_rows)))
    if n:
        starts = seg[:-1]
        seg_chrom = spot_chrom[starts].astype(np.int32)
        cmin = np.minimum.reduceat(spot_chrom, starts)
        cmax = np.maximum.reduceat(spot_chrom, starts)
        seg_chrom[cmin != cmax] = -1
        seg_trace = trace[starts].astype(np.int32)
        seg_cell = cell[starts].astype(np.int32)
        cell_codes = cell[cel[:-1]].astype(np.int32)
    else:
        seg_chrom = seg_trace = seg_cell = cell_codes = np.zeros(0, dtype=np.int32)
    tables_meta["spots"]["file"] = "spots.parquet"
    if "spot_tracks" in tables_meta:
        tables_meta["spot_tracks"]["file"] = "spot_tracks.parquet"
    tables_meta["layers"] = {}
    idx_arrow = pa.array(order) if order is not None else None
    for name, cols in columns.items():
        if name.startswith("layers/"):
            key = name.split("/", 1)[1]
            fname = f"layers/{layer_names[key]}.parquet"
            tables_meta["layers"][key] = fname
        else:
            fname = f"{name}.parquet"
        names = [c for c, _ in cols]
        arrays = [a for _, a in cols]
        w = _SpotTableWriter(tpath / fname, level)
        if n == 0:
            w.write(pa.Table.from_arrays([a.slice(0, 0) for a in arrays], names=names))
        for g in range(len(rg) - 1):
            a0, a1 = int(rg[g]), int(rg[g + 1])
            if idx_arrow is None:
                part = [a.slice(a0, a1 - a0) for a in arrays]
            else:
                part = [a.take(idx_arrow.slice(a0, a1 - a0)) for a in arrays]
            w.write(pa.Table.from_arrays(part, names=names))
        w.close()
    index = {"trace_offsets": seg, "trace_codes": seg_trace, "trace_cells": seg_cell,
             "chrom_trace": seg_chrom,
             "cell_offsets": cel if has_cells else np.zeros(1, dtype=np.int64),
             "cell_codes": cell_codes if has_cells else np.zeros(0, dtype=np.int32),
             "row_groups": rg}
    return index, {}


#: rows handed to the partition writer at a time by the in-memory writer
_WRITE_SLICE_ROWS = 1 << 20


def _write_spots_partitioned(columns, tpath: Path, tables_meta, layer_names, *, cell, trace,
                             spot_chrom, order, has_cells, chrom_names, row_group_rows, level):
    """The format 2.1 layout: one partition (directory) per chromosome."""
    import pyarrow as pa

    n = len(trace)
    names = list(columns)
    w = SpotPartitionWriter(tpath, names, level=level, row_group_rows=row_group_rows,
                            has_cells=has_cells, layer_names=layer_names)
    tables = {name: pa.Table.from_arrays([a for _, a in cols], names=[c for c, _ in cols])
              for name, cols in columns.items()}
    if n == 0:
        w.begin(-1, None, "empty")
        w.write_empty(tables)
        w.end()
    else:
        bounds = np.r_[0, np.flatnonzero(spot_chrom[1:] != spot_chrom[:-1]) + 1, n]
        codes = [int(spot_chrom[a]) for a in bounds[:-1]]
        dirs = partition_dirs([chrom_names[c] for c in codes])
        idx_arrow = pa.array(order) if order is not None else None
        for p, code in enumerate(codes):
            a, b = int(bounds[p]), int(bounds[p + 1])
            w.begin(code, chrom_names[code], dirs[p])
            for s0 in range(a, b, _WRITE_SLICE_ROWS):
                s1 = min(b, s0 + _WRITE_SLICE_ROWS)
                if idx_arrow is None:
                    part = {name: t.slice(s0, s1 - s0) for name, t in tables.items()}
                else:
                    take = idx_arrow.slice(s0, s1 - s0)
                    part = {name: t.take(take) for name, t in tables.items()}
                w.add(part, cell[s0:s1], trace[s0:s1])
                del part
            w.end()
    _partition_meta(tables_meta, w, layer_names)
    return w.index(), {"n_partitions": len(w.partitions)}


def _partition_meta(tables_meta: Dict[str, Any], w: "SpotPartitionWriter", layer_names) -> None:
    """Table metadata of a partitioned store (per-partition files)."""
    tables_meta["spots"]["layout"] = "partitioned"
    tables_meta["partitions"] = [
        {"chrom": p["chrom"], "code": p["code"], "dir": p["dir"], "n_rows": int(p["n_rows"]),
         "files": dict(p["files"])} for p in w.partitions]
    tables_meta["layers"] = {key: f"layers/{layer_names[key]}"
                             for key in (n.split("/", 1)[1] for n in w.tables if n.startswith("layers/"))}


def _write_small_parts(root, root_path: Path, tables_meta: Dict[str, Any], *, level: int, bins,
                       bin_tracks, cells, traces, intervals, points, cellm, binm, results,
                       uns) -> None:
    """Everything but the spot-aligned tables and ``index/``: bins, bin
    tracks, cells, traces, intervals, points, cellm / binm, results, uns and
    the linked-file records."""
    comp = _compressor(level)
    tpath = root_path / "tables"
    tables = root.create_group("tables")
    _write_frame(bins.reset_index(drop=True), tpath / "bins.parquet", level)
    tables_meta["bins"] = {"file": "bins.parquet", "n_rows": int(len(bins))}
    if len(bin_tracks.columns):
        _write_frame(bin_tracks.reset_index(drop=True), tpath / "bin_tracks.parquet", level)
        tables_meta["bin_tracks"] = {"file": "bin_tracks.parquet", "n_rows": int(len(bins))}
    for key, df in (("cells", cells), ("traces", traces)):
        if len(df.columns) or len(df):
            _write_frame(df, tpath / f"{key}.parquet", level)
            tables_meta[key] = {"file": f"{key}.parquet", "n_rows": int(len(df))}
    iv_names = _safe_names(list(intervals))
    iv_meta = {}
    for key, table in intervals.items():
        fname = f"intervals/{iv_names[key]}.parquet"
        _write_frame(pd.DataFrame(table), tpath / fname, level)
        iv_meta[str(key)] = {"file": fname, "kind": table.kind, "source_result": table.source_result}
    tables_meta["intervals"] = iv_meta
    pt_names = _safe_names(list(points))
    pt_meta = {}
    for key, df in points.items():
        if "/" in key or not key:
            raise ValueError(f"points key must be non-empty without '/': {key!r}")
        fname = f"points/{pt_names[key]}.parquet"
        _write_frame(df, tpath / fname, level)
        pt_meta[str(key)] = fname
    tables_meta["points"] = pt_meta
    tables.attrs.update({"tables": tables_meta})

    for gname, d in (("cellm", cellm), ("binm", binm)):
        g = root.create_group(gname)
        names = _safe_names(list(d))
        for key, a in d.items():
            a = np.asarray(a)
            if a.dtype == object:
                raise TypeError(f"{gname}[{key!r}]: object-dtype arrays cannot be stored")
            if a.dtype.kind in "US":
                raise TypeError(f"{gname}[{key!r}]: string arrays cannot be stored in {gname}")
            _zarr_array(g, names[key], a, comp)
        g.attrs.update({"keys": names})

    _write_results(root.create_group("results"), root_path / "results", results, intervals, level)
    uns_d = dict(uns)
    link_records: Dict[str, Dict[str, Any]] = {"contacts": {}, "links": {}}
    for fam, grp in _LINK_FAMILIES.items():
        if fam in uns_d:
            link_records[grp][fam] = uns_d.pop(fam)
    _write_uns(root.create_group("uns"), uns_d, level, order=[str(k) for k in uns])
    for grp, recs in link_records.items():
        root.create_group(grp).attrs.update(
            {"records": _to_json_value(recs), "relpaths": _link_relpaths(recs, root_path)})



def _link_relpaths(records: Dict[str, Any], root_path: Path) -> Dict[str, Any]:
    """Absolute linked paths that live next to the store, relative to the
    store's parent directory — used on read when the absolute path is gone
    (the folder was moved)."""
    out: Dict[str, Any] = {}
    parent = Path(root_path).resolve().parent
    for fam, raw in records.items():
        if not isinstance(raw, Mapping):
            continue
        recs = {"__single__": raw} if "path" in raw else raw
        for key, rec in recs.items():
            if isinstance(rec, Mapping) and isinstance(rec.get("path"), str):
                p = Path(rec["path"])
                if p.is_absolute():
                    try:
                        out.setdefault(fam, {})[key] = p.resolve().relative_to(parent).as_posix()
                    except ValueError:
                        pass
    return out


def _write_results(group, gpath: Path, results, intervals, level: int) -> None:
    records = results.records() if isinstance(results, ResultsStore) else None
    ref_of = {id(t): k for k, t in (intervals or {}).items()}
    names = _safe_names(list(results.keys()))
    for key, val in results.items():
        key = str(key)
        node = names[key]
        where = f"results[{key!r}]"
        if records is not None and records[key].kind == "intervals" and id(val) in ref_of:
            sub = group.create_group(node)
            attrs = {"_type": "ref", "_value_ref": f"intervals/{ref_of[id(val)]}"}
        else:
            sub, attrs = _write_value(group, gpath, node, val, where, level)
        if records is not None:
            rec = records[key]
            attrs.update({"_kind": rec.kind, "_function": rec.function, "_params": rec.params,
                          "_inputs": rec.inputs, "_uchrom_version": rec.uchrom_version,
                          "_created_utc": rec.created_utc})
        sub.attrs.update(_to_json_value(attrs))
    group.attrs.update({"keys": names})


def _write_value(group, gpath: Path, node: str, val: Any, where: str, level: int):
    """Write one results value under ``group/node``; returns (node, attrs)."""
    if isinstance(val, pd.DataFrame):
        sub = group.create_group(node)
        _write_frame(val, gpath / node / "table.parquet", level)
        return sub, {"_type": "dataframe", "_n_rows": int(len(val))}
    if isinstance(val, pd.Series):
        sub = group.create_group(node)
        _write_frame(val.to_frame(name="_value"), gpath / node / "table.parquet", level)
        return sub, {"_type": "series",
                     "_series_name": None if val.name is None else str(val.name)}
    if isinstance(val, Mapping):
        sub = group.create_group(node)
        names = _safe_names([str(k) for k in val.keys()])
        for k, v in val.items():
            k = str(k)
            child, attrs = _write_value(sub, gpath / node, names[k], v, f"{where}[{k!r}]", level)
            child.attrs.update(_to_json_value(attrs))
        return sub, {"_type": "dict", "_keys": names}
    if isinstance(val, np.ndarray):
        if val.dtype == object:
            raise TypeError(f"{where}: object-dtype arrays cannot be stored; convert to a "
                            f"numeric/string dtype or a list first.")
        if val.dtype.kind in "biuf" and val.ndim > 0:
            data = np.ascontiguousarray(val)
            chunks = tuple(max(1, s) for s in data.shape)
            a = group.create_array(node, data=data, chunks=chunks, compressors=_compressor(level))
            return a, {"_type": "ndarray"}
        sub = group.create_group(node)
        return sub, {"_type": "json", "value": _to_json_value(val)}
    if isinstance(val, np.generic):
        val = val.item()
    try:
        doc = _to_json_value(_results_jsonable(val) if not isinstance(val, tuple) else val)
        json.dumps(doc, allow_nan=True)
    except TypeError as exc:
        raise TypeError(
            f"{where}: cannot serialise value of type {type(val).__name__} to ChromData "
            f"results. Supported: DataFrame, Series, ndarray, dict, and JSON-compatible "
            f"scalars / lists."
        ) from exc
    sub = group.create_group(node)
    return sub, {"_type": "json", "value": doc}


def _write_uns(group, uns: Mapping, level: int, order: Optional[List[str]] = None) -> None:
    """uns → JSON attrs; values holding numeric arrays of more than 64
    elements become zarr sub-groups / arrays (attrs record the key order,
    ``order`` overriding it — e.g. to keep the place of the linked-file
    records, which are stored under ``contacts/`` / ``links/``)."""
    plain: Dict[str, Any] = {}
    nodes: Dict[str, str] = {}
    full_order = order
    order = []
    names = _safe_names([str(k) for k in uns.keys()])
    for key, val in uns.items():
        key = str(key)
        order.append(key)
        if _contains_array(val):
            node = names[key]
            if isinstance(val, np.ndarray):
                data = np.ascontiguousarray(val)
                group.create_array(node, data=data, chunks=tuple(max(1, s) for s in data.shape),
                                   compressors=_compressor(level))
            else:
                _write_uns(group.create_group(node), val, level)
            nodes[key] = node
            continue
        try:
            doc = _to_json_value(val)
            json.dumps(doc, allow_nan=True)
        except (TypeError, ValueError):
            doc = str(val)
        plain[key] = doc
    group.attrs.update({"values": plain, "nodes": nodes, "order": full_order or order})


# ======================================================================
# Reader: container access
# ======================================================================

class Container:
    """Read access to a ``.chromdata.zarr`` directory or a ``.cdz`` zip."""

    def __init__(self, path: PathLike):
        path = Path(path)
        kind = container_kind(path)
        if kind not in ("zarr", "cdz"):
            raise ValueError(f"{path} is not a .chromdata.zarr / .cdz store")
        if not path.exists():
            raise FileNotFoundError(path)
        zarr = _zarr()
        self.path = path
        self.kind = kind
        self._zip = None
        if kind == "zarr":
            store = zarr.storage.LocalStore(str(path), read_only=True)
        else:
            self._zip = zipfile.ZipFile(path, "r")
            self._members = {i.filename: i for i in self._zip.infolist()}
            store = zarr.storage.ZipStore(str(path), mode="r")
        self.store = store
        self.root = zarr.open_group(store=store, mode="r")
        attrs = dict(self.root.attrs)
        if "uchrom" not in attrs:
            raise ValueError(f"{path}: not a ChromData store (no 'uchrom' attributes)")
        self.meta = attrs["uchrom"]

    # -- files -----------------------------------------------------------

    def exists(self, rel: str) -> bool:
        if self._zip is not None:
            return rel in self._members
        return (self.path / rel).exists()

    def parquet(self, rel: str):
        """``pyarrow.parquet.ParquetFile`` of a member.

        Plain file reads, not memory maps: mapped pages would count as
        resident memory in backed mode.  A ``.cdz`` member (stored
        uncompressed) is read in place through a byte-range view of the
        archive."""
        import pyarrow as pa
        import pyarrow.parquet as pq

        if self._zip is None:
            return pq.ParquetFile(str(self.path / rel))
        info = self._members[rel]
        if info.compress_type != zipfile.ZIP_STORED:
            with self._zip.open(info) as fh:
                return pq.ParquetFile(pa.BufferReader(fh.read()))
        with open(self.path, "rb") as fh:
            fh.seek(info.header_offset)
            header = fh.read(30)
        name_len, extra_len = struct.unpack("<HH", header[26:30])
        offset = info.header_offset + 30 + name_len + extra_len
        return pq.ParquetFile(pa.PythonFile(_ByteRange(self.path, offset, info.file_size), mode="r"))

    def read_frame(self, rel: str) -> pd.DataFrame:
        return _arrow_to_frame(self.parquet(rel).read())

    def group_attrs(self, name: str) -> dict:
        try:
            return dict(self.root[name].attrs)
        except KeyError:
            return {}

    def array(self, name: str) -> np.ndarray:
        return np.asarray(self.root[name][...])

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()
        try:
            self.store.close()
        except Exception:
            pass


class _ByteRange(io.RawIOBase):
    """Read-only file object over ``[offset, offset + size)`` of a file
    (positional reads, so concurrent readers do not share a cursor)."""

    def __init__(self, path: Path, offset: int, size: int):
        super().__init__()
        self._fd = os.open(str(path), os.O_RDONLY)
        self._off = int(offset)
        self._size = int(size)
        self._pos = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, pos: int, whence: int = 0) -> int:
        base = {0: 0, 1: self._pos, 2: self._size}[whence]
        self._pos = max(0, min(self._size, base + int(pos)))
        return self._pos

    def readinto(self, b) -> int:
        n = min(len(b), self._size - self._pos)
        if n <= 0:
            return 0
        data = os.pread(self._fd, n, self._off + self._pos)
        b[:len(data)] = data
        self._pos += len(data)
        return len(data)

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            n = self._size - self._pos
        n = max(0, min(n, self._size - self._pos))
        data = os.pread(self._fd, n, self._off + self._pos) if n else b""
        self._pos += len(data)
        return data

    def close(self) -> None:
        if not self.closed:
            try:
                os.close(self._fd)
            finally:
                super().close()


def _read_categories(c: Container, meta: dict) -> Dict[str, Tuple[pd.Index, bool]]:
    out = {}
    for col, info in (meta or {}).items():
        vals = c.read_frame(f"tables/{info['file']}")["value"]
        out[col] = (pd.Index(vals.to_numpy() if vals.dtype != object else vals.to_numpy(dtype=object)),
                    bool(info.get("ordered", False)))
    return out


def read_small_parts(c: Container) -> Dict[str, Any]:
    """Everything that is loaded eagerly — also in backed mode."""
    tmeta = c.group_attrs("tables").get("tables", {})
    bins = c.read_frame("tables/bins.parquet")
    bins.index = pd.RangeIndex(len(bins), name=BIN_ID)
    if "chrom" not in bins.columns:
        bins = pd.DataFrame({"chrom": pd.Categorical([]), "start": pd.Series(dtype=np.int64),
                             "end": pd.Series(dtype=np.int64)}, index=pd.RangeIndex(0, name=BIN_ID))
    elif not isinstance(bins["chrom"].dtype, pd.CategoricalDtype):
        bins["chrom"] = bins["chrom"].astype(str).astype("category")
    parts: Dict[str, Any] = {"tables_meta": tmeta, "bins": bins}
    parts["bin_tracks"] = (c.read_frame("tables/bin_tracks.parquet")
                           if "bin_tracks" in tmeta else None)
    for key in ("cells", "traces"):
        parts[key] = c.read_frame(f"tables/{tmeta[key]['file']}") if key in tmeta else None
    intervals = {}
    for key, info in tmeta.get("intervals", {}).items():
        intervals[key] = IntervalTable.from_frame(
            c.read_frame(f"tables/{info['file']}"), kind=info.get("kind") or None,
            source_result=info.get("source_result") or None)
    parts["intervals"] = intervals
    parts["points"] = {k: c.read_frame(f"tables/{f}") for k, f in tmeta.get("points", {}).items()}
    for gname in ("cellm", "binm"):
        names = c.group_attrs(gname).get("keys", {})
        parts[gname] = {k: c.array(f"{gname}/{node}") for k, node in names.items()}
    parts["results"] = _read_results(c, intervals)
    uns = _read_uns(c, "uns")
    for grp in ("contacts", "links"):
        attrs = c.group_attrs(grp)
        recs = _from_json_value(attrs.get("records", {}))
        rel = attrs.get("relpaths", {})
        for fam, raw in recs.items():
            uns[fam] = _relocate_links(raw, rel.get(fam, {}), c.path)
    order = c.group_attrs("uns").get("order") or []
    uns = {**{k: uns[k] for k in order if k in uns}, **{k: v for k, v in uns.items() if k not in order}}
    parts["uns"] = uns
    index = {}
    for name in ("trace_offsets", "trace_codes", "trace_cells", "chrom_trace", "cell_offsets",
                 "cell_codes", "row_groups"):
        index[name] = c.array(f"index/{name}")
    partitioned = tmeta.get("spots", {}).get("layout") == "partitioned"
    if partitioned:
        for name in ("cell_partition", "partition_offsets", "partition_groups", "partition_chrom"):
            index[name] = c.array(f"index/{name}")
    else:  # format 2.0: the whole table is one partition (any chromosome)
        n_rows = int(tmeta.get("spots", {}).get("n_rows", c.meta.get("n_spots", 0)))
        index["cell_partition"] = np.zeros(len(index["cell_codes"]), dtype=np.int32)
        index["partition_offsets"] = np.array([0, n_rows], dtype=np.int64)
        index["partition_groups"] = np.array([0, len(index["row_groups"]) - 1], dtype=np.int64)
        index["partition_chrom"] = np.array([-1], dtype=np.int32)
    parts["partitioned"] = partitioned
    parts["index"] = index
    parts["spot_meta"] = tmeta.get("spots", {})
    parts["categories"] = {
        "spots": _read_categories(c, tmeta.get("spots", {}).get("categorical")),
        "spot_tracks": _read_categories(c, tmeta.get("spot_tracks", {}).get("categorical")),
    }
    return parts


def _relocate_links(raw: Any, relpaths: Dict[str, str], store_path: Path) -> Any:
    """Point absolute linked paths that no longer exist at the file next to
    the store (recorded relative path), so a moved project folder keeps its
    links."""
    if not relpaths or not isinstance(raw, Mapping):
        return raw
    single = "path" in raw
    recs = {"__single__": dict(raw)} if single else {k: dict(v) if isinstance(v, Mapping) else v
                                                     for k, v in raw.items()}
    parent = Path(store_path).resolve().parent
    for key, rel in relpaths.items():
        rec = recs.get(key)
        if isinstance(rec, dict) and isinstance(rec.get("path"), str) and not Path(rec["path"]).exists():
            cand = parent / rel
            if cand.exists():
                rec["path"] = str(cand)
    return recs["__single__"] if single else recs


def _read_results(c: Container, intervals: Dict[str, Any]) -> ResultsStore:
    store = ResultsStore()
    try:
        grp = c.root["results"]
    except KeyError:
        return store
    names = dict(grp.attrs).get("keys", {})
    for key, node in names.items():
        item = grp[node]
        attrs = _from_json_value(dict(item.attrs))
        if attrs.get("_type") == "ref":
            value = intervals[attrs["_value_ref"].split("/", 1)[1]]
        else:
            value = _read_value(c, f"results/{node}", item, attrs)
        kind = attrs.get("_kind")
        if not kind:
            store[key] = value
            continue
        store[key] = ResultRecord(
            kind=kind, value=value, params=attrs.get("_params") or {},
            function=attrs.get("_function") or None,
            uchrom_version=attrs.get("_uchrom_version") or "unknown",
            inputs=attrs.get("_inputs") or {}, created_utc=attrs.get("_created_utc") or "",
        )
    return store


def _read_value(c: Container, rel: str, item, attrs: dict) -> Any:
    kind = attrs.get("_type")
    if kind == "dataframe":
        return c.read_frame(f"{rel}/table.parquet")
    if kind == "series":
        s = c.read_frame(f"{rel}/table.parquet")["_value"]
        s.name = attrs.get("_series_name")
        return s
    if kind == "dict":
        out = {}
        for k, node in attrs.get("_keys", {}).items():
            child = item[node]
            out[k] = _read_value(c, f"{rel}/{node}", child, _from_json_value(dict(child.attrs)))
        return out
    if kind == "ndarray":
        return np.asarray(item[...])
    if kind == "json":
        return attrs.get("value")
    raise ValueError(f"{rel}: unknown result value type {kind!r}")


def _read_uns(c: Container, rel: str, group=None) -> dict:
    grp = group if group is not None else c.root[rel]
    attrs = dict(grp.attrs)
    values = attrs.get("values", {})
    nodes = attrs.get("nodes", {})
    out = {}
    for key in attrs.get("order", list(values) + list(nodes)):
        if key in nodes:
            item = grp[nodes[key]]
            if hasattr(item, "shape") and not hasattr(item, "group_keys"):
                out[key] = np.asarray(item[...])
            else:
                out[key] = _read_uns(c, f"{rel}/{nodes[key]}", item)
        elif key in values:
            out[key] = _from_json_value(values[key])
    return out


# ======================================================================
# Spot rows (shared by the in-memory reader and backed mode)
# ======================================================================

#: reads of at least this many rows from several pieces are combined into
#: single-chunk columns (so the pandas conversion is zero-copy)
_COMBINE_MIN_ROWS = 1 << 18


_IO_POOL = None


def _io_pool():
    """Shared thread pool for reading row groups of several partitions."""
    global _IO_POOL
    if _IO_POOL is None:
        from concurrent.futures import ThreadPoolExecutor
        _IO_POOL = ThreadPoolExecutor(max_workers=min(16, (os.cpu_count() or 4)),
                                      thread_name_prefix="uchrom-io")
    return _IO_POOL


class _ColumnFill:
    """One output column of known length filled piece by piece.

    Integer / float columns go into one buffer allocated from Arrow's pool
    up front (float nulls become NaN, as pandas would make them); other
    types — and an integer column that turns out to hold nulls — keep their
    chunks and are combined at the end."""

    def __init__(self, typ, n: int):
        import pyarrow as pa
        import pyarrow.types as pat

        self.typ = typ
        self.n = int(n)
        self.pos = 0
        self.chunks: Optional[List[Any]] = None
        self.is_float = pat.is_floating(typ)
        if pat.is_integer(typ) or self.is_float:
            self.dt = np.dtype(typ.to_pandas_dtype())
            self.buf = pa.allocate_buffer(max(1, self.n * self.dt.itemsize))
            self.arr = np.frombuffer(self.buf, dtype=self.dt, count=self.n)
        else:
            self.buf = None
            self.chunks = []

    def add(self, column) -> None:
        import pyarrow as pa

        for piece in column.chunks:
            m = len(piece)
            if self.chunks is None and piece.null_count and not self.is_float:
                # integers with nulls: keep Arrow semantics (chunks)
                self.chunks = [pa.array(self.arr[:self.pos], type=self.typ)] if self.pos else []
                self.buf = self.arr = None
            if self.chunks is not None:
                self.chunks.append(piece)
            elif m:
                self.arr[self.pos:self.pos + m] = piece.to_numpy(zero_copy_only=False)
            self.pos += m

    def finish(self):
        import pyarrow as pa

        if self.chunks is not None:
            return pa.chunked_array(self.chunks, type=self.typ).combine_chunks()
        return pa.Array.from_buffers(self.typ, self.n, [None, self.buf])


def combine_tables(tables: Sequence[Any], threads: int = 8):
    """Concatenate Arrow tables of one schema into a table whose columns are
    **single chunks** (``pyarrow.concat_tables`` keeps one chunk per input).

    ``Table.to_pandas`` is zero-copy only for single-chunk numeric columns;
    with several chunks it copies every column, doubling peak memory on a
    full read.  Numeric null-free columns are copied into one preallocated
    buffer per column (several columns at a time, in threads); the inputs
    release each column as soon as it is copied, so the peak stays at about
    the table plus a few columns.  A list argument is emptied (the
    inputs are consumed).
    """
    import pyarrow as pa
    import pyarrow.types as pat
    from concurrent.futures import ThreadPoolExecutor

    src = tables
    tables = [t for t in src if t is not None]
    if isinstance(src, list):
        src.clear()        # the caller's list must not keep the inputs alive
    if not tables:
        raise ValueError("no tables")
    if len(tables) == 1:
        return tables[0]
    names = tables[0].column_names
    schema = tables[0].schema
    n = sum(t.num_rows for t in tables)
    out: List[Any] = [None] * len(names)

    def one(i, chunks):
        typ = schema.field(i).type
        fixed = (pat.is_integer(typ) or pat.is_floating(typ)) and not any(c.null_count for c in chunks)
        if fixed:
            # allocate from Arrow's pool: it reuses the memory the inputs
            # release (a numpy allocation would add to it)
            dt = np.dtype(typ.to_pandas_dtype())
            buf = pa.allocate_buffer(max(1, n * dt.itemsize))
            arr = np.frombuffer(buf, dtype=dt, count=n)
            pos = 0
            for c in chunks:
                for piece in c.chunks:
                    m = len(piece)
                    if m:
                        arr[pos:pos + m] = piece.to_numpy(zero_copy_only=False)
                    pos += m
            return pa.Array.from_buffers(typ, n, [None, buf])
        return pa.chunked_array([p for c in chunks for p in c.chunks], type=typ).combine_chunks()

    step = max(1, int(threads))
    with ThreadPoolExecutor(max_workers=step) as ex:
        for g0 in range(0, len(names), step):
            ids = list(range(g0, min(len(names), g0 + step)))
            jobs = [ex.submit(one, i, [t.column(k) for t in tables])
                    for k, i in enumerate(ids)]
            for i, job in zip(ids, jobs):
                out[i] = job.result()
            # release the copied columns of the inputs
            tables = [t.drop_columns(list(t.column_names[:len(ids)])) for t in tables]
    return pa.Table.from_arrays(out, schema=schema)


class SpotRows:
    """Row access to the spot-aligned Parquet tables of a store.

    Rows are numbered globally: partition after partition (format 2.1: one
    per chromosome; format 2.0: a single one).  Every spot-aligned table has
    the same row groups (``index/row_groups``, global offsets;
    ``index/partition_groups`` gives each partition's first group), so a
    row range maps onto the same groups in each table.

    Row groups a request covers completely are read in one call and not
    cached (``get_chrom`` reads a whole partition); partially covered ones go
    through a small LRU cache of decoded groups bounded in bytes
    (``cache_bytes``), from which small selections are copied so a group can
    be freed.
    """

    def __init__(self, c: Container, parts: Dict[str, Any], cache_bytes: int = DEFAULT_CACHE_BYTES):
        from collections import OrderedDict

        self.c = c
        tmeta = parts["tables_meta"]
        idx = parts["index"]
        self.n = int(tmeta.get("spots", {}).get("n_rows", c.meta.get("n_spots", 0)))
        self.rg = np.asarray(idx["row_groups"], dtype=np.int64)
        self.part_offsets = np.asarray(idx["partition_offsets"], dtype=np.int64)
        self.part_groups = np.asarray(idx["partition_groups"], dtype=np.int64)
        self.part_chrom = np.asarray(idx["partition_chrom"], dtype=np.int64)
        self.partitioned = bool(parts.get("partitioned"))
        self.cats = parts["categories"]
        self.spot_meta = tmeta.get("spots", {})
        if self.partitioned:
            self.part_files = [{name: f"tables/{rel}" for name, rel in p["files"].items()}
                               for p in tmeta["partitions"]]
        else:
            files = {"spots": "tables/spots.parquet"}
            if "spot_tracks" in tmeta:
                files["spot_tracks"] = "tables/spot_tracks.parquet"
            for key, f in tmeta.get("layers", {}).items():
                files[f"layers/{key}"] = f"tables/{f}"
            self.part_files = [files]
        #: table names ("spots", "spot_tracks", "layers/<key>") → True
        self.files: Dict[str, bool] = {name: True for name in self.part_files[0]}
        n_groups = len(self.rg) - 1
        self.group_part = np.repeat(np.arange(len(self.part_files), dtype=np.int64),
                                    np.diff(self.part_groups)) if n_groups else np.zeros(0, np.int64)
        self._pf: Dict[Tuple[str, int], Any] = {}
        self._flocks: Dict[Tuple[str, int], Any] = {}
        self._cache: "OrderedDict[Tuple[str, int, Tuple[str, ...]], Any]" = OrderedDict()
        self._cache_used = 0
        self.cache_bytes = int(cache_bytes)
        # one reader at a time: ParquetFile objects and the cache are shared
        # (the web server calls in from a thread pool)
        self._lock = threading.RLock()
        self.coord_dtype = np.dtype(self.spot_meta.get("coord_dtype", "float64"))

    @property
    def n_partitions(self) -> int:
        return len(self.part_files)

    def pf(self, name: str, part: int = 0):
        with self._lock:
            key = (name, int(part))
            if key not in self._pf:
                self._pf[key] = self.c.parquet(self.part_files[int(part)][name])
            return self._pf[key]

    def columns(self, name: str) -> List[str]:
        return list(self.pf(name).schema_arrow.names)

    def empty(self, name: str, columns: Optional[Sequence[str]] = None):
        t = self.pf(name).schema_arrow.empty_table()
        return t.select(list(columns)) if columns is not None else t

    def partition_range(self, part: int) -> Tuple[int, int]:
        return int(self.part_offsets[part]), int(self.part_offsets[part + 1])

    # -- raw Arrow access --------------------------------------------------

    def read_all(self, name: str, columns: Optional[Sequence[str]] = None):
        """The whole table (all partitions), with single-chunk columns.

        Partitions are decoded one at a time and copied into preallocated
        buffers, so the peak is the table plus one partition (see
        :class:`_ColumnFill`), and ``to_pandas`` is zero-copy."""
        import pyarrow as pa

        cols = list(columns) if columns is not None else None
        with self._lock:
            if self.n_partitions == 1:
                return self.pf(name, 0).read(columns=cols, use_threads=True)
            fills = None
            schema = None
            for p in range(self.n_partitions):
                t = self.pf(name, p).read(columns=cols, use_threads=True)
                if fills is None:
                    schema = t.schema
                    fills = [_ColumnFill(f.type, self.n) for f in schema]
                for i, f in enumerate(fills):
                    f.add(t.column(i))
                del t
            return pa.Table.from_arrays([f.finish() for f in fills], schema=schema)

    def _local(self, g: int) -> Tuple[int, int]:
        p = int(self.group_part[g])
        return p, g - int(self.part_groups[p])

    def _file_lock(self, name: str, part: int):
        with self._lock:
            key = (name, int(part))
            lk = self._flocks.get(key)
            if lk is None:
                lk = self._flocks[key] = threading.Lock()
            return lk

    def _group(self, name: str, g: int, columns: Tuple[str, ...]):
        key = (name, g, columns)
        with self._lock:
            t = self._cache.get(key)
            if t is not None:
                self._cache.move_to_end(key)
                return t
        p, lg = self._local(g)
        pf = self.pf(name, p)
        with self._file_lock(name, p):
            t = pf.read_row_group(lg, columns=list(columns), use_threads=True)
        size = int(t.nbytes)
        with self._lock:
            if size <= self.cache_bytes and key not in self._cache:
                while self._cache and self._cache_used + size > self.cache_bytes:
                    _, old = self._cache.popitem(last=False)
                    self._cache_used -= int(old.nbytes)
                self._cache[key] = t
                self._cache_used += size
        return t

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()
            self._cache_used = 0

    def read_ranges(self, name: str, ranges: Sequence[Tuple[int, int]],
                    columns: Optional[Sequence[str]] = None):
        """Rows of the given ``[start, stop)`` ranges (ascending, disjoint)
        of one table, as one Arrow table.

        Consecutive row groups a range covers completely are read in one
        call (not cached); partially covered groups go through the cache.
        Different partitions are read in parallel threads (a cell touches
        one row group per chromosome)."""
        import pyarrow as pa

        cols = tuple(columns) if columns is not None else tuple(self.columns(name))
        per_group: Dict[int, List[Tuple[int, int]]] = {}
        for a, b in ranges:
            a, b = int(a), int(b)
            if b <= a:
                continue
            g0 = int(np.searchsorted(self.rg, a, side="right") - 1)
            g1 = int(np.searchsorted(self.rg, b, side="left"))
            for g in range(g0, g1):
                lo, hi = max(a, int(self.rg[g])), min(b, int(self.rg[g + 1]))
                per_group.setdefault(g, []).append((lo - int(self.rg[g]), hi - int(self.rg[g])))
        # plan: ("run", [g, ...]) of consecutive full groups of one partition,
        # or ("part", g, local ranges); tasks keep the output order
        tasks: List[Tuple] = []
        for g in sorted(per_group):
            local = per_group[g]
            size = int(self.rg[g + 1] - self.rg[g])
            kept = sum(hi - lo for lo, hi in local)
            if kept == size:
                last = tasks[-1] if tasks else None
                if (last is not None and last[0] == "run" and g == last[1][-1] + 1
                        and self.group_part[g] == self.group_part[last[1][-1]]):
                    last[1].append(g)
                else:
                    tasks.append(("run", [g]))
            else:
                tasks.append(("part", g, local))

        def do(task):
            if task[0] == "run":
                gs = task[1]
                p, lg0 = self._local(gs[0])
                pf = self.pf(name, p)
                with self._file_lock(name, p):
                    return pf.read_row_groups(list(range(lg0, lg0 + len(gs))), columns=list(cols),
                                              use_threads=True)
            _, g, local = task
            t = self._group(name, g, cols)
            kept = sum(hi - lo for lo, hi in local)
            if len(local) == 1 and kept * 2 >= t.num_rows:
                return t.slice(local[0][0], kept)
            # copy small selections, so the decoded group can be freed
            idx = np.concatenate([np.arange(lo, hi) for lo, hi in local])
            return t.take(pa.array(idx))

        def part_of(task):
            return int(self.group_part[task[1][0] if task[0] == "run" else task[1]])

        by_part: Dict[int, List[int]] = {}
        for i, task in enumerate(tasks):
            by_part.setdefault(part_of(task), []).append(i)
        pieces: List[Any] = [None] * len(tasks)
        if len(by_part) > 1:
            def work(ids):
                for i in ids:
                    pieces[i] = do(tasks[i])
            list(_io_pool().map(work, by_part.values()))
        else:
            for i, task in enumerate(tasks):
                pieces[i] = do(task)
        if not pieces:
            return self.empty(name, cols)
        if len(pieces) == 1:
            return pieces[0]
        if sum(p.num_rows for p in pieces) >= _COMBINE_MIN_ROWS:
            return combine_tables(pieces)
        return pa.concat_tables(pieces)

    def take(self, name: str, rows: np.ndarray, columns: Optional[Sequence[str]] = None):
        """Arbitrary rows (any order) of one table."""
        import pyarrow as pa

        rows = np.asarray(rows, dtype=np.int64)
        cols = tuple(columns) if columns is not None else tuple(self.columns(name))
        if len(rows) == 0:
            return self.empty(name, cols)
        order = np.argsort(rows, kind="stable")
        srt = rows[order]
        g = np.searchsorted(self.rg, srt, side="right") - 1
        pieces = []
        for gi in np.unique(g):
            sel = srt[g == gi] - int(self.rg[gi])
            pieces.append(self._group(name, int(gi), cols).take(pa.array(sel)))
        t = pa.concat_tables(pieces)
        inv = np.empty_like(order)
        inv[order] = np.arange(len(order))
        return t.take(pa.array(inv))

    # -- conversion --------------------------------------------------------
    def to_frame(self, name: str, table) -> pd.DataFrame:
        """Arrow table of a spot-aligned file → DataFrame (codes → categoricals)."""
        cats = self.cats.get(name, {})
        names = list(table.column_names)
        coded = [c for c in names if c in cats]
        codes = {c: table.column(c).to_numpy() for c in coded}
        plain = table.drop_columns(coded) if coded else table
        # Arrow's own conversion: multi-threaded, one block per column
        df = plain.to_pandas(split_blocks=True, self_destruct=True, use_threads=True) \
            if plain.num_columns else pd.DataFrame(index=pd.RangeIndex(table.num_rows))
        del plain, table
        for c in coded:
            categories, ordered = cats[c]
            if _FROM_CODES_VALIDATE:
                df[c] = pd.Categorical.from_codes(codes[c], categories=categories,
                                                  ordered=ordered, validate=False)
            else:  # pragma: no cover - pandas < 2.1
                df[c] = pd.Categorical.from_codes(codes[c], categories=categories, ordered=ordered)
        if list(df.columns) != names:
            df = df[names]
        df.index = pd.RangeIndex(len(df))
        return df

    def coords_of(self, table, columns=_COORD_COLUMNS) -> np.ndarray:
        out = np.empty((table.num_rows, 3), dtype=np.float64)
        for j, c in enumerate(columns):
            out[:, j] = table.column(c).to_numpy()
        return out


def _is_numeric(t) -> bool:
    import pyarrow.types as pat
    return pat.is_integer(t) or pat.is_floating(t) or pat.is_boolean(t)


try:
    pd.Categorical.from_codes([0], categories=["a"], validate=False)
    _FROM_CODES_VALIDATE = True
except TypeError:  # pragma: no cover - pandas < 2.1
    _FROM_CODES_VALIDATE = False


__all__ = [
    "CONTAINER", "Container", "DEFAULT_CACHE_BYTES", "DEFAULT_ROW_GROUP_ROWS", "DEFAULT_ZSTD_LEVEL",
    "SpotPartitionWriter", "SpotRows", "ZARR_FORMAT_VERSION", "ZARR_LAYOUTS", "ZARR_SUFFIX",
    "ZIP_SUFFIX", "container_kind", "partition_dirs", "read_small_parts", "sort_order", "write_zarr",
]
