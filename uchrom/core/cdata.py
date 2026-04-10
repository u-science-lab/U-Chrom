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

        path = Path(path)
        with h5py.File(path, "w") as f:
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
        """Read from HDF5 (.h5cd) file."""
        import h5py

        path = Path(path)
        with h5py.File(path, "r") as f:
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

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame, **kwargs) -> "ChromData":
        """Create from a reconstruction output DataFrame.

        Expects columns: chrom, start, end, x, y, z.
        Each chromosome becomes one trace.
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

        # Carry over extra columns (e.g. cell_id, contact_count)
        skip = required | {"index"}
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
        columns = None

        with open(path, "r") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("##Columns="):
                    cols_str = line.split("=", 1)[1].strip().strip("()")
                    columns = [c.strip() for c in cols_str.split(",")]
                elif line.startswith("##"):
                    key, _, val = line[2:].partition("=")
                    header_meta[key.strip()] = val.strip()
                elif line.startswith("#"):
                    key, _, val = line[1:].partition(":")
                    header_meta[key.strip()] = val.strip()
                else:
                    data_lines.append(line)

        if not data_lines:
            raise ValueError(f"No data rows found in {path}")

        # Parse data
        from io import StringIO as _StringIO
        text = "\n".join(data_lines)
        df = pd.read_csv(_StringIO(text), header=None, skipinitialspace=True)

        if columns is not None:
            df.columns = columns[:len(df.columns)]
        else:
            # Fallback: assume standard column order
            default_cols = ["Spot_ID", "Trace_ID", "X", "Y", "Z",
                            "Chrom", "Chrom_Start", "Chrom_End"]
            df.columns = default_cols[:len(df.columns)]

        # Map FOF-CT columns to ChromData
        col_map = {
            "X": "x", "Y": "y", "Z": "z",
            "Chrom": "chrom", "Chrom_Start": "start", "Chrom_End": "end",
            "Trace_ID": "trace_id", "Spot_ID": "spot_id",
            "Cell_ID": "cell_id",
            "Sub_Cell_ROI_ID": "sub_cell_roi_id",
            "Extra_Cell_ROI_ID": "extra_cell_roi_id",
        }
        df = df.rename(columns=col_map)

        coords = df[["x", "y", "z"]].values.astype(np.float64)

        spot_cols = ["chrom", "start", "end", "trace_id"]
        for extra in ("spot_id", "cell_id", "sub_cell_roi_id", "extra_cell_roi_id"):
            if extra in df.columns:
                spot_cols.append(extra)
        spots = df[spot_cols].copy()

        # Store FOF-CT header metadata
        uns = kwargs.pop("uns", {})
        if header_meta:
            uns["fofct_header"] = header_meta
        xyz_unit = header_meta.get("XYZ_Unit", None)
        if xyz_unit:
            uns["xyz_unit"] = xyz_unit
        genome = header_meta.get("Genome_Assembly", None)
        if genome:
            uns["genome_assembly"] = genome

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
