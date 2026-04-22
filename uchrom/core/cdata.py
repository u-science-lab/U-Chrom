"""ChromData — core data container for U-Chrom.

Analogous to AnnData for single-cell genomics, ChromData provides a
structured container for chromatin 3D structure data.

Hierarchy: Cell → Trace → Spot/Bin

Three core tables:
    - Core table: 3D coordinates + genomic positions (FOF-CT compatible)
    - Cell table: cell-level metadata and embeddings
    - Chromatin table: epigenomic tracks per bin (ATAC, ChIP, etc.)
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Union, Optional, Dict, List

import numpy as np
import pandas as pd


PathLike = Union[str, Path]

_SPOTS_REQUIRED_COLUMNS = ("chrom", "start", "end", "trace_id")
_CATEGORICAL_COLUMNS = ("chrom", "trace_id", "cell_id")

# ``.h5cd`` on-disk format version. Semantics (MAJOR.MINOR):
#   MAJOR bump  — breaking change: a reader for the old MAJOR cannot read the
#                 new file without running a migration.
#   MINOR bump  — additive/backwards-compatible change (e.g. a new optional
#                 group or attribute).  Older readers should ignore unknown
#                 fields and keep working.
FORMAT_VERSION = "1.0"
_SUPPORTED_MAJOR = 1


class ChromData:
    """Chromatin Data container.

    Parameters
    ----------
    coords : np.ndarray, shape (n_spots, 3)
        3D coordinates (x, y, z) for each spot/bin.
    spots : pd.DataFrame, shape (n_spots,)
        Spot-level metadata.  Required columns: chrom, start, end, trace_id.
        Optional: cell_id, spot_id, etc.
    cells : pd.DataFrame, optional
        Cell-level metadata.  Index should be cell_id.
    cellm : dict, optional
        Per-cell multi-dimensional annotations.
        e.g. ``{'embedding': array(n_cells, d)}``
    tracks : pd.DataFrame, optional
        Epigenomic signals per bin, row-aligned to *spots*.
        e.g. columns: ATAC, H3K27ac, H3K27me3, …
    traces : pd.DataFrame, optional
        Trace-level metadata.  Index should be trace_id.
    layers : dict, optional
        Alternative coordinate representations, each ``(n_spots, 3)``.
    results : dict, optional
        Analysis results.
        e.g. ``{'tads': DataFrame, 'loops': DataFrame, 'compartments': array}``
    uns : dict, optional
        Unstructured metadata.
        e.g. ``{'genome_assembly': 'GRCh38', 'xyz_unit': 'micron'}``
    validate : bool
        If True (default), validate data consistency on construction.
    """

    def __init__(
        self,
        coords: np.ndarray,
        spots: pd.DataFrame,
        *,
        cells: Optional[pd.DataFrame] = None,
        cellm: Optional[Dict[str, np.ndarray]] = None,
        tracks: Optional[pd.DataFrame] = None,
        traces: Optional[pd.DataFrame] = None,
        layers: Optional[Dict[str, np.ndarray]] = None,
        results: Optional[dict] = None,
        uns: Optional[dict] = None,
        validate: bool = True,
    ):
        self.coords = np.asarray(coords, dtype=np.float64)
        self.spots = spots.reset_index(drop=True)
        self.cells = cells if cells is not None else pd.DataFrame()
        self.cellm = cellm if cellm is not None else {}
        self.tracks = tracks
        self.traces = traces if traces is not None else pd.DataFrame()
        self.layers = layers if layers is not None else {}
        self.results = results if results is not None else {}
        self.uns = uns if uns is not None else {}

        # Convert string-heavy columns to categorical for memory efficiency
        self._categorify()

        if validate:
            self._validate()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def n_spots(self) -> int:
        return self.coords.shape[0]

    @property
    def n_traces(self) -> int:
        return self.spots["trace_id"].nunique()

    @property
    def n_cells(self) -> int:
        if "cell_id" in self.spots.columns:
            return self.spots["cell_id"].nunique()
        return len(self.cells) if len(self.cells) > 0 else 0

    @property
    def chroms(self) -> List[str]:
        return list(self.spots["chrom"].cat.categories
                    if hasattr(self.spots["chrom"], "cat")
                    else self.spots["chrom"].unique())

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate(self):
        if self.coords.ndim != 2 or self.coords.shape[1] != 3:
            raise ValueError(
                f"coords must have shape (n, 3), got {self.coords.shape}"
            )
        if self.coords.shape[0] != len(self.spots):
            raise ValueError(
                f"coords rows ({self.coords.shape[0]}) != spots rows ({len(self.spots)})"
            )
        for col in _SPOTS_REQUIRED_COLUMNS:
            if col not in self.spots.columns:
                raise ValueError(f"spots missing required column: '{col}'")
        if self.tracks is not None and len(self.tracks) != self.n_spots:
            raise ValueError(
                f"tracks rows ({len(self.tracks)}) != n_spots ({self.n_spots})"
            )
        for key, arr in self.layers.items():
            if arr.shape != self.coords.shape:
                raise ValueError(
                    f"layers['{key}'] shape {arr.shape} != coords shape {self.coords.shape}"
                )

    def _categorify(self):
        for col in _CATEGORICAL_COLUMNS:
            if col in self.spots.columns and not hasattr(self.spots[col].dtype, "categories"):
                self.spots[col] = self.spots[col].astype("category")

    # ------------------------------------------------------------------
    # Subsetting
    # ------------------------------------------------------------------

    def __getitem__(self, index) -> "ChromData":
        if isinstance(index, (pd.Series, np.ndarray)):
            if index.dtype == bool:
                index = np.where(index)[0]
        idx = np.asarray(index)

        new_coords = self.coords[idx]
        new_spots = self.spots.iloc[idx].reset_index(drop=True)
        new_tracks = self.tracks.iloc[idx].reset_index(drop=True) if self.tracks is not None else None
        new_layers = {k: v[idx] for k, v in self.layers.items()}

        # Filter traces/cells to those still referenced
        new_traces = self._filter_traces(new_spots)
        new_cells, new_cellm = self._filter_cells(new_spots)

        return ChromData(
            new_coords,
            new_spots,
            cells=new_cells,
            cellm=new_cellm,
            tracks=new_tracks,
            traces=new_traces,
            layers=new_layers,
            results=self.results,
            uns=self.uns,
            validate=False,
        )

    def _filter_traces(self, spots: pd.DataFrame) -> pd.DataFrame:
        if len(self.traces) == 0:
            return self.traces
        keep = spots["trace_id"].unique()
        return self.traces[self.traces.index.isin(keep)]

    def _filter_cells(self, spots: pd.DataFrame):
        if len(self.cells) == 0:
            return self.cells, self.cellm
        if "cell_id" not in spots.columns:
            return self.cells, self.cellm
        keep = spots["cell_id"].unique()
        mask = self.cells.index.isin(keep)
        new_cells = self.cells[mask]
        new_cellm = {}
        for k, v in self.cellm.items():
            new_cellm[k] = v[mask.values] if hasattr(mask, "values") else v[mask]
        return new_cells, new_cellm

    def get_cell(self, cell_id) -> "ChromData":
        if "cell_id" not in self.spots.columns:
            raise KeyError("spots has no 'cell_id' column")
        mask = self.spots["cell_id"] == cell_id
        return self[mask.values]

    def get_trace(self, trace_id) -> "ChromData":
        mask = self.spots["trace_id"] == trace_id
        return self[mask.values]

    def get_chrom(self, chrom: str) -> "ChromData":
        mask = self.spots["chrom"] == chrom
        return self[mask.values]

    # ------------------------------------------------------------------
    # Pairwise computation (on-demand, per-trace)
    # ------------------------------------------------------------------

    def compute_distances(self, trace_id=None) -> np.ndarray:
        """Compute pairwise Euclidean distance matrix.

        Parameters
        ----------
        trace_id : optional
            If given, compute only for spots in that trace.
            If None, compute for all spots (use with caution on large data).

        Returns
        -------
        np.ndarray, shape (n, n)
        """
        if trace_id is not None:
            sub = self.get_trace(trace_id)
            return _pdist_matrix(sub.coords)
        return _pdist_matrix(self.coords)

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def write(self, path: PathLike) -> None:
        """Write to HDF5 (.h5cd) file."""
        import h5py

        try:
            from uchrom import __version__ as _uchrom_version
        except Exception:
            _uchrom_version = "unknown"

        path = Path(path)
        with h5py.File(path, "w") as f:
            f.attrs["uchrom_format_version"] = FORMAT_VERSION
            f.attrs["uchrom_version"] = _uchrom_version
            f.create_dataset("coords", data=self.coords)
            _write_dataframe(f, "spots", self.spots)
            _write_dataframe(f, "cells", self.cells)
            _write_dataframe(f, "tracks", self.tracks)
            _write_dataframe(f, "traces", self.traces)
            _write_dict_of_arrays(f, "layers", self.layers)
            _write_dict_of_arrays(f, "cellm", self.cellm)
            _write_results(f, "results", self.results)
            _write_uns(f, "uns", self.uns)

    @classmethod
    def read(cls, path: PathLike) -> "ChromData":
        """Read from HDF5 (.h5cd) file.

        Dispatches to a version-specific reader based on
        ``f.attrs['uchrom_format_version']``.  Files written before
        versioning was introduced are read with a warning using the v1.0
        reader (the on-disk layout has been stable from the start).

        Forward compatibility:

        - Same MAJOR, higher MINOR  → read with a warning; unknown fields
          are ignored silently by the lower-level helpers.
        - Different MAJOR           → raise ``ValueError`` with guidance.
        """
        import warnings
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
            if major != _SUPPORTED_MAJOR:
                raise ValueError(
                    f"{path}: format version {version_str} has incompatible "
                    f"MAJOR with this uchrom (supports MAJOR={_SUPPORTED_MAJOR}). "
                    f"Upgrade uchrom or convert the file."
                )
            cur_major, cur_minor = _parse_version(FORMAT_VERSION)
            if minor > cur_minor:
                warnings.warn(
                    f"{path}: written with format version {version_str} "
                    f"(reader supports up to {FORMAT_VERSION}). "
                    f"Forward-compatible — unknown fields will be ignored.",
                    stacklevel=2,
                )

            return _read_v1(cls, f)

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame, *, cell_id=None, **kwargs) -> "ChromData":
        """Create from a reconstruction output DataFrame.

        Expects columns: chrom, start, end, x, y, z.
        Each chromosome becomes one trace.

        Parameters
        ----------
        df : DataFrame with columns chrom, start, end, x, y, z.
        cell_id : hashable, optional
            If given, tag every spot with this cell identifier (e.g. derived
            from the output filename for single-cell reconstruction).  The
            DataFrame's own ``cell_id`` column, if any, takes precedence.
        **kwargs
            Forwarded to the :class:`ChromData` constructor.
        """
        required = {"chrom", "start", "end", "x", "y", "z"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"DataFrame missing columns: {missing}")

        coords = df[["x", "y", "z"]].values.astype(np.float64)

        # Assign trace_id: one trace per chromosome
        chroms = df["chrom"].values
        chrom_to_id = {c: i for i, c in enumerate(sorted(set(chroms)))}
        trace_ids = [chrom_to_id[c] for c in chroms]

        spots = pd.DataFrame({
            "chrom": df["chrom"].values,
            "start": df["start"].values,
            "end": df["end"].values,
            "trace_id": trace_ids,
        })

        if "cell_id" in df.columns:
            spots["cell_id"] = df["cell_id"].values
        elif cell_id is not None:
            spots["cell_id"] = cell_id

        # Carry over extra columns (e.g. contact_count)
        skip = required | {"index", "cell_id"}
        for col in df.columns:
            if col not in skip and col not in spots.columns:
                spots[col] = df[col].values

        return cls(coords, spots, **kwargs)

    @classmethod
    def from_fofct(cls, core_path: PathLike, **kwargs) -> "ChromData":
        """Read from FOF-CT core table file.

        Parameters
        ----------
        core_path : path
            Path to the FOF-CT core table (CSV/TSV/TXT).
        **kwargs
            Additional keyword arguments passed to ChromData constructor
            (e.g. cells, tracks, uns).
        """
        path = Path(core_path)
        header_meta = {}
        data_lines = []
        columns = None  # from ``##columns=`` meta line if present

        with open(path, "r") as fh:
            for line in fh:
                raw = line.strip()
                if not raw:
                    continue
                # Some FOF-CT writers wrap the whole header line in quotes and
                # pad with trailing commas so every line has the same column
                # count.  Strip those so we can recognise ``#`` headers.
                stripped = raw.rstrip(",").strip()
                if stripped.startswith('"') and stripped.endswith('"') and len(stripped) >= 2:
                    stripped = stripped[1:-1]
                if stripped.lower().startswith("##columns="):
                    cols_str = stripped.split("=", 1)[1].strip().strip("()")
                    columns = [c.strip() for c in cols_str.split(",")]
                elif stripped.startswith("##"):
                    key, _, val = stripped[2:].partition("=")
                    header_meta[key.strip()] = val.strip()
                elif stripped.startswith("#"):
                    key, _, val = stripped[1:].partition(":")
                    header_meta[key.strip()] = val.strip()
                else:
                    data_lines.append(raw)

        if not data_lines:
            raise ValueError(f"No data rows found in {path}")

        # Some FOF-CT files repeat the column names as a CSV header row right
        # before the data (in addition to the ``##columns=`` meta line).  If
        # the first non-comment line has non-numeric values in positions where
        # numbers are expected, treat it as a CSV header.
        first_token = data_lines[0].split(",", 1)[0].strip()
        has_csv_header = bool(first_token) and not (
            first_token[0].isdigit() or first_token[0] in ("-", "+", ".")
        )
        if has_csv_header:
            header_row = data_lines[0]
            data_lines = data_lines[1:]
            if columns is None:
                columns = [c.strip() for c in header_row.split(",")]

        if not data_lines:
            raise ValueError(f"No data rows found in {path}")

        # Parse data
        from io import StringIO as _StringIO
        text = "\n".join(data_lines)
        df = pd.read_csv(_StringIO(text), header=None, skipinitialspace=True)

        if columns is not None and len(columns) == len(df.columns):
            df.columns = columns
        elif columns is not None:
            # Column count mismatch — trust the data and label the extras
            df.columns = columns + [f"col_{i}" for i in range(len(columns), len(df.columns))]
        else:
            default_cols = ["Spot_ID", "Trace_ID", "X", "Y", "Z",
                            "Chrom", "Chrom_Start", "Chrom_End"]
            df.columns = default_cols[:len(df.columns)]

        # Map FOF-CT columns to ChromData — case-insensitive.
        canonical_map = {
            "x": "x", "y": "y", "z": "z",
            "chrom": "chrom",
            "chrom_start": "start", "chromstart": "start",
            "chrom_end": "end", "chromend": "end",
            "trace_id": "trace_id", "traceid": "trace_id",
            "spot_id": "spot_id", "spotid": "spot_id",
            "cell_id": "cell_id", "cellid": "cell_id",
            "sub_cell_roi_id": "sub_cell_roi_id",
            "extra_cell_roi_id": "extra_cell_roi_id",
        }
        rename = {c: canonical_map[c.lower()] for c in df.columns if c.lower() in canonical_map}
        df = df.rename(columns=rename)

        missing = {"x", "y", "z"} - set(df.columns)
        if missing:
            raise ValueError(
                f"FOF-CT core table missing coordinate columns {missing}. "
                f"Parsed columns: {list(df.columns)}"
            )

        coords = df[["x", "y", "z"]].values.astype(np.float64)

        # Spot-level columns: the required set first, then any extras carried
        # through verbatim (custom FOF-CT columns like ``Readout``).
        spot_cols = ["chrom", "start", "end", "trace_id"]
        for extra in ("spot_id", "cell_id", "sub_cell_roi_id", "extra_cell_roi_id"):
            if extra in df.columns and extra not in spot_cols:
                spot_cols.append(extra)
        coord_cols = {"x", "y", "z"}
        for col in df.columns:
            if col not in spot_cols and col not in coord_cols:
                spot_cols.append(col)
        spots = df[spot_cols].copy()

        # Store FOF-CT header metadata (case-insensitive lookup for promotion).
        uns = kwargs.pop("uns", {})
        if header_meta:
            uns["fofct_header"] = header_meta
        lower_meta = {k.lower(): v for k, v in header_meta.items()}
        if "xyz_unit" in lower_meta:
            uns["xyz_unit"] = lower_meta["xyz_unit"]
        if "genome_assembly" in lower_meta:
            uns["genome_assembly"] = lower_meta["genome_assembly"]

        return cls(coords, spots, uns=uns, **kwargs)

    def to_dataframe(self) -> pd.DataFrame:
        """Export as a flat DataFrame with coords + spots columns."""
        df = self.spots.copy()
        df["x"] = self.coords[:, 0]
        df["y"] = self.coords[:, 1]
        df["z"] = self.coords[:, 2]
        # Reorder so coords are prominent
        front = ["chrom", "start", "end", "x", "y", "z"]
        rest = [c for c in df.columns if c not in front]
        return df[front + rest]

    # ------------------------------------------------------------------
    # Copy
    # ------------------------------------------------------------------

    def copy(self) -> "ChromData":
        return ChromData(
            self.coords.copy(),
            self.spots.copy(),
            cells=self.cells.copy() if len(self.cells) > 0 else None,
            cellm={k: v.copy() for k, v in self.cellm.items()} or None,
            tracks=self.tracks.copy() if self.tracks is not None else None,
            traces=self.traces.copy() if len(self.traces) > 0 else None,
            layers={k: v.copy() for k, v in self.layers.items()} or None,
            results=deepcopy(self.results) or None,
            uns=deepcopy(self.uns) or None,
            validate=False,
        )

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        parts = [
            f"ChromData: n_spots={self.n_spots}, n_traces={self.n_traces}",
        ]
        if self.n_cells > 0:
            parts[0] += f", n_cells={self.n_cells}"

        spot_cols = list(self.spots.columns)
        parts.append(f"  spots:   {spot_cols}")

        if len(self.cells) > 0:
            parts.append(f"  cells:   {list(self.cells.columns)} ({len(self.cells)} cells)")
        if self.cellm:
            shapes = {k: v.shape for k, v in self.cellm.items()}
            parts.append(f"  cellm:   {shapes}")
        if self.tracks is not None:
            parts.append(f"  tracks:  {list(self.tracks.columns)}")
        if len(self.traces) > 0:
            parts.append(f"  traces:  {list(self.traces.columns)} ({len(self.traces)} traces)")
        if self.layers:
            parts.append(f"  layers:  {list(self.layers.keys())}")
        if self.results:
            parts.append(f"  results: {list(self.results.keys())}")
        if self.uns:
            parts.append(f"  uns:     {list(self.uns.keys())}")

        return "\n".join(parts)

    def __len__(self) -> int:
        return self.n_spots


# ======================================================================
# Utilities
# ======================================================================

def _pdist_matrix(coords: np.ndarray) -> np.ndarray:
    """Compute pairwise Euclidean distance matrix from (n, 3) coords."""
    diff = coords[:, None, :] - coords[None, :, :]
    return np.sqrt((diff ** 2).sum(axis=-1))


def _parse_version(s: str):
    """Parse 'MAJOR.MINOR' into a (major, minor) int tuple."""
    parts = str(s).split(".")
    try:
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        raise ValueError(f"invalid format version string: {s!r}")
    return major, minor


# ======================================================================
# Version-specific readers
# ======================================================================
# Add new `_read_vN` functions as MAJOR bumps occur; dispatch from
# ChromData.read().  Each reader is responsible for its on-disk layout
# and may call a migration helper to produce the current in-memory form.

def _read_v1(cls, f) -> "ChromData":
    """Reader for .h5cd format MAJOR version 1."""
    coords = f["coords"][:]
    spots = _read_dataframe(f, "spots")
    cells = _read_dataframe(f, "cells")
    tracks = _read_dataframe(f, "tracks")
    traces = _read_dataframe(f, "traces")
    layers = _read_dict_of_arrays(f, "layers")
    cellm = _read_dict_of_arrays(f, "cellm")
    results = _read_results(f, "results")
    uns = _read_uns(f, "uns")

    return cls(
        coords,
        spots,
        cells=cells if len(cells) > 0 else None,
        cellm=cellm or None,
        tracks=tracks if len(tracks) > 0 else None,
        traces=traces if len(traces) > 0 else None,
        layers=layers or None,
        results=results or None,
        uns=uns or None,
    )


# ======================================================================
# HDF5 I/O helpers
# ======================================================================

def _write_dataframe(f, name: str, df: Optional[pd.DataFrame]):
    """Write a DataFrame to an HDF5 group, one dataset per column."""
    if df is None or len(df) == 0:
        f.create_group(name)
        return
    grp = f.create_group(name)
    grp.attrs["_n_rows"] = len(df)
    grp.attrs["_columns"] = list(df.columns)
    for col in df.columns:
        series = df[col]
        if hasattr(series.dtype, "categories"):
            # Store categorical as string
            data = series.astype(str).values
        elif series.dtype == object:
            data = series.astype(str).values
        else:
            data = series.values
        if data.dtype.kind in ("U", "S", "O"):
            grp.create_dataset(col, data=data.astype("S"))
        else:
            grp.create_dataset(col, data=data)


def _read_dataframe(f, name: str) -> pd.DataFrame:
    """Read a DataFrame from an HDF5 group."""
    if name not in f:
        return pd.DataFrame()
    grp = f[name]
    if "_columns" not in grp.attrs:
        return pd.DataFrame()
    columns = list(grp.attrs["_columns"])
    data = {}
    for col in columns:
        if col not in grp:
            continue
        arr = grp[col][:]
        if arr.dtype.kind == "S":
            arr = np.array([x.decode("utf-8") for x in arr])
        data[col] = arr
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data)


def _write_dict_of_arrays(f, name: str, d: dict):
    """Write a dict of numpy arrays to an HDF5 group."""
    grp = f.create_group(name)
    for key, arr in d.items():
        grp.create_dataset(key, data=np.asarray(arr))


def _read_dict_of_arrays(f, name: str) -> dict:
    """Read a dict of numpy arrays from an HDF5 group."""
    if name not in f:
        return {}
    grp = f[name]
    return {key: grp[key][:] for key in grp}


def _write_results(f, name: str, results: dict):
    """Write results dict (DataFrames and arrays) to HDF5."""
    grp = f.create_group(name)
    for key, val in results.items():
        if isinstance(val, pd.DataFrame):
            _write_dataframe(grp, key, val)
        elif isinstance(val, np.ndarray):
            grp.create_dataset(key, data=val)


def _read_results(f, name: str) -> dict:
    """Read results dict from HDF5."""
    if name not in f:
        return {}
    grp = f[name]
    results = {}
    for key in grp:
        item = grp[key]
        if isinstance(item, type(grp)):  # is a group → DataFrame
            results[key] = _read_dataframe(grp, key)
        else:
            results[key] = item[:]
    return results


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
                grp.attrs[key] = str(val)
        else:
            grp.attrs[key] = str(val)


def _read_uns(f, name: str) -> dict:
    """Read uns dict from HDF5."""
    if name not in f:
        return {}
    grp = f[name]
    result = dict(grp.attrs)
    for key in grp:
        item = grp[key]
        if isinstance(item, type(grp)):
            result[key] = _read_uns(grp, key)
        else:
            result[key] = item[:]
    return result
