"""Legacy HDF5 ``.h5cd`` container (ChromData format 1.x / 2.0) — conversion only.

``.h5cd`` is no longer a ChromData format: ``ChromData.read`` / ``write`` refuse it.  This
module keeps the reader so old files can be converted once
(:func:`uchrom.io.upgrade_h5cd`, ``python -m uchrom.io.upgrade old.h5cd``) and the writer
for the format benchmarks that measure it as a baseline (uchrom-reproducibility ``benchmarks/store``).  It is
private: nothing else in ``uchrom`` uses it.

HDF5 layout (format 2.0)::

    data.h5cd
    ├── @uchrom_format_version  = "2.0"
    ├── @uchrom_version         = "0.2.0"
    ├── @spot_order             = "unsorted"
    ├── bins/                group — chrom (codes + categories), start, end, …
    ├── coords               (n_spots, 3) float64
    ├── spots/               group — bin_id (int32), trace_id / cell_id as
    │                         {codes, categories}, extra columns
    ├── tracks/              group — bin-level tracks, n_bins rows
    ├── spot_tracks/         group — spot-level tracks, n_spots rows
    ├── binm/                group of (n_bins, ...) ndarrays per key
    ├── intervals/<key>/     DataFrame group, @_kind, @_source_result
    ├── cells/               group
    ├── traces/              group
    ├── cellm/               group of (n_cells, ...) ndarrays per key
    ├── layers/              group of (n_spots, 3) ndarrays per key
    ├── points/              optional group of DataFrames (non-genomic
    │                         3-D points: x, y, z, cell_id, …)
    ├── results/             group — typed entries (``_type`` attr):
    │                         DataFrame / Series / nested dict as
    │                         sub-groups, ndarrays as datasets,
    │                         scalars & lists as JSON string datasets;
    │                         provenance attrs (``_kind``, ``_function``,
    │                         ``_params``, …) on each entry (1.4)
    └── uns/                 nested group — scalars as attrs,
                              dicts as sub-groups
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Union

import numpy as np
import pandas as pd

from chromdata.cdata import (BIN_ID, LOCI, ChromData, _SERIES_COLUMN, _UNS_JSON_PREFIX,
                               _metadata_jsonable, _nonempty, _parse_version)
from chromdata.intervals import IntervalTable
from chromdata.results import ResultRecord, ResultsStore, jsonable as _results_jsonable

PathLike = Union[str, Path]

# ``.h5cd`` on-disk format version. Semantics (MAJOR.MINOR):
#   MAJOR bump  — breaking change: a reader for the old MAJOR cannot read the
#                 new file without running a migration.
#   MINOR bump  — additive/backwards-compatible change (e.g. a new optional
#                 group or attribute).  Older readers should ignore unknown
#                 fields and keep working.
#
# 1.1: per-DataFrame ``_index`` dataset + ``_index_name`` attr.  Files with
#      a non-trivial DataFrame index (e.g. ``cells`` keyed by ``cell_id``)
#      previously lost that index on round-trip; 1.1 preserves it.  1.0
#      readers ignore the extra dataset and recover the old behaviour.
# 1.2: typed ``results`` entries (``_type`` attr: dataframe / series / dict /
#      json).  Nested dicts, Series, scalars and lists now round-trip; before
#      1.2 anything other than a DataFrame or ndarray was silently dropped on
#      write.  1.1 readers still see DataFrames and arrays unchanged.
# 1.3: optional ``points/`` group — named DataFrames of non-genomic 3-D
#      points (x, y, z + columns such as cell_id, gene) in the coords frame,
#      e.g. nascent RNA spots.  Older readers ignore the group.
# 1.4: ``results`` entries carry provenance (``cd.results`` is a
#      :class:`~chromdata.results.ResultsStore`).  Each top-level item of
#      ``results/`` gains attrs ``_kind``, ``_function``, ``_params`` (JSON),
#      ``_inputs`` (JSON), ``_uchrom_version`` and ``_created_utc``.  The
#      value itself is stored in place exactly as in 1.2/1.3, so older
#      readers still read the value and ignore the extra attrs.
#
# 2.0: the ``bins`` locus axis (MAJOR bump; ChromData 2.0 roadmap step 3).
#      ``bins/`` (index = bin_id), bin-level ``tracks/`` (n_bins rows),
#      ``binm/``, spot-level ``spot_tracks/``, typed ``intervals/<key>``
#      (``@kind``, ``@source_result``).  ``spots/`` stores ``bin_id``
#      (int32) instead of chrom/start/end, which are derived from ``bins``
#      on read.  Categorical columns are stored as ``{codes, categories}``
#      groups.  A ``results/<key>`` whose value is ``intervals/<key>`` holds
#      only its provenance attrs plus ``_value_ref``.  1.x files are
#      upgraded on read (see :func:`_read_v1`) and by
#      :func:`uchrom.io.upgrade_h5cd`.
FORMAT_VERSION = "2.0"
_SUPPORTED_MAJORS = (1, 2)


def read_h5cd(path: PathLike) -> ChromData:
    """Read a ``.h5cd`` file (format 1.x or 2.0) into memory.

    Dispatches on ``f.attrs['uchrom_format_version']``: MAJOR 2 → :func:`_read_v2`, MAJOR 1
    → :func:`_read_v1`, which upgrades the file to the 2.0 model (bins derived from the spot
    loci; the spot-aligned 1.x ``tracks`` split into ``bin_tracks`` / ``spot_tracks``).
    Unversioned files are read as 1.0 with a warning; an unknown MAJOR raises.
    """
    import h5py

    path = Path(path)
    with h5py.File(path, "r") as f:
        version_str = f.attrs.get("uchrom_format_version")
        if version_str is None:
            warnings.warn(
                f"{path}: missing uchrom_format_version attr; "
                f"assuming legacy 1.0 layout.",
                stacklevel=2,
            )
            version_str = "1.0"
        elif isinstance(version_str, bytes):
            version_str = version_str.decode("utf-8")

        major, minor = _parse_version(version_str)
        if major not in _SUPPORTED_MAJORS:
            raise ValueError(
                f"{path}: format version {version_str} has incompatible "
                f"MAJOR with this uchrom (supports MAJOR in "
                f"{list(_SUPPORTED_MAJORS)}). Upgrade uchrom or convert the file."
            )
        cur_major, cur_minor = _parse_version(FORMAT_VERSION)
        if major == cur_major and minor > cur_minor:
            warnings.warn(
                f"{path}: written with format version {version_str} "
                f"(reader supports up to {FORMAT_VERSION}). "
                f"Forward-compatible — unknown fields will be ignored.",
                stacklevel=2,
            )

        # 1.x files are upgraded in memory (bins derived from the spot
        # loci, spot-aligned tracks split); uchrom.io.upgrade_h5cd
        # rewrites them as 2.0 on disk.
        cd = _read_v1(ChromData, f) if major == 1 else _read_v2(ChromData, f)
    cd._source_path = path
    return cd


def write_h5cd(cd: ChromData, path: PathLike, *, compression: Optional[str] = "gzip",
               compression_opts: Optional[int] = 4, compress_floats: bool = False) -> None:
    """Write ``cd`` as a ``.h5cd`` 2.0 file (for format benchmarks; not a ChromData format).

    ``compression`` (``"gzip"``, ``"lzf"`` or ``None``) applies to the integer / string
    datasets of 4,096 elements or more; ``compress_floats`` also compresses ``coords``,
    ``layers`` and float tracks.
    """
    import h5py

    try:
        from uchrom import __version__ as _uchrom_version
    except Exception:
        _uchrom_version = "unknown"
    path = Path(path)
    cd._check_bin_ids()
    if compression not in (None, "gzip", "lzf"):
        raise ValueError("compression must be 'gzip', 'lzf' or None")
    _WRITE_OPTS.update(compression=compression, compress_floats=bool(compress_floats),
                       compression_opts=compression_opts if compression == "gzip" else None)
    try:
        _write_h5(cd, h5py, path, _uchrom_version)
    finally:
        _WRITE_OPTS.update(compression=None, compression_opts=None, compress_floats=False)


def _write_h5(cd: ChromData, h5py, path: Path, _uchrom_version: str) -> None:
    spots = cd.spots.drop(columns=[c for c in LOCI if c in cd.spots.columns])
    spots[BIN_ID] = spots[BIN_ID].to_numpy().astype(
        np.int32 if cd.n_bins < 2 ** 31 else np.int64)
    with h5py.File(path, "w") as f:
        f.attrs["uchrom_format_version"] = FORMAT_VERSION
        f.attrs["uchrom_version"] = _uchrom_version
        f.attrs["spot_order"] = "unsorted"
        _write_dataframe(f, "bins", cd._bins.reset_index(drop=True))
        _create_dataset(f, "coords", cd.coords)
        _write_dataframe(f, "spots", spots)
        f["spots"].attrs["_column_order"] = json.dumps([str(c) for c in cd.spots.columns])
        _write_dataframe(f, "tracks", cd._bin_tracks.reset_index(drop=True),
                         n_rows=cd.n_bins)
        _write_dataframe(f, "spot_tracks", cd._spot_tracks, n_rows=cd.n_spots)
        if cd._spot_view_order:
            f["spot_tracks"].attrs["_spot_view_order"] = json.dumps(cd._spot_view_order)
        _write_dict_of_arrays(f, "binm", cd.binm)
        _write_dataframe(f, "cells", cd.cells)
        _write_dataframe(f, "traces", cd.traces)
        _write_dict_of_arrays(f, "layers", cd.layers)
        _write_dict_of_arrays(f, "cellm", cd.cellm)
        grp = f.create_group("intervals")
        for key, table in cd._intervals.items():
            _write_dataframe(grp, key, pd.DataFrame(table))
            grp[key].attrs["_kind"] = table.kind or ""
            grp[key].attrs["_source_result"] = table.source_result or ""
        _write_results(f, "results", cd.results, intervals=cd._intervals)
        _write_uns(f, "uns", cd.uns)
        if cd.points:
            grp = f.create_group("points")
            for key, df in cd.points.items():
                if "/" in key or not key:
                    raise ValueError(f"points key must be non-empty without '/': {key!r}")
                _write_dataframe(grp, key, df)
        if cd.cell_shapes:
            import warnings
            warnings.warn("cell_shapes are not stored in .h5cd; write a .chromdata.zarr / .cdz to keep "
                          "the cell outlines", UserWarning, stacklevel=3)


def _read_v1(cls, f) -> "ChromData":
    """Reader for .h5cd format MAJOR version 1, upgraded to the 2.0 model.

    ``bins`` are the unique ``(chrom, start, end)`` of the spots (ordered
    by chromosome, start, end) and ``spots.bin_id`` points into them.  The
    spot-aligned 1.x ``tracks`` table is split: columns that are constant
    for every spot of a bin become ``bin_tracks``, the rest ``spot_tracks``
    (logged at INFO level on the ``uchrom`` logger).
    """
    import logging

    coords = f["coords"][:]
    spots = _read_dataframe(f, "spots")
    cells = _read_dataframe(f, "cells")
    tracks = _read_dataframe(f, "tracks")
    traces = _read_dataframe(f, "traces")
    layers = _read_dict_of_arrays(f, "layers")
    cellm = _read_dict_of_arrays(f, "cellm")
    results = _read_results_store(f, "results")
    uns = _read_uns(f, "uns")
    points = {k: _read_dataframe(f["points"], k) for k in f["points"]} if "points" in f else {}
    if len(spots) == 0 and not all(c in spots.columns for c in LOCI):
        for col in LOCI:
            if col not in spots.columns:
                spots[col] = pd.Series(dtype=object if col == "chrom" else np.int64)

    cd = cls(
        coords,
        spots,
        cells=cells if len(cells) > 0 else None,
        cellm=cellm or None,
        traces=traces if len(traces) > 0 else None,
        layers=layers or None,
        results=results,
        uns=uns or None,
        points=points or None,
    )
    if len(tracks) > 0 and len(tracks.columns) > 0:
        cd._set_spot_aligned_tracks(tracks)
        names = cd.track_names()
        logging.getLogger("uchrom").info(
            "format 1.x upgrade: %d track(s) -> bin_tracks %s; %d -> spot_tracks %s",
            len(names["bin"]), names["bin"], len(names["spot"]), names["spot"],
        )
    return cd


def _read_v2(cls, f) -> "ChromData":
    """Reader for .h5cd format MAJOR version 2."""
    bins = _read_dataframe(f, "bins")
    if len(bins.columns) == 0:
        bins = pd.DataFrame({"chrom": pd.Series(dtype=object),
                             "start": pd.Series(dtype=np.int64),
                             "end": pd.Series(dtype=np.int64)})
    bins.index = pd.RangeIndex(len(bins), name=BIN_ID)
    coords = f["coords"][:]
    spots = _read_dataframe(f, "spots")
    if BIN_ID not in spots.columns:
        spots[BIN_ID] = np.zeros(len(spots), dtype=np.int64)
    spots[BIN_ID] = spots[BIN_ID].to_numpy().astype(np.int64)
    bin_tracks = _read_dataframe(f, "tracks")
    spot_tracks = _read_dataframe(f, "spot_tracks")
    intervals = {}
    if "intervals" in f:
        for key in f["intervals"]:
            table = _read_dataframe(f["intervals"], key)
            attrs = f["intervals"][key].attrs
            intervals[key] = IntervalTable.from_frame(
                table,
                kind=_attr_str(attrs.get("_kind")) or None,
                source_result=_attr_str(attrs.get("_source_result")) or None,
            )
    cd = cls(
        coords,
        spots,
        bins=bins,
        cells=_nonempty(_read_dataframe(f, "cells")),
        cellm=_read_dict_of_arrays(f, "cellm") or None,
        binm=_read_dict_of_arrays(f, "binm") or None,
        intervals=intervals,
        traces=_nonempty(_read_dataframe(f, "traces")),
        layers=_read_dict_of_arrays(f, "layers") or None,
        results=_read_results_store(f, "results", intervals=intervals),
        uns=_read_uns(f, "uns") or None,
        points={k: _read_dataframe(f["points"], k) for k in f["points"]} if "points" in f else None,
    )
    if len(bin_tracks.columns):
        cd.bin_tracks = bin_tracks
    if len(spot_tracks.columns):
        cd.spot_tracks = spot_tracks
    order = _attr_str(f["spot_tracks"].attrs.get("_spot_view_order")) if "spot_tracks" in f else None
    if order:
        cd._spot_view_order = json.loads(order)
    col_order = _attr_str(f["spots"].attrs.get("_column_order")) if "spots" in f else None
    if col_order:
        wanted = [c for c in json.loads(col_order) if c in cd.spots.columns]
        cd.spots = cd.spots[wanted + [c for c in cd.spots.columns if c not in wanted]]
    return cd


# ======================================================================
# HDF5 I/O helpers
# ======================================================================

def _write_dataframe(f, name: str, df: Optional[pd.DataFrame], n_rows: Optional[int] = None):
    """Write a DataFrame to an HDF5 group, one dataset per column.

    Format 1.1: when the index is not a trivial ``RangeIndex`` or has a
    name, it is written to a reserved ``_index`` dataset with the name
    stored in ``_index_name``.  Old (1.0) readers ignore both and
    reconstruct a default RangeIndex — the historical behaviour.

    Format 2.0: categorical columns are sub-groups ``{codes, categories}``
    (``_type = "categorical"``) instead of one byte string per row.
    ``n_rows`` records the row count of a column-less table.
    """
    if df is None or len(df.columns) == 0:
        grp = f.create_group(name)
        if n_rows is not None:
            grp.attrs["_n_rows"] = int(n_rows)
        return
    grp = f.create_group(name)
    grp.attrs["_n_rows"] = len(df)
    if len(df) == 0:
        # keep the schema of empty tables (e.g. spots of data without 3-D
        # coordinates) so required columns survive a round trip
        grp.attrs["_columns"] = [str(c) for c in df.columns]
        grp.attrs["_empty"] = True
        # dtypes of the empty columns (additive, format 1.4) so that an
        # empty result table keeps its schema on a round trip
        grp.attrs["_dtypes"] = [_empty_dtype_str(df[c].dtype) for c in df.columns]
        return
    grp.attrs["_columns"] = list(df.columns)
    for col in df.columns:
        series = df[col]
        if hasattr(series.dtype, "categories"):
            _write_categorical(grp, col, series)
            continue
        elif series.dtype == object:
            data = series.astype(str).values
        else:
            data = series.values
        if data.dtype.kind in ("U", "S", "O"):
            _create_dataset(grp, col, _encode_str(data) if data.dtype.kind != "S" else data)
        else:
            _create_dataset(grp, col, data)

    # Preserve a non-trivial index — see format 1.1 note above.
    idx = df.index
    is_trivial_range = (
        isinstance(idx, pd.RangeIndex)
        and idx.start == 0
        and idx.step == 1
        and idx.name is None
    )
    if not is_trivial_range:
        idx_vals = idx.to_numpy()
        if idx_vals.dtype == object or idx_vals.dtype.kind in ("U", "S"):
            data = _encode_str(idx_vals.astype(str))
        else:
            data = idx_vals
        grp.create_dataset("_index", data=data)
        grp.attrs["_index_name"] = idx.name if idx.name is not None else ""


# Filter settings for the current ``ChromData.write`` call (set / reset there).
_WRITE_OPTS: Dict[str, Any] = {"compression": None, "compression_opts": None,
                               "compress_floats": False}
_COMPRESS_MIN_ELEMENTS = 4096
_CHUNK_ROWS = 65536


def _create_dataset(grp, name: str, data) -> Any:
    """``create_dataset`` with the write call's compression for big arrays.

    Arrays of at least 4,096 elements are chunked along the first axis
    (up to 65,536 rows per chunk) and compressed; smaller ones are stored
    contiguously, so tiny files do not pay the chunk-index overhead.
    Float arrays are compressed only with ``compress_floats``.
    """
    data = np.asarray(data)
    comp = _WRITE_OPTS.get("compression")
    if data.dtype.kind in "fc" and not _WRITE_OPTS.get("compress_floats"):
        comp = None
    if comp is None or data.ndim == 0 or data.size < _COMPRESS_MIN_ELEMENTS:
        return grp.create_dataset(name, data=data)
    chunks = (min(len(data), _CHUNK_ROWS),) + tuple(data.shape[1:])
    return grp.create_dataset(name, data=data, chunks=chunks, compression=comp,
                              compression_opts=_WRITE_OPTS.get("compression_opts"),
                              shuffle=data.dtype.kind in "iuf")


def _encode_str(values) -> np.ndarray:
    """str array → fixed-width UTF-8 bytes (vectorised; ASCII fast path)."""
    arr = np.asarray(values, dtype=str)
    try:
        return arr.astype("S")
    except UnicodeEncodeError:
        return np.char.encode(arr, "utf-8")


def _decode_bytes(arr: np.ndarray, dtype=None) -> np.ndarray:
    """Fixed-width bytes → str (vectorised; ASCII fast path, UTF-8 fallback)."""
    try:
        out = arr.astype(str)
    except UnicodeDecodeError:
        out = np.char.decode(arr, "utf-8")
    return out.astype(dtype) if dtype is not None else out


def _write_categorical(grp, col: str, series: pd.Series) -> None:
    """Categorical column → ``{codes, categories}`` sub-group (format 2.0)."""
    cat = series.cat
    n = len(cat.categories)
    code_dtype = np.int8 if n < 2 ** 7 else np.int16 if n < 2 ** 15 else np.int32
    sub = grp.create_group(col)
    sub.attrs["_type"] = "categorical"
    sub.attrs["_ordered"] = bool(cat.ordered)
    _create_dataset(sub, "codes", np.asarray(cat.codes).astype(code_dtype))
    cats = np.asarray(cat.categories)
    if cats.dtype.kind in "OUS":
        sub.create_dataset("categories", data=_encode_str(cats.astype(str)))
    else:
        sub.create_dataset("categories", data=cats)


def _read_categorical(sub) -> pd.Categorical:
    cats = sub["categories"][:]
    if cats.dtype.kind == "S":
        cats = _decode_bytes(cats, dtype=object)
    return pd.Categorical.from_codes(
        sub["codes"][:].astype(np.int64), categories=cats,
        ordered=bool(sub.attrs.get("_ordered", False)),
    )


def _empty_dtype_str(dtype) -> str:
    """dtype name for an empty column; anything exotic → ``object``."""
    if hasattr(dtype, "categories"):
        return "object"
    try:
        np.dtype(dtype)
    except TypeError:
        return "object"
    return str(dtype)


def _read_dataframe(f, name: str) -> pd.DataFrame:
    """Read a DataFrame from an HDF5 group."""
    if name not in f:
        return pd.DataFrame()
    grp = f[name]
    if "_columns" not in grp.attrs:
        return pd.DataFrame()
    columns = [_attr_str(c) for c in grp.attrs["_columns"]]
    if grp.attrs.get("_empty", False):
        dtypes = [_attr_str(d) for d in grp.attrs.get("_dtypes", [])]
        if len(dtypes) != len(columns):
            dtypes = ["object"] * len(columns)
        return pd.DataFrame({c: pd.Series(dtype=d) for c, d in zip(columns, dtypes)})
    data = {}
    for col in columns:
        if col not in grp:
            continue
        item = grp[col]
        if isinstance(item, type(grp)):
            if _attr_str(item.attrs.get("_type")) == "categorical":
                data[col] = _read_categorical(item)
            continue
        arr = item[:]
        if arr.dtype.kind == "O" and len(arr) and isinstance(arr[0], bytes):
            arr = arr.astype("S")        # variable-length strings (h5py returns bytes)
        if arr.dtype.kind == "S":
            arr = _decode_bytes(arr)
        data[col] = arr
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    # Format 1.1: restore the index if it was persisted.
    if "_index" in grp:
        idx_arr = grp["_index"][:]
        if idx_arr.dtype.kind == "S":
            idx_arr = _decode_bytes(idx_arr)
        name_attr = grp.attrs.get("_index_name", "")
        if isinstance(name_attr, bytes):
            name_attr = name_attr.decode("utf-8")
        idx_name = name_attr or None
        df.index = pd.Index(idx_arr, name=idx_name)
    return df


def _write_dict_of_arrays(f, name: str, d: dict):
    """Write a dict of numpy arrays to an HDF5 group."""
    grp = f.create_group(name)
    for key, arr in d.items():
        _create_dataset(grp, key, np.asarray(arr))


def _read_dict_of_arrays(f, name: str) -> dict:
    """Read a dict of numpy arrays from an HDF5 group."""
    if name not in f:
        return {}
    grp = f[name]
    return {key: grp[key][:] for key in grp}


def _write_results(f, name: str, results, _path: str = "results", intervals=None):
    """Write ``cd.results`` (a ResultsStore or plain dict) to HDF5.

    Values are written by :func:`_write_result_value` (format 1.2 typed
    layout).  Format 1.4: when ``results`` is a :class:`ResultsStore`, the
    provenance of each top-level record is added as attrs on the value's
    group / dataset (``_kind``, ``_function``, ``_params``, ``_inputs``,
    ``_uchrom_version``, ``_created_utc``).
    """
    grp = f.create_group(name)
    grp.attrs["_type"] = "dict"
    records = results.records() if isinstance(results, ResultsStore) else None
    ref_of = {id(t): k for k, t in (intervals or {}).items()}
    for key, val in results.items():
        key = str(key)
        where = f"{_path}[{key!r}]"
        if records is not None and records[key].kind == "intervals" and id(val) in ref_of:
            # format 2.0: the value lives in intervals/<key>; store a reference
            sub = grp.create_group(key)
            sub.attrs["_type"] = "ref"
            sub.attrs["_value_ref"] = f"intervals/{ref_of[id(val)]}"
        else:
            _write_result_value(grp, key, val, where)
        if records is not None:
            rec = records[key]
            attrs = grp[key].attrs
            attrs["_kind"] = rec.kind
            attrs["_function"] = rec.function or ""
            attrs["_params"] = json.dumps(rec.params, allow_nan=True, sort_keys=True)
            attrs["_inputs"] = json.dumps(rec.inputs, allow_nan=True, sort_keys=True)
            attrs["_uchrom_version"] = rec.uchrom_version or ""
            attrs["_created_utc"] = rec.created_utc or ""


def _write_result_value(grp, key: str, val: Any, where: str) -> None:
    """Write one results value (format 1.2 typed layout).

    * ``dataframe`` — sub-group, one dataset per column (1.0 layout)
    * ``series``    — as ``dataframe`` with a single column
    * ``dict``      — sub-group, written recursively
    * ``json``      — scalar string dataset holding a JSON document
                      (str / int / float / bool / None / list / tuple)
    * plain dataset (no ``_type``) — ndarray

    Values that fit none of these raise ``TypeError`` instead of being
    silently dropped (the pre-1.2 behaviour).
    """
    if "/" in key or key in (".", ""):
        raise ValueError(f"{where}: result keys must be non-empty and contain no '/'.")
    if isinstance(val, pd.DataFrame):
        _write_dataframe(grp, key, val)
        grp[key].attrs["_type"] = "dataframe"
    elif isinstance(val, pd.Series):
        _write_dataframe(grp, key, val.to_frame(name=_SERIES_COLUMN))
        grp[key].attrs["_type"] = "series"
        if val.name is not None:
            grp[key].attrs["_series_name"] = str(val.name)
    elif isinstance(val, Mapping):
        sub = grp.create_group(key)
        sub.attrs["_type"] = "dict"
        for k, v in val.items():
            k = str(k)
            _write_result_value(sub, k, v, f"{where}[{k!r}]")
    elif isinstance(val, np.ndarray):
        if val.dtype == object:
            raise TypeError(
                f"{where}: object-dtype arrays cannot be stored in .h5cd; "
                f"convert to a numeric/string dtype or a list first."
            )
        grp.create_dataset(key, data=val)
    else:
        if isinstance(val, np.generic):
            val = val.item()
        try:
            doc = json.dumps(_results_jsonable(val), allow_nan=True)
        except TypeError as exc:
            raise TypeError(
                f"{where}: cannot serialise value of type "
                f"{type(val).__name__} to .h5cd results. Supported: "
                f"DataFrame, Series, ndarray, dict, and JSON-compatible "
                f"scalars / lists."
            ) from exc
        ds = grp.create_dataset(key, data=doc)
        ds.attrs["_type"] = "json"
        if isinstance(val, tuple):
            ds.attrs["_pytype"] = "tuple"


def _read_results_store(f, name: str, intervals=None) -> ResultsStore:
    """Read ``results/`` into a :class:`ResultsStore`.

    Items with format-1.4 provenance attrs become full records; older
    items (no ``_kind``) become records with an inferred kind and no
    provenance.
    """
    store = ResultsStore()
    if name not in f:
        return store
    values = _read_results(f, name)
    grp = f[name]
    for key, value in values.items():
        attrs = grp[key].attrs
        ref = _attr_str(attrs.get("_value_ref"))
        if ref:
            value = (intervals or {})[ref.split("/", 1)[1]]
        kind = _attr_str(attrs.get("_kind"))
        if not kind:
            store[key] = value
            continue
        store[key] = ResultRecord(
            kind=kind,
            value=value,
            params=json.loads(_attr_str(attrs.get("_params")) or "{}"),
            function=_attr_str(attrs.get("_function")) or None,
            uchrom_version=_attr_str(attrs.get("_uchrom_version")) or "unknown",
            inputs=json.loads(_attr_str(attrs.get("_inputs")) or "{}"),
            created_utc=_attr_str(attrs.get("_created_utc")) or "",
        )
    return store


def _read_results(f, name: str) -> dict:
    """Read a results dict of plain values (inverse of :func:`_write_results`).

    Pre-1.2 files have no ``_type`` attrs: groups are DataFrames and
    datasets are arrays, which is exactly the fallback below.
    """
    if name not in f:
        return {}
    grp = f[name]
    results = {}
    for key in grp:
        item = grp[key]
        kind = _attr_str(item.attrs.get("_type"))
        if isinstance(item, type(grp)):
            if kind == "ref":
                results[key] = None      # resolved by _read_results_store
            elif kind == "dict":
                results[key] = _read_results(grp, key)
            elif kind == "series":
                series = _read_dataframe(grp, key)[_SERIES_COLUMN]
                series.name = _attr_str(item.attrs.get("_series_name"))
                results[key] = series
            else:  # "dataframe" or legacy (untyped) group
                results[key] = _read_dataframe(grp, key)
        elif kind == "json":
            raw = item[()]
            value = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
            if _attr_str(item.attrs.get("_pytype")) == "tuple":
                value = tuple(value)
            results[key] = value
        else:
            results[key] = item[:]
    return results


def _attr_str(value: Any) -> Optional[str]:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def _write_uns(f, name: str, uns: dict):
    """Write uns dict to HDF5 attrs and sub-groups."""
    grp = f.create_group(name)
    for key, val in uns.items():
        if isinstance(val, (str, int, float, bool)):
            grp.attrs[key] = val
        elif isinstance(val, np.ndarray):
            grp.create_dataset(key, data=val)
        elif isinstance(val, dict):
            _write_uns(grp, key, val)
        elif isinstance(val, (list, tuple)):
            try:
                grp.create_dataset(key, data=np.array(val))
            except (TypeError, ValueError):
                grp.attrs[key] = _UNS_JSON_PREFIX + json.dumps(
                    _metadata_jsonable(val),
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                )
        else:
            grp.attrs[key] = str(val)


def _read_uns(f, name: str) -> dict:
    """Read uns dict from HDF5."""
    if name not in f:
        return {}
    grp = f[name]
    result = {key: _read_uns_attr(value) for key, value in grp.attrs.items()}
    for key in grp:
        item = grp[key]
        if isinstance(item, type(grp)):
            result[key] = _read_uns(grp, key)
        else:
            result[key] = item[:]
    return result


def _read_uns_attr(value: Any) -> Any:
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str) and value.startswith(_UNS_JSON_PREFIX):
        return json.loads(value[len(_UNS_JSON_PREFIX):])
    return value
