"""ChromData — core data container for U-Chrom.

Purpose
-------
``ChromData`` is the project-wide interface for chromatin 3D structure
data.  It unifies the two kinds of input U-Chrom consumes —

    * **sequencing-based** (Hi-C, Dip-C) → produced by
      :mod:`uchrom.recon` reconstruction
    * **imaging-based** (ORCA, MERFISH, DNA seqFISH+) → produced by
      :mod:`uchrom.im` + chromatin tracing

— into a single flat "structure table" (*genomic bins → 3-D coordinates*)
plus hierarchical metadata for cells, traces, and population-level
aggregate results.  Every downstream analysis module (``uchrom.strc``,
``uchrom.fea``, ``uchrom.emb``, ``uchrom.pl``, the ``uchrom-browser`` web browser)
consumes or produces ``ChromData`` — the format is the contract that
decouples tools along the pipeline.

Conceptually it is the chromatin-structure analogue of
`AnnData <https://anndata.readthedocs.io/>`_ for scRNA-seq.  The main
difference is an extra hierarchical axis: AnnData has
``observations × variables``; ChromData has
``Cell → Trace → Spot`` with coordinates in 3-D.

Hierarchy
---------
Cell → Trace → Spot::

    * Spot   — one genomic bin observed in one trace, with an (x, y, z).
    * Trace  — an ordered polymer of spots along a chromatin fibre.  In
               a diploid cell one chromosome contributes two traces
               (maternal + paternal, when haplotype-resolved).
    * Cell   — a physical cell that contains one or more traces.

Attributes summary
------------------

    bins        DataFrame (n_bins)           locus axis, index = bin_id:
                                              chrom, start, end, [name, ...]
    bin_tracks  DataFrame (n_bins, ?)        per-locus signals (ATAC, GC,
                                              features, compartment score)
    binm        dict[str, (n_bins, ...)]     per-locus multi-dim
    intervals   dict[str, IntervalTable]     typed TADs / loops / peaks /
                                              segments
    coords      (n_spots, 3) ndarray         x, y, z per spot
    spots       DataFrame (n_spots, ≥2)      bin_id, trace_id, [cell_id,
                                              spot_id, ...]; chrom / start /
                                              end derived from bins
    spot_tracks DataFrame (n_spots, ?)       per-spot signals (IF, z-scores)
    tracks      (deprecated) spot-aligned view of bin_tracks + spot_tracks
    cells       DataFrame (n_cells, ?)       cell_type, position, ...
    cellm       dict[str, ndarray]            per-cell multi-dim
                                              (embedding, UMAP, ...)
    traces      DataFrame (n_traces, ?)      trace-level metadata
    layers      dict[str, (n_spots, 3)]      alt. coordinate sets
    points      dict[str, DataFrame]         non-genomic 3-D points (RNA spots, …)
    cell_shapes dict[str, DataFrame]         cell outlines (cell_id, WKB geometry);
                                              centroids: cells columns +
                                              uns['cell_spatial'] (format 2.3)
                                              (raw / corrected / aligned)
    clusters    dict[str, ClusterTable]       multi-way contacts: clusters of genomic
                                              fragments (SPRITE, Pore-C, ChIA-Drop; 2.4)
    results     ResultsStore                  analysis outputs + provenance
                                              (loops, tads, compartments)
    uns         dict                          unstructured metadata
                                              (genome_assembly, xyz_unit,
                                              fofct_header, ...)

See :attr:`_SPOTS_REQUIRED_COLUMNS` below for the contract on ``spots``.

Spot required columns
---------------------
    bin_id     int → ``bins.index`` (derived by the constructor from
               ``chrom / start / end`` when not given)
    trace_id   int or str (stored as ``pd.Categorical``)

``spots["chrom" / "start" / "end"]`` are derived from ``bins`` (kept in
memory for convenience, not stored on disk); ``cd.spots_with_loci()`` is
the stable accessor.  Constructors keep accepting spots with
``chrom / start / end`` and no ``bin_id``: bins are the unique loci.

Optional but conventional columns:

    cell_id            int or str (categorical)
    spot_id            int or str (globally unique; FOF-CT Spot_ID)
    sub_cell_roi_id    see FOF-CT
    extra_cell_roi_id  see FOF-CT

Any extra column is preserved verbatim (e.g. ``Readout`` in Takei / Hu
FOF-CT files).  String-heavy columns are auto-converted to
``pd.Categorical`` in ``__init__`` for ~10× memory savings on large
datasets.

FOF-CT compatibility
--------------------
:meth:`ChromData.from_fofct` parses a `4DN FOF-CT core table
<https://fish-omics-format.readthedocs.io/>`_:

    FOF-CT field          →  ChromData location
    ----------------------  ---------------------------------
    Spot_ID                 spots['spot_id']
    Trace_ID                spots['trace_id']
    X, Y, Z                 coords[:, 0], coords[:, 1], coords[:, 2]
    Chrom                   spots['chrom']
    Chrom_Start             spots['start']
    Chrom_End               spots['end']
    Cell_ID                 spots['cell_id']
    Sub_Cell_ROI_ID         spots['sub_cell_roi_id']
    Extra_Cell_ROI_ID       spots['extra_cell_roi_id']

Header fields (``##Genome_Assembly``, ``##XYZ_Unit``, ``#Lab_Name``,
``#Software_*``, ...) are preserved verbatim in
``uns['fofct_header']``; the two standard keys ``genome_assembly`` and
``xyz_unit`` are also promoted to top-level ``uns`` entries.  The parser
tolerates several real-world FOF-CT quirks (case-insensitive
``##columns=``, header lines wrapped in double quotes with trailing
commas, a CSV column header line after ``##columns=``, etc).

On-disk formats
---------------
``cd.write(path)`` / ``ChromData.read(path)`` pick the container from the
path:

    <name>.chromdata.zarr   format 2.0 — Zarr v3 group with Parquet tables,
                            spots sorted by (cell, trace, bin) plus an
                            ``index/`` of row offsets; readable *backed*
                            (``read(path, backed=True)``).  See
                            :mod:`chromdata.zarrcd` and ``spec.md``.
    <name>.cdz              the same store in one uncompressed zip file.

The older HDF5 container (``.h5cd``, format 1.x / 2.0) is no longer read or
written; ``python -m uchrom.io.upgrade old.h5cd`` converts a file once
(:mod:`uchrom.io._h5cd_legacy` holds its reader and layout).

Stores carry two root attributes:

    uchrom_format_version    "MAJOR.MINOR" contract of the file layout
    uchrom_version           uchrom package version that wrote the file

Semantics:

    * **Same MAJOR**  — readable.  Higher MINOR triggers a warning but
      unknown fields are ignored (forward-compatible additive changes).
    * **Different MAJOR** — :exc:`ValueError` on read, with guidance to
      upgrade chromdata or convert the file.

New MINOR layouts are read next to the old ones (as 2.2 reads 2.1 and 2.0);
see ``_check_zarr_version`` and :mod:`chromdata.zarrcd`.

Design decisions (why this shape)
---------------------------------
* **Flat storage + hierarchical access.**  ``spots`` holds every
  observation in one DataFrame; ``get_cell`` / ``get_trace`` /
  ``get_chrom`` return new ``ChromData`` instances.  Mutation is
  non-destructive.
* **No global pairwise matrix.**  Pairwise distances / contacts are
  biologically meaningful per-trace, not globally across cells, and
  would be O(n²) to store.  Use
  :meth:`ChromData.compute_distances` on demand.
* **Three "core tables"** distinguishing *where the data comes from*
  drives the module layout:

      * ``core``  (coords + spots)   — *what* (3-D structure)
      * ``cell`` (cells + cellm)     — *who* (cell identity / embedding)
      * ``tracks``                   — *what else per bin*
                                       (ATAC / ChIP signal)

* **Categorical dtypes** on string columns save ~10× memory without
  changing behaviour.
* **Versioned on-disk format** lets future changes break cleanly —
  downstream tools can refuse unknown MAJOR versions rather than
  silently deserialise wrong data.

See also the format specification (``packages/chromdata/spec.md``) for a short human-oriented description
of the format, and ``docs/source/guide/chromdata.md`` for tutorial-style
material.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Union, Optional, Dict, List, Mapping, Sequence, Tuple

import numpy as np
import pandas as pd

from .bins import (
    BIN_ID,
    LOCI,
    bins_from_loci,
    loci_of,
    map_loci_to_bins,
    normalise_bins,
    split_spot_tracks,
)
from .clusters import ClusterTable
from .intervals import IntervalStore
from .results import ResultsStore


PathLike = Union[str, Path]

_SPOTS_REQUIRED_COLUMNS = ("bin_id", "trace_id")
_CATEGORICAL_COLUMNS = ("chrom", "trace_id", "cell_id")
def _uchrom_io(module: str, name: str):
    """A reader of the analysis library ``uchrom`` (``uchrom.io.<module>.<name>``), which ``chromdata`` does not
    depend on: these loaders of specific datasets live there."""
    import importlib

    try:
        return getattr(importlib.import_module(f"uchrom.io.{module}"), name)
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.split(".")[0] == "uchrom":
            raise ImportError(f"{name} is part of the analysis library: pip install u-chrom") from exc
        raise


_UNS_JSON_PREFIX = "__uchrom_json__:"
_SERIES_COLUMN = "_value"



#: scratch directories of maps exported from the embedded copies of a store (by store location)
_EXPORT_DIRS: Dict[str, Path] = {}


class ChromData:
    """Chromatin Data — the core container for U-Chrom.

    See the module docstring of :mod:`chromdata.cdata` for the full
    purpose, hierarchy, FOF-CT mapping, and on-disk format contract.
    Summary:

    * The central abstraction is a "structure table" — genomic bins
      mapped to 3D coordinates.  Each row of ``spots`` (with the
      corresponding row of ``coords``) is one **Spot**.
    * Spots are grouped hierarchically as **Cell → Trace → Spot**.  A
      Trace is an ordered chromatin-fibre polymer; a Cell contains one
      or more traces.
    * All analysis in U-Chrom consumes or produces ``ChromData``.
      Reconstruction modules (``uchrom.recon``) emit it, structure
      callers (``uchrom.strc``) decorate ``cd.results[...]`` with TADs /
      loops / compartments, and the browser / plotters render it.

    Parameters
    ----------
    coords : ndarray, shape (n_spots, 3)
        3-D coordinates (x, y, z) per spot.
    spots : DataFrame, shape (n_spots, ≥2)
        Per-spot metadata.  **Required:** ``trace_id`` (int or str, will
        be categorified) and either ``bin_id`` (with ``bins=``) or the
        locus columns ``chrom`` / ``start`` (0-based) / ``end``
        (non-inclusive), from which ``bins`` and ``bin_id`` are derived.
        Optional: ``cell_id`` (int or str), ``spot_id``, FOF-CT
        ``sub_cell_roi_id`` / ``extra_cell_roi_id``, and any
        experiment-specific annotation column (carried through
        verbatim).
    bins : DataFrame, optional
        Locus axis (``chrom, start, end`` + optional ``resolution``,
        ``name``, …); row ``i`` is ``bin_id`` ``i``.  Derived from the spot
        loci when omitted (ordered by chromosome, start, end).
    cells : DataFrame, optional
        Per-cell metadata indexed by cell_id.
    cellm : dict[str, ndarray], optional
        Per-cell multi-dimensional annotations (embeddings, UMAP, …).
        Each array's first axis length = ``n_cells``.
    tracks : DataFrame, optional
        Per-locus signals (ATAC, ChIP-seq, …): ``n_bins`` rows (or an
        index named ``bin_id``) → :attr:`bin_tracks`.  A spot-aligned
        1.x table (``n_spots`` rows) is still accepted with a
        ``DeprecationWarning`` and split (columns constant within every
        bin → ``bin_tracks``, the rest → ``spot_tracks``).
    spot_tracks : DataFrame, optional
        Per-spot signals (IF intensity, seqFISH z-scores), ``n_spots`` rows.
    binm : dict[str, ndarray], optional
        Per-locus multi-dimensional arrays, first axis ``n_bins``.
    intervals : dict[str, DataFrame], optional
        Typed interval tables (see :mod:`chromdata.intervals`).
    traces : DataFrame, optional
        Per-trace metadata indexed by trace_id.
    layers : dict[str, ndarray], optional
        Alternative coordinate sets, each with shape ``(n_spots, 3)`` —
        e.g. raw / drift-corrected / aligned.
    points : dict[str, DataFrame], optional
        Named sets of non-genomic 3-D points in the same frame as
        ``coords`` — e.g. nascent RNA spots or IF puncta.  Each DataFrame
        needs ``x, y, z``; ``cell_id`` (if present) links points to cells
        and is used when subsetting.
    cell_shapes : dict[str, DataFrame], optional
        Cell outlines: ``cell_id`` + ``geometry`` (WKB bytes), one row per
        cell (see :meth:`set_cell_shapes`); subset with the cells.
    clusters : dict[str, ClusterTable], optional
        Multi-way contacts — clusters of genomic fragments observed together
        (SPRITE, Pore-C, ChIA-Drop; :class:`~chromdata.clusters.ClusterTable`,
        see :meth:`set_clusters`).  Kept whole when spots are subset.
    results : dict or ResultsStore, optional
        Analysis outputs, stored as a :class:`~chromdata.results.ResultsStore`
        (``cd.results[key]`` returns the value, ``cd.results.record(key)``
        the value plus provenance).  Keys follow ``"<what>.<method>"``:
        ``'tads.arcfish'``, ``'loops.axiswise_f'``,
        ``'compartments.axes_pc'``, ….
    uns : dict, optional
        Unstructured metadata preserved on disk.  Conventional keys:
        ``'genome_assembly'``, ``'xyz_unit'``, ``'fofct_header'``.
        Auto-discovery context may use ``'dataset_references'`` for source
        papers/repositories and ``'user_annotations'`` for user-provided
        priors, constraints, or hypothesis seeds.
    validate : bool
        If True (default), validate internal consistency on
        construction (coords shape, spots required columns, tracks /
        layers alignment).

    Notes
    -----
    Derived accessors: ``n_spots``, ``n_traces``, ``n_cells``, ``chroms``.  Key methods:
    ``from_dataframe``, ``from_fofct``, ``read``, ``write``, ``to_dataframe``, ``get_cell``,
    ``get_trace``, ``get_chrom``, ``compute_distances``.

    On-disk format — ``.chromdata.zarr`` / ``.cdz``
    -----------------------------------------------
    Versioned Zarr v3 + Parquet.  See :mod:`chromdata.cdata` module docstring for
    the full layout and the :meth:`read` / :meth:`write` round-trip
    contract.

    Notes
    -----
    * Subsetting (``cd[mask]``, ``get_chrom`` etc.) always returns a new
      ``ChromData``; the source is not mutated.
    * Global pairwise distance matrices are intentionally not stored —
      they are biologically meaningful per-trace, not across cells, and
      would be O(n²) memory.  Compute on demand via
      :meth:`compute_distances(trace_id=...)`.
    * String columns (``chrom``, ``trace_id``, ``cell_id``) are
      auto-converted to ``pd.Categorical`` for ~10× memory savings.
    """

    def __init__(
        self,
        coords: np.ndarray,
        spots: pd.DataFrame,
        *,
        bins: Optional[pd.DataFrame] = None,
        cells: Optional[pd.DataFrame] = None,
        cellm: Optional[Dict[str, np.ndarray]] = None,
        tracks: Optional[pd.DataFrame] = None,
        spot_tracks: Optional[pd.DataFrame] = None,
        binm: Optional[Dict[str, np.ndarray]] = None,
        intervals: Optional[Mapping[str, pd.DataFrame]] = None,
        traces: Optional[pd.DataFrame] = None,
        layers: Optional[Dict[str, np.ndarray]] = None,
        results: Optional[dict] = None,
        uns: Optional[dict] = None,
        points: Optional[Dict[str, pd.DataFrame]] = None,
        cell_shapes: Optional[Dict[str, pd.DataFrame]] = None,
        clusters: Optional[Dict[str, ClusterTable]] = None,
        linked_adata=None,
        validate: bool = True,
        _own_spots: bool = False,
    ):
        # _own_spots: the caller hands over a fresh spots frame (RangeIndex)
        # that may be modified in place — readers use it to skip two copies
        self.coords = np.asarray(coords, dtype=np.float64)
        self.spots, self._bins = _attach_bins(spots if _own_spots else spots.reset_index(drop=True),
                                              bins, validate=validate, copy=not _own_spots)
        self.cells = cells if cells is not None else pd.DataFrame()
        self.cellm = cellm if cellm is not None else {}
        self.traces = traces if traces is not None else pd.DataFrame()
        self.layers = layers if layers is not None else {}
        self.binm = dict(binm) if binm is not None else {}
        self.intervals = intervals if intervals is not None else {}
        self.results = results if results is not None else {}
        self.uns = uns if uns is not None else {}
        self.points = {k: v.reset_index(drop=True) for k, v in (points or {}).items()}
        self.cell_shapes = {k: v.reset_index(drop=True) for k, v in (cell_shapes or {}).items()}
        self.clusters: Dict[str, ClusterTable] = dict(clusters or {})
        self._linked_adata = linked_adata

        self._bin_tracks = _empty_frame(self.n_bins, name=BIN_ID)
        self._spot_tracks = _empty_frame(len(self.spots))
        self._spot_view_order: Optional[List[str]] = None
        if spot_tracks is not None:
            self.spot_tracks = spot_tracks
        if tracks is not None:
            if _is_bin_level(tracks, self.n_bins, len(self.spots)):
                self.bin_tracks = tracks
            else:
                import warnings
                warnings.warn(
                    "ChromData(tracks=<spot-aligned table>) is deprecated: pass "
                    "per-spot signals as spot_tracks= and per-locus signals as "
                    "a bins-aligned tracks=.  The table was split automatically "
                    "(columns constant within every bin became bin-level).",
                    DeprecationWarning,
                    stacklevel=2,
                )
                self._set_spot_aligned_tracks(tracks)

        # Convert string-heavy columns to categorical for memory efficiency
        self._categorify()

        if validate:
            self._validate()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def results(self) -> ResultsStore:
        """Analysis outputs — a :class:`~chromdata.results.ResultsStore`.

        Behaves like a ``dict`` of values; assigning a plain ``dict``
        converts it.  Values that cannot be written to a store raise
        ``TypeError`` on assignment.
        """
        return self._results

    @results.setter
    def results(self, value) -> None:
        self._results = ResultsStore.coerce(value)

    @property
    def n_spots(self) -> int:
        return self.coords.shape[0]

    # -- locus axis (format 2.0) -------------------------------------------

    @property
    def bins(self) -> pd.DataFrame:
        """Locus axis: ``DataFrame`` indexed by ``bin_id`` with ``chrom``
        (category), ``start``, ``end`` and optional per-locus columns
        (``resolution``, ``name``, …).  Shared by all cells; subsetting
        spots keeps every bin."""
        return self._bins

    @property
    def n_bins(self) -> int:
        return len(self._bins)

    @property
    def bin_tracks(self) -> pd.DataFrame:
        """Per-locus signals (bulk ATAC, ChIP, GC, annotation features,
        compartment scores …), ``n_bins`` rows indexed by ``bin_id``.

        This is the table the 2.0 design calls ``tracks``; during the 2.x
        series ``cd.tracks`` remains the deprecated spot-aligned view.
        """
        return self._bin_tracks

    @bin_tracks.setter
    def bin_tracks(self, value: Optional[pd.DataFrame]) -> None:
        if value is None or len(value.columns) == 0:
            self._bin_tracks = _empty_frame(self.n_bins, name=BIN_ID)
            return
        if len(value) != self.n_bins:
            raise ValueError(f"bin_tracks rows ({len(value)}) != n_bins ({self.n_bins})")
        out = value.copy()
        out.index = pd.RangeIndex(self.n_bins, name=BIN_ID)
        self._bin_tracks = out
        self._drop_view_order_extras()

    @property
    def spot_tracks(self) -> pd.DataFrame:
        """Per-observation signals (per-spot IF intensity, seqFISH
        z-scores …), row-aligned to ``spots``."""
        return self._spot_tracks

    @spot_tracks.setter
    def spot_tracks(self, value: Optional[pd.DataFrame]) -> None:
        if value is None or len(value.columns) == 0:
            self._spot_tracks = _empty_frame(len(self.spots))
            return
        if len(value) != len(self.spots):
            raise ValueError(f"spot_tracks rows ({len(value)}) != n_spots ({len(self.spots)})")
        self._spot_tracks = value.reset_index(drop=True)
        self._drop_view_order_extras()

    @property
    def tracks(self) -> Optional[pd.DataFrame]:
        """Deprecated spot-aligned view of all tracks (1.x ``cd.tracks``).

        Returns :meth:`tracks_spot_view` — bin-level tracks broadcast to
        spots plus spot-level tracks — or ``None`` when there are none.
        Use :attr:`bin_tracks` / :attr:`spot_tracks` instead.  Assigning a
        spot-aligned table splits it (columns constant within every bin
        go to ``bin_tracks``, the rest to ``spot_tracks``); assigning a
        table with ``n_bins`` rows (or index named ``bin_id``) sets
        ``bin_tracks``.
        """
        import warnings
        warnings.warn(
            "cd.tracks is the deprecated spot-aligned view; use cd.bin_tracks "
            "(per locus), cd.spot_tracks (per spot) or cd.tracks_spot_view().",
            DeprecationWarning,
            stacklevel=2,
        )
        if len(self._bin_tracks.columns) == 0 and len(self._spot_tracks.columns) == 0:
            return None
        view = _TracksView(self.tracks_spot_view())
        view._uchrom_owner = self
        return view

    @tracks.setter
    def tracks(self, value: Optional[pd.DataFrame]) -> None:
        if value is None:
            self._bin_tracks = _empty_frame(self.n_bins, name=BIN_ID)
            self._spot_tracks = _empty_frame(len(self.spots))
            self._spot_view_order = None
        elif _is_bin_level(value, self.n_bins, len(self.spots)):
            self.bin_tracks = value
        else:
            self._set_spot_aligned_tracks(value)

    def _set_spot_aligned_tracks(self, value: pd.DataFrame) -> None:
        if len(value) != len(self.spots):
            raise ValueError(f"tracks rows ({len(value)}) != n_spots ({len(self.spots)})")
        bt, st, order = split_spot_tracks(value.reset_index(drop=True),
                                          self.spots[BIN_ID].to_numpy(), self.n_bins)
        self._bin_tracks = bt
        self._spot_tracks = st
        self._spot_view_order = order

    def _set_track_column(self, name: str, values) -> None:
        """Write one spot-aligned column (``cd.tracks[name] = values``).

        Stored bin-level when the column already is a bin track and the new
        values are constant within every bin, otherwise spot-level."""
        from .bins import constant_per_bin

        col = pd.Series(np.asarray(values), name=name).reset_index(drop=True)
        if len(col) != self.n_spots:
            raise ValueError(f"track {name!r} has {len(col)} values, expected n_spots={self.n_spots}")
        bin_id = self.spots[BIN_ID].to_numpy()
        order = np.argsort(bin_id, kind="stable")
        if name in self._bin_tracks.columns and constant_per_bin(col, bin_id, order):
            bt = self._bin_tracks.copy()
            bt.iloc[bin_id, bt.columns.get_loc(name)] = col.to_numpy()
            self._bin_tracks = bt
        else:
            if name in self._bin_tracks.columns:
                self._bin_tracks = self._bin_tracks.drop(columns=[name])
            st = self._spot_tracks.copy()
            st[name] = col.to_numpy()
            self._spot_tracks = st
        if self._spot_view_order is not None and name not in self._spot_view_order:
            self._spot_view_order.append(name)

    def _drop_view_order_extras(self) -> None:
        if self._spot_view_order is None:
            return
        present = set(map(str, self._bin_tracks.columns)) | set(map(str, self._spot_tracks.columns))
        self._spot_view_order = [c for c in self._spot_view_order if c in present]

    def tracks_spot_view(self, columns: Optional[List[str]] = None) -> pd.DataFrame:
        """All tracks aligned to spots (the 1.x ``tracks`` layout).

        Bin-level tracks are broadcast through ``spots.bin_id``;
        spot-level tracks are appended.  ``columns`` selects a subset.
        """
        bt, st = self._bin_tracks, self._spot_tracks
        if columns is not None:
            columns = [str(c) for c in columns]
            missing = [c for c in columns if c not in bt.columns and c not in st.columns]
            if missing:
                raise KeyError(f"unknown track(s): {missing}")
            bt = bt[[c for c in columns if c in bt.columns]]
            st = st[[c for c in columns if c in st.columns]]
        parts = []
        if len(bt.columns):
            view = bt.iloc[self.spots[BIN_ID].to_numpy()].reset_index(drop=True)
            parts.append(view)
        if len(st.columns):
            parts.append(st.reset_index(drop=True))
        if not parts:
            return pd.DataFrame(index=pd.RangeIndex(len(self.spots)))
        out = pd.concat(parts, axis=1) if len(parts) > 1 else parts[0]
        order = columns if columns is not None else self._spot_view_order
        if order:
            front = [c for c in order if c in out.columns]
            out = out[front + [c for c in out.columns if c not in front]]
        return out

    def track_names(self) -> Dict[str, List[str]]:
        """``{"bin": [...], "spot": [...]}`` — names of the stored tracks."""
        return {"bin": [str(c) for c in self._bin_tracks.columns],
                "spot": [str(c) for c in self._spot_tracks.columns]}

    @property
    def intervals(self) -> IntervalStore:
        """Typed interval tables (TADs, loops, peaks, segments) — see
        :mod:`chromdata.intervals`."""
        return self._intervals

    @intervals.setter
    def intervals(self, value) -> None:
        self._intervals = IntervalStore.coerce(value)

    def spots_with_loci(self) -> pd.DataFrame:
        """A copy of ``spots`` with ``chrom`` / ``start`` / ``end`` derived
        from ``bins`` via ``bin_id`` (the stable way to get spot loci)."""
        out = self.spots.copy()
        for col, vals in loci_of(self._bins, out[BIN_ID].to_numpy()).items():
            out[col] = vals
        return out

    def rebuild_bins(self) -> "ChromData":
        """Re-derive ``bins`` / ``bin_id`` from the spots' ``chrom`` /
        ``start`` / ``end`` after they were edited in place.  Bin-level
        tracks are carried over for loci that still exist; ``binm`` must be
        empty.  Returns ``self``."""
        if self.binm:
            raise ValueError("rebuild_bins() cannot remap binm; clear cd.binm first")
        old_bins, old_bt = self._bins, self._bin_tracks
        spots = self.spots.drop(columns=[BIN_ID])
        self.spots, self._bins = _attach_bins(spots, None, validate=True)
        if len(old_bt.columns):
            ids = map_loci_to_bins(self._bins, old_bins)  # new bins located in old
            bt = old_bt.iloc[np.where(ids >= 0, ids, 0)].reset_index(drop=True)
            bt.loc[ids < 0, :] = np.nan
            self.bin_tracks = bt
        else:
            self._bin_tracks = _empty_frame(self.n_bins, name=BIN_ID)
        return self

    def _check_bin_ids(self) -> None:
        """Spots must carry a valid ``bin_id`` whose bin matches the spot's
        chrom / start / end (the loci columns are derived, not independent)."""
        if BIN_ID not in self.spots.columns:
            if all(c in self.spots.columns for c in LOCI):
                ids = map_loci_to_bins(self.spots, self._bins)
                if (ids < 0).any():
                    raise ValueError(
                        "spots have no bin_id and some loci are not in cd.bins; "
                        "call cd.rebuild_bins()"
                    )
                self.spots[BIN_ID] = ids
                return
            raise ValueError("spots missing required column 'bin_id'")
        ids = self.spots[BIN_ID].to_numpy()
        if len(ids) and (ids.min() < 0 or ids.max() >= self.n_bins):
            raise ValueError(f"spots.bin_id out of range [0, {self.n_bins})")
        derived = loci_of(self._bins, ids.astype(np.int64))
        for col in LOCI:
            if col not in self.spots.columns:
                self.spots[col] = derived[col]
                continue
            have = self.spots[col]
            if col == "chrom":
                same = np.asarray(have.astype(str)) == np.asarray(pd.Series(derived[col]).astype(str))
            else:
                same = have.to_numpy() == derived[col]
            if not np.all(same):
                raise ValueError(
                    f"spots[{col!r}] disagrees with bins[spots.bin_id] for "
                    f"{int((~np.asarray(same)).sum())} spot(s).  chrom/start/end "
                    f"are derived from bins in format 2.0: edit cd.bins, or call "
                    f"cd.rebuild_bins() after editing spot loci."
                )

    @property
    def n_traces(self) -> int:
        return self.spots["trace_id"].nunique()

    @property
    def n_cells(self) -> int:
        # Cells known from spots; fall back to the cells table for data
        # without 3-D spots (e.g. single-cell Hi-C / RNA only).
        if "cell_id" in self.spots.columns and len(self.spots) > 0:
            return self.spots["cell_id"].nunique()
        return len(self.cells) if len(self.cells) > 0 else 0

    @property
    def chroms(self) -> List[str]:
        return [str(c) for c in self._bins["chrom"].cat.categories]

    @property
    def linked_adata(self):
        """Linked AnnData object, loaded lazily from ``uns`` metadata if possible."""
        if self._linked_adata is None:
            path = self.uns.get("linked_anndata", {}).get("path")
            if path:
                path = self.resolve_link_path(path)
                if path.exists():
                    import anndata as ad
                    self._linked_adata = ad.read_h5ad(path)
            if self._linked_adata is None:   # no file: an AnnData embedded in the store (embed_links)
                src = self._links_from()
                if src is not None and (isinstance(src, str) or Path(src).is_dir()):
                    from .embedded import list_embedded_anndata, read_embedded_anndata
                    found = list_embedded_anndata(str(src), "linked_anndata")
                    if found:
                        self._linked_adata = read_embedded_anndata(str(src), next(iter(found.values())))
        return self._linked_adata

    @linked_adata.setter
    def linked_adata(self, value) -> None:
        self._linked_adata = value

    def load_linked_anndata(self, path: Optional[PathLike] = None):
        """Load, cache, and return the linked AnnData object."""
        if path is None:
            path = self.uns.get("linked_anndata", {}).get("path")
        if path is None:
            raise ValueError("No linked AnnData path is recorded in cd.uns['linked_anndata'].")
        import anndata as ad
        self._linked_adata = ad.read_h5ad(self.resolve_link_path(path))
        return self._linked_adata

    def link_mudata(
        self,
        path: PathLike,
        *,
        key: str = "default",
        modalities: Optional[List[str]] = None,
        cell_axis: Optional[str] = None,
        spatial_source: Optional[str] = None,
        not_measured_spatial: Optional[bool] = None,
        **metadata: Any,
    ) -> dict:
        """Record a linked MuData file in ``uns['linked_mudata']``.

        The MuData object is kept external.  ``ChromData`` stores only
        lightweight provenance so multi-modal cell matrices are not forced
        into ``coords`` / ``spots``.
        """
        record = {
            "path": str(path),
            "format": "h5mu",
            "modalities": list(modalities) if modalities is not None else [],
            "cell_axis": cell_axis,
            "spatial_source": spatial_source,
            "not_measured_spatial": not_measured_spatial,
            **metadata,
        }
        record = _clean_metadata_record(record)
        _set_linked_record(self.uns, "linked_mudata", key, record)
        return record

    def load_linked_mudata(self, *, key: str = "default"):
        """Load a linked MuData file by key.

        ``mudata`` is an optional dependency.  A clear ImportError is raised
        when it is unavailable.
        """
        record = _linked_record(self.uns.get("linked_mudata"), key)
        path = record.get("path")
        if not path:
            raise ValueError(f"No linked MuData path is recorded for key {key!r}.")
        try:
            import mudata as md
        except ImportError as exc:  # pragma: no cover - depends on optional env
            raise ImportError(
                "mudata is required to load linked MuData files. "
                "Install it with `pip install mudata` or use an environment "
                "that provides mudata."
            ) from exc
        return md.read_h5mu(self.resolve_link_path(path))

    def link_scool(
        self,
        path: PathLike,
        *,
        key: str = "default",
        cell_name: Optional[str] = None,
        barcode_source: Optional[str] = None,
        genome_assembly: Optional[str] = None,
        bin_size: Optional[int] = None,
        coordinate_status: str = "contacts, not xyz coordinates",
        **metadata: Any,
    ) -> dict:
        """Record a linked scool contact store in ``uns['linked_scool']``."""
        record = {
            "path": str(self._link_target(path)),
            "format": "scool",
            "cell_name": cell_name,
            "barcode_source": barcode_source,
            "genome_assembly": genome_assembly,
            "bin_size": int(bin_size) if bin_size is not None else None,
            "coordinate_status": coordinate_status,
            **metadata,
        }
        record = _clean_metadata_record(record)
        _set_linked_record(self.uns, "linked_scool", key, record)
        return record

    def _links_from(self):
        """The store whose linked files and embedded copies this object reads: the store it was read from,
        or — for a subset or a copy — its parent's (``_link_origin``)."""
        src = getattr(self, "_source_path", None)
        return src if src is not None else getattr(self, "_link_origin", None)

    def resolve_link_path(self, path: PathLike) -> Path:
        """Linked-file path; relative paths resolve against the directory of
        the store this object was read from (else the working directory),
        so a dataset folder can be moved or shipped as a whole."""
        p = Path(path).expanduser()
        src = self._links_from()
        if isinstance(src, str):      # remote store (URL): links do not resolve against it
            return p
        if not p.is_absolute() and src is not None:
            p = Path(src).parent / p
        return p

    def _link_target(self, path: PathLike) -> Path:
        """The path to record for a new link: as given, except a relative path that names a file under the
        working directory but not under the store this object was read from — the file the caller means —
        which is made absolute (relative links otherwise resolve against the store, :meth:`resolve_link_path`)."""
        p = Path(path).expanduser()
        if not p.is_absolute() and self._links_from() is not None and not self.resolve_link_path(p).exists() \
                and p.exists():
            return p.resolve()
        return p

    def link_cool(
        self,
        path: PathLike,
        *,
        key: str = "default",
        label: Optional[str] = None,
        genome_assembly: Optional[str] = None,
        **metadata: Any,
    ) -> dict:
        """Record a linked bulk / pseudo-bulk ``.cool`` or ``.mcool`` in
        ``uns['linked_cool']`` (the counterpart of :meth:`link_scool` for
        one matrix per file).  The file stays external.  A relative path resolves against the store the
        object was read from (else the working directory); one that only exists under the working directory
        is recorded as an absolute path."""
        path = self._link_target(path)
        record = {
            "path": str(path),
            "format": "mcool" if path.suffix == ".mcool" else "cool",
            "label": label or path.stem,
            "genome_assembly": genome_assembly or self.uns.get("genome_assembly"),
            **metadata,
        }
        record = _clean_metadata_record(record)
        _set_linked_record(self.uns, "linked_cool", key, record)
        return record

    def embedded_links(self) -> Dict[str, Dict[str, str]]:
        """Copies embedded in the store (:mod:`chromdata.embedded`): ``{"contacts": {key: group},
        "anndata": {...}, "images": {...}}`` (empty for a store without them or a non-directory store)."""
        src = self._links_from()
        if src is None or not (isinstance(src, str) or Path(src).is_dir() or str(src).lower().endswith(".cdz")):
            return {"contacts": {}, "anndata": {}, "images": {}}
        from .embedded import list_embedded, list_embedded_anndata, list_embedded_images

        loc = str(src)
        return {"contacts": list_embedded(loc), "anndata": list_embedded_anndata(loc), "images": list_embedded_images(loc)}

    def _embedded_export_dir(self) -> Path:
        """Scratch directory (removed at exit) for cooler files exported from embedded maps — one per store,
        shared by the objects that read it (subsets and copies included), so a map is exported once."""
        key = str(self._links_from())
        d = _EXPORT_DIRS.get(key)
        if d is None:
            import atexit
            import shutil
            import tempfile

            d = Path(tempfile.mkdtemp(prefix="uchrom-embedded-"))
            atexit.register(shutil.rmtree, d, True)
            _EXPORT_DIRS[key] = d
        return d

    def linked_cool_path(self, key: str = "default", *, resolution: Optional[int] = None) -> str:
        """Path of the linked ``.cool`` / ``.mcool`` ``key``; when the file is gone but the map is embedded
        in the store, it is exported once to a scratch ``.mcool`` and that path is returned — with
        ``resolution``, a ``.mcool`` of that level only (much faster for a coarse level of a genome-wide
        map)."""
        record = _linked_record(self.uns.get("linked_cool"), key)
        path = record.get("path")
        if path and self.resolve_link_path(path).exists():
            return str(self.resolve_link_path(path))
        if key in self.embedded_links()["contacts"]:
            from .embedded import export_mcool

            d = self._embedded_export_dir()
            out = d / f"{key}.mcool".replace("/", "_")
            if out.exists():
                return str(out)
            if resolution is not None:
                out = d / f"{key}@{int(resolution)}.mcool".replace("/", "_")
                if not out.exists():
                    export_mcool(str(self._links_from()), key, out, resolutions=[int(resolution)])
                return str(out)
            export_mcool(str(self._links_from()), key, out)
            return str(out)
        raise FileNotFoundError(f"linked_cool {key!r}: {path!r} does not exist and the map is not embedded in the store")

    def load_linked_cool(self, key: str = "default", *, resolution: Optional[int] = None):
        """The linked bulk / pseudo-bulk map ``key`` as a ``cooler.Cooler`` (one resolution of an ``.mcool``:
        ``resolution=``, default the finest); from the embedded copy when the file is gone
        (:meth:`linked_cool_path`)."""
        import cooler

        path = self.linked_cool_path(key, resolution=resolution)
        uris = cooler.fileops.list_coolers(path)
        if "/" not in uris:                              # several resolutions (/resolutions/<r>)
            res = sorted(int(u.rsplit("/", 1)[-1]) for u in uris)
            r = int(resolution) if resolution is not None else res[0]
            if r not in res:
                raise ValueError(f"linked_cool {key!r}: no resolution {r} (have {res})")
            return cooler.Cooler(f"{path}::/resolutions/{r}")
        return cooler.Cooler(path)

    def linked_scool_path(self, key: str = "default", *, cells: Optional[Sequence[str]] = None,
                          trans: bool = True) -> str:
        """Path of the linked per-cell ``.scool`` ``key`` (the file itself when it exists: all its cells).
        When the file is gone but the map is embedded in the store (an atlas store), the cells — all, or
        ``cells`` — are exported once to a scratch ``.scool`` (:func:`chromdata.embedded.export_scool`, one
        read per chromosome; ``trans=False`` leaves out the contacts between chromosomes) and that path is
        returned."""
        record = _linked_record(self.uns.get("linked_scool"), key)
        path = record.get("path")
        if path and self.resolve_link_path(path).exists():
            return str(self.resolve_link_path(path))
        if key in self.embedded_links()["contacts"]:
            import hashlib

            from .embedded import export_scool

            tag = "all" if cells is None else hashlib.md5("\n".join(map(str, cells)).encode()).hexdigest()[:12]
            out = self._embedded_export_dir() / f"{key}.{tag}{'' if trans else '.cis'}.scool".replace("/", "_")
            if not out.exists():
                export_scool(str(self._links_from()), key, out,
                             cells=None if cells is None else [str(c) for c in cells], trans=trans)
            return str(out)
        raise FileNotFoundError(f"linked_scool {key!r}: {path!r} does not exist and the map is not embedded in the store")

    def load_linked_scool(self, *, key: str = "default", cell: Optional[str] = None):
        """Load metadata or one cell cooler from a linked scool file.

        If ``cell`` is ``None``, returns a summary dict with available scool
        cells.  If ``cell`` is supplied, returns ``cooler.Cooler`` for that
        cell group.
        """
        record = _linked_record(self.uns.get("linked_scool"), key)
        path = record.get("path")
        if not path:
            raise ValueError(f"No linked scool path is recorded for key {key!r}.")
        try:
            import cooler
        except ImportError as exc:  # pragma: no cover - cooler is a core dep now
            raise ImportError("cooler is required to load linked scool files.") from exc

        if not self.resolve_link_path(path).exists() and key in self.embedded_links()["contacts"]:
            from .embedded import EmbeddedContacts, export_cool

            loc = str(self._links_from())
            if cell is None:
                cells = EmbeddedContacts(loc, self.embedded_links()["contacts"][key]).cells
                return {"path": None, "cells": [f"/cells/{c}" for c in cells], "record": record, "embedded": True}
            out = self._embedded_export_dir() / f"{key}.{cell}.cool".replace("/", "_")
            if not out.exists():
                export_cool(loc, key, out, cell=str(cell).removeprefix("/cells/"))
            return cooler.Cooler(str(out))

        if cell is None:
            path = str(self.resolve_link_path(path))
            cells = cooler.fileops.list_scool_cells(path)
            return {"path": str(path), "cells": cells, "record": record}

        cell_uri = str(cell)
        if not cell_uri.startswith("/cells/"):
            cell_uri = f"/cells/{cell_uri}"
        return cooler.Cooler(f"{self.resolve_link_path(path)}::{cell_uri}")

    # ------------------------------------------------------------------
    # Cell spatial position (centroids, outlines, linked SpatialData)
    # ------------------------------------------------------------------

    def _cell_ids_axis(self) -> pd.Index:
        ids = self._cells_axis_ids()
        return pd.Index(ids if ids is not None else [str(x) for x in self.cells.index], name="cell_id")

    def _align_cell_rows(self, arr: np.ndarray, cell_ids) -> np.ndarray:
        """Rows of ``arr`` (one per ``cell_ids``) placed on the ``cells`` axis
        (NaN for cells not given); creates ``cells`` when it is empty."""
        if cell_ids is None:
            if len(self.cells) == 0:
                raise ValueError("cell_ids are required when cells is empty.")
            if len(self.cells) != arr.shape[0]:
                raise ValueError("position rows must match cells rows when cell_ids is not provided.")
            return arr
        ids = pd.Index([str(x) for x in cell_ids], name="cell_id")
        if len(ids) != arr.shape[0]:
            raise ValueError("cell_ids length must match the position rows.")
        if ids.has_duplicates:
            raise ValueError("cell_ids must be unique.")
        if len(self.cells) == 0:
            self.cells = pd.DataFrame(index=ids)
            return arr
        positions = self._cell_ids_axis().get_indexer(ids)
        if np.any(positions < 0):
            missing = ids[positions < 0]
            raise ValueError(f"cell_ids are not present in cells: {list(missing[:5])}")
        aligned = np.full((len(self.cells), arr.shape[1]), np.nan, dtype=np.float64)
        aligned[positions] = arr
        return aligned

    def set_cell_positions(
        self,
        positions=None,
        *,
        key: str = "default",
        cell_ids: Optional[Sequence[Any]] = None,
        columns: Optional[Sequence[str]] = None,
        unit: Optional[str] = None,
        frame: Optional[str] = None,
        region_col: Optional[str] = None,
        in_coords_frame: Optional[bool] = None,
        status: str = "measured",
        source: Optional[str] = None,
        method: Optional[str] = None,
        shapes: Optional[str] = None,
        **metadata: Any,
    ) -> dict:
        """Store where each cell is (its centroid, 2-D or 3-D) in ``cells``.

        Cell positions describe cells, not chromatin spots: they are
        ``cells`` columns — ``centroid_x``, ``centroid_y`` [, ``centroid_z``]
        for ``key="default"``, ``<key>_centroid_x`` … otherwise — described
        by the record ``uns['cell_spatial'][key]`` (schema in
        ``packages/chromdata/spec.md``).  Read them back with
        :meth:`cell_positions`.

        Parameters
        ----------
        positions : (n, 2) / (n, 3) array or DataFrame, optional
            Centroids.  A DataFrame uses its ``x, y[, z]`` columns (or its
            first 2 / 3 columns) and, without ``cell_ids``, its index as the
            cell ids.  ``None`` registers existing ``cells`` columns given as
            ``columns`` (e.g. a loader's ``cell_center_x_global``).
        cell_ids : sequence, optional
            Cell of each row; rows are aligned onto the ``cells`` axis (cells
            not given get NaN).  Without it, rows follow ``cells``.
        columns : sequence of str, optional
            ``cells`` column names to write (or to register).
        unit : str, optional
            Length unit (``"um"``, ``"nm"``, ``"px"`` …).
        frame : str, optional
            Coordinate system: ``"fov"`` (local to one field of view — name
            it with ``region_col``), ``"tissue"`` / ``"global"`` (one
            stitched frame per section / sample) or any other name.
        region_col : str, optional
            ``cells`` column naming the region / FOV a local frame belongs to.
        in_coords_frame : bool, optional
            True when the positions share the frame of ``cd.coords``.
        status : {"measured", "inferred"}
            ``"inferred"`` (e.g. mapped by Tangram) needs ``source``.
        source, method : str, optional
            Where the positions come from and how they were obtained.
        shapes : str, optional
            Key of :attr:`cell_shapes` holding the outlines of these cells.
        **metadata
            Kept in the record, e.g. ``voxel_size=[0.103, 0.103, 0.25]`` and
            ``voxel_unit="um"`` for positions stored in voxels (``unit="voxel"``;
            ``cell_positions(physical=True)`` applies them).

        Returns the record.
        """
        from . import cellspatial as _cs

        _cs.check_status(status, source, "set_cell_positions")
        if positions is None:
            if not columns:
                raise ValueError("pass positions, or columns= naming existing cells columns")
            cols = [str(c) for c in columns]
            missing = [c for c in cols if c not in self.cells.columns]
            if missing:
                raise KeyError(f"columns {missing} are not in cd.cells")
            if len(cols) not in (2, 3):
                raise ValueError("columns must name 2 or 3 columns (x, y[, z])")
        else:
            if isinstance(positions, pd.DataFrame):
                if cell_ids is None:
                    cell_ids = [str(x) for x in positions.index]
                use = ([c for c in ("x", "y", "z") if c in positions.columns]
                       if {"x", "y"} <= set(positions.columns) else list(positions.columns[:3]))
                arr = positions[use].to_numpy(dtype=np.float64)
            else:
                arr = np.asarray(positions, dtype=np.float64)
            if arr.ndim != 2 or arr.shape[1] not in (2, 3):
                raise ValueError("positions must have shape (n_cells, 2) or (n_cells, 3).")
            if columns and len(columns) != arr.shape[1]:
                raise ValueError(f"columns names {len(columns)} columns for {arr.shape[1]}-D positions")
            arr = self._align_cell_rows(arr, cell_ids)
            cols = [str(c) for c in columns] if columns else list(_cs.centroid_columns(key, arr.shape[1]))
            for j, c in enumerate(cols):
                self.cells[c] = arr[:, j]
        if region_col is not None and region_col not in self.cells.columns:
            raise KeyError(f"region_col {region_col!r} is not a cells column")
        if shapes is not None and shapes not in self.cell_shapes:
            raise KeyError(f"no cell_shapes[{shapes!r}]")
        record = {
            "x_col": cols[0], "y_col": cols[1], "z_col": cols[2] if len(cols) == 3 else None,
            "ndim": len(cols), "unit": unit, "frame": frame, "region_col": region_col,
            "in_coords_frame": None if in_coords_frame is None else bool(in_coords_frame),
            "status": status, "source": source, "method": method, "shapes": shapes,
            **metadata,
        }
        record = _clean_metadata_record(record)
        _set_linked_record(self.uns, _cs.POSITIONS_FAMILY, key, record)
        return record

    def cell_positions(self, key: str = "default", *, physical: bool = False) -> pd.DataFrame:
        """Cell centroids as a DataFrame indexed by ``cell_id``: ``x``, ``y``
        [, ``z``] (float, NaN where unknown) [+ ``region``]; the record
        (unit, frame, status, …) is in ``.attrs['cell_spatial']``.

        Reads the record ``uns['cell_spatial'][key]`` (1.x records and their
        ``spatial_x`` / ``spatial_y`` columns included).  Without a record,
        ``key="default"`` falls back to known column names —
        ``centroid_x/y/z``, then the older ``x_centroid/y_centroid/z_centroid``
        and ``spatial_x/spatial_y`` — with ``status`` unknown
        (``attrs['cell_spatial']['unrecorded'] is True``).  ``KeyError`` when
        there is no position set.  ``physical=True`` converts positions
        stored in voxels (record ``voxel_size`` / ``voxel_unit``) to physical
        units.
        """
        from . import cellspatial as _cs

        records = _linked_records(self.uns.get(_cs.POSITIONS_FAMILY))
        if key in records and records[key].get("x_col"):
            rec = _cs.normalize_record(records[key])
        elif key == "default" and len(self.cells):
            found = _cs.legacy_columns(self.cells)
            if found is None:
                raise KeyError("no cell positions: no uns['cell_spatial'] record and no centroid columns")
            rec = {"x_col": found[0], "y_col": found[1], "z_col": found[2],
                   "ndim": 3 if found[2] else 2, "unrecorded": True}
            rec = {k: v for k, v in rec.items() if v is not None}
        else:
            raise KeyError(f"no cell position set {key!r}; known: {sorted(records)}")
        return _cs.positions_frame(self.cells, self._cell_ids_axis(), rec, physical=physical)

    def set_cell_spatial_coordinates(
        self,
        xy: np.ndarray,
        *,
        key: str = "default",
        cell_ids: Optional[List[str]] = None,
        x_col: Optional[str] = None,
        y_col: Optional[str] = None,
        source: Optional[str] = None,
        method: Optional[str] = None,
        coordinate_system: Optional[str] = None,
        inferred: bool = True,
        **metadata: Any,
    ) -> dict:
        """Deprecated: use :meth:`set_cell_positions`.

        Kept for 1.x callers: ``coordinate_system`` becomes ``frame``,
        ``inferred`` the ``status``, ``x_col`` / ``y_col`` the column names.
        Columns now default to the schema names (``centroid_x`` …, was
        ``spatial_x`` …); positions written by older versions stay readable
        through :meth:`cell_positions`.
        """
        import warnings

        from . import cellspatial as _cs

        warnings.warn(
            "set_cell_spatial_coordinates() is deprecated; use set_cell_positions(positions, "
            "frame=..., unit=..., status='measured' | 'inferred', source=...)",
            DeprecationWarning, stacklevel=2,
        )
        arr = np.asarray(xy, dtype=np.float64)
        if arr.ndim != 2 or arr.shape[1] != 2:
            raise ValueError("xy must have shape (n_cells, 2).")
        columns = None
        if x_col or y_col:
            default = _cs.centroid_columns(key, 2)
            columns = [x_col or default[0], y_col or default[1]]
        status = "inferred" if inferred else "measured"
        if status == "inferred" and not source:
            source = method or "unspecified"
        return self.set_cell_positions(arr, key=key, cell_ids=cell_ids, columns=columns, frame=coordinate_system,
                                       status=status, source=source, method=method, **metadata)

    def set_cell_shapes(
        self,
        shapes,
        *,
        key: str = "cell",
        cell_ids: Optional[Sequence[Any]] = None,
        unit: Optional[str] = None,
        frame: Optional[str] = None,
        in_coords_frame: Optional[bool] = None,
        status: str = "measured",
        source: Optional[str] = None,
        method: Optional[str] = None,
        **metadata: Any,
    ) -> dict:
        """Store cell outlines (polygons) as ``cell_shapes[key]``.

        ``shapes``: a GeoDataFrame / GeoSeries (index = cell ids), a
        DataFrame with ``cell_id`` + WKB ``geometry``, a mapping ``cell_id →
        shape``, or a sequence (with ``cell_ids``) of shapely geometries, WKB
        bytes or ``(n, 2)`` / ``(n, 3)`` vertex arrays of the exterior ring.
        Vertex arrays and WKB need no geometry library; shapely / geopandas
        are only needed to read them back as geometries
        (:meth:`cell_shapes_geodataframe`).  Common keys: ``"cell"``
        (segmented cell boundary), ``"nucleus"``.  Frame / unit / status are
        recorded in ``uns['cell_shapes'][key]`` (the same fields as
        :meth:`set_cell_positions`).  Stored as GeoParquet
        (``tables/cell_shapes/<key>.parquet``) in ``.chromdata.zarr`` /
        ``.cdz``.  Returns the record.
        """
        from . import cellspatial as _cs

        _cs.check_status(status, source, "set_cell_shapes")
        if not key or "/" in key:
            raise ValueError(f"cell_shapes key must be non-empty without '/': {key!r}")
        df = _cs.to_wkb(shapes, cell_ids)
        self.cell_shapes[key] = df
        record = {
            "geometry_types": sorted({_cs.wkb_type(w) for w in df["geometry"]}),
            "n": int(len(df)), "unit": unit, "frame": frame,
            "in_coords_frame": None if in_coords_frame is None else bool(in_coords_frame),
            "status": status, "source": source, "method": method, **metadata,
        }
        record = _clean_metadata_record(record)
        _set_linked_record(self.uns, _cs.SHAPES_FAMILY, key, record)
        return record

    def set_clusters(self, key: str, data, **kwargs) -> ClusterTable:
        """Store multi-way contacts as ``clusters[key]``.

        ``data`` is a :class:`~chromdata.clusters.ClusterTable` or a frame
        with one row per fragment (cluster label, ``chrom``, ``start``,
        ``end`` [, cell id]); a frame goes through
        :meth:`ClusterTable.from_frame` with ``kwargs`` (``cell=``,
        ``member_columns=``, …), the chromosome order of :attr:`bins` and,
        for per-cell data, the cell order of :attr:`cells` (cells absent
        from it are appended).  Saved as ``clusters/<key>/`` in
        ``.chromdata.zarr`` / ``.cdz`` (format 2.4); a large table built
        after the store can be added with
        :func:`chromdata.clusters.add_clusters`.
        """
        if not key or "/" in str(key):
            raise ValueError(f"clusters key must be non-empty without '/': {key!r}")
        if isinstance(data, ClusterTable):
            table = data
        elif isinstance(data, pd.DataFrame):
            kw = dict(kwargs)
            chrom_col = kw.get("chrom", "chrom")
            if "chroms" not in kw and len(self.bins):
                known = [str(c) for c in self.bins["chrom"].cat.categories]
                extra = sorted(set(data[chrom_col].astype(str)) - set(known))
                kw["chroms"] = known + extra
            cell_col = kw.get("cell")
            if cell_col and "cells" not in kw and len(self.cells):
                known = [str(c) for c in self.cells.index]
                seen = set(known)
                extra = sorted({str(c) for c in pd.unique(data[cell_col])} - seen)
                kw["cells"] = known + extra
            table = ClusterTable.from_frame(data, **kw)
        else:
            raise TypeError(f"clusters need a ClusterTable or a DataFrame, not {type(data).__name__}")
        self.clusters[str(key)] = table
        return table

    def cell_shapes_geodataframe(self, key: str = "cell"):
        """``cell_shapes[key]`` as a ``geopandas.GeoDataFrame`` indexed by
        ``cell_id`` (needs shapely + geopandas; the record is in
        ``.attrs['cell_shapes']``)."""
        from . import cellspatial as _cs

        if key not in self.cell_shapes:
            raise KeyError(f"no cell_shapes[{key!r}]; known: {sorted(self.cell_shapes)}")
        meta = _linked_records(self.uns.get(_cs.SHAPES_FAMILY)).get(key)
        return _cs.shapes_geodataframe(self.cell_shapes[key], meta)

    def link_spatialdata(
        self,
        path: PathLike,
        *,
        key: str = "default",
        table: Optional[str] = None,
        region: Optional[Any] = None,
        region_key: Optional[str] = None,
        instance_key: Optional[str] = None,
        cell_col: Optional[str] = None,
        coordinate_system: Optional[str] = None,
        read_attrs: bool = True,
        **metadata: Any,
    ) -> dict:
        """Record a linked SpatialData zarr store in ``uns['linked_spatialdata']``.

        The store stays external (images, labels, shapes, other tables).  The
        cell map joins its annotating ``table`` to ChromData cells: rows
        whose ``region_key`` column equals ``region`` are cells, and their
        ``instance_key`` value equals the ChromData ``cell_id`` — or the value
        of the ``cells`` column ``cell_col`` when the ids differ.  With
        ``read_attrs`` (and spatialdata installed) ``table`` / ``region`` /
        ``region_key`` / ``instance_key`` default to the table's
        ``spatialdata_attrs``.  Relative paths resolve against the directory
        of the ChromData store (as for :meth:`link_scool`).
        """
        from . import cellspatial as _cs

        if cell_col is not None and cell_col not in self.cells.columns:
            raise KeyError(f"cell_col {cell_col!r} is not a cells column")
        version = None
        resolved = self.resolve_link_path(path)
        if read_attrs and resolved.exists():
            try:
                sd = _cs.require_spatialdata()
            except ImportError:
                sd = None
            if sd is not None:
                version = getattr(sd, "__version__", None)
                name, attrs, names = _cs.spatialdata_table_attrs(resolved, table)
                if name is None and len(names) > 1:
                    raise ValueError(f"the SpatialData store has several tables {names}; pass table=")
                table = table or name
                region = region if region is not None else attrs.get("region")
                region_key = region_key or attrs.get("region_key")
                instance_key = instance_key or attrs.get("instance_key")
        record = {
            "path": str(path), "format": "spatialdata", "table": table,
            "region": list(region) if isinstance(region, (list, tuple)) else region,
            "region_key": region_key, "instance_key": instance_key, "cell_col": cell_col,
            "coordinate_system": coordinate_system, "spatialdata_version": version,
            **metadata,
        }
        record = _clean_metadata_record(record)
        _set_linked_record(self.uns, _cs.SPATIALDATA_FAMILY, key, record)
        return record

    def load_linked_spatialdata(self, *, key: str = "default", cells: Optional[Sequence[Any]] = None,
                                elements: Optional[Sequence[str]] = None):
        """The linked SpatialData object (``spatialdata`` needed).

        ``cells`` (ChromData cell ids) subsets the annotating table and the
        elements it annotates to those cells
        (``spatialdata.match_sdata_to_table``); ``elements`` reads only the
        named elements (plus the tables).
        """
        from . import cellspatial as _cs

        record = _linked_record(self.uns.get(_cs.SPATIALDATA_FAMILY), key)
        if not record.get("path"):
            raise ValueError(f"No linked SpatialData path is recorded for key {key!r}.")
        return _cs.load_spatialdata(self, record, cells=cells, elements=elements)

    def to_spatialdata(self, *, positions_key: str = "default", shapes_key: Optional[str] = None,
                       spots: bool = True, points: bool = True, cell_table: bool = True,
                       coordinate_system: Optional[str] = None):
        """Export to a :class:`spatialdata.SpatialData` (spatialdata +
        geopandas needed): spots as a 3-D points element ``spots`` (with
        chrom / start / end / bin_id / trace_id / cell_id columns), each
        ``points[key]`` as ``points_<key>``, the cell centroids as points
        ``cell_centroids``, the outlines ``cell_shapes[key]`` as a shapes
        element ``cell_shapes_<key>``, and ``cells`` (+ ``cellm`` in obsm) as
        the table ``cells`` annotating the outlines.  Spots and cell
        positions get separate coordinate systems (``"spots"`` and the
        position frame); the unit and the records are in
        ``sdata.attrs['uchrom']``."""
        from . import cellspatial as _cs

        return _cs.to_spatialdata(self, positions_key=positions_key, shapes_key=shapes_key, spots=spots,
                                  points=points, cell_table=cell_table, coordinate_system=coordinate_system)

    def coord_status(self) -> dict:
        """Return a compact status summary for ``coords``."""
        total = int(self.coords.size)
        finite = int(np.isfinite(self.coords).sum())
        nan = int(np.isnan(self.coords).sum())
        if total == 0:
            status = "empty"
        elif finite == total:
            status = "complete"
        elif nan == total:
            status = "unavailable_all_nan"
        else:
            status = "partially_missing"
        return {"status": status, "total_values": total, "finite_values": finite, "nan_values": nan}

    def describe_links(self) -> dict:
        """Summarize linked external modality records."""
        return {
            "coord_status": self.coord_status(),
            "linked_anndata": dict(self.uns.get("linked_anndata", {}) or {}),
            "linked_mudata": _linked_records(self.uns.get("linked_mudata")),
            "linked_scool": _linked_records(self.uns.get("linked_scool")),
            "linked_cool": _linked_records(self.uns.get("linked_cool")),
            "cell_spatial": _linked_records(self.uns.get("cell_spatial")),
            "cell_shapes": _linked_records(self.uns.get("cell_shapes")),
            "linked_spatialdata": _linked_records(self.uns.get("linked_spatialdata")),
        }

    def validate_links(self, *, check_files: bool = True) -> List[str]:
        """Return issues found in linked external modality metadata."""
        issues: List[str] = []
        coord = self.coord_status()
        declared = self.uns.get("coordinate_status") or self.uns.get("coords_status")
        if coord["status"] == "unavailable_all_nan" and not declared:
            issues.append(
                "coords are all NaN but uns['coordinate_status'] or uns['coords_status'] is not set"
            )

        embedded = self.embedded_links()["contacts"] if check_files else {}
        for family, expected_format in (("linked_mudata", "h5mu"), ("linked_scool", "scool"),
                                        ("linked_cool", "cool|mcool"), ("linked_spatialdata", "spatialdata")):
            records = _linked_records(self.uns.get(family))
            for key, record in records.items():
                path = record.get("path")
                if not path:
                    issues.append(f"{family}.{key} missing path")
                    continue
                if (check_files and not self.resolve_link_path(path).exists()
                        and not (family in ("linked_scool", "linked_cool") and key in embedded)):
                    issues.append(f"{family}.{key} path does not exist: {path}")
                fmt = record.get("format")
                if fmt and str(fmt) not in expected_format.split("|"):
                    issues.append(f"{family}.{key} format={fmt!r} != {expected_format!r}")

        for key, record in _linked_records(self.uns.get("linked_scool")).items():
            if record.get("coordinate_status") in {None, ""}:
                issues.append(f"linked_scool.{key} missing coordinate_status")
            if check_files and record.get("path") and self.resolve_link_path(record["path"]).exists():
                try:
                    import cooler

                    if not cooler.fileops.is_scool_file(str(self.resolve_link_path(record["path"]))):
                        issues.append(f"linked_scool.{key} is not a valid scool file")
                except ImportError:
                    issues.append("cooler is not installed; linked_scool validity could not be checked")

        issues += self._validate_cell_spatial(check_files=check_files)
        return issues

    def _validate_cell_spatial(self, *, check_files: bool) -> List[str]:
        """Issues of the cell-position / cell-shape records and of the linked
        SpatialData stores (their table, instance key and cell map)."""
        from . import cellspatial as _cs

        issues: List[str] = []
        for key, raw in _linked_records(self.uns.get(_cs.POSITIONS_FAMILY)).items():
            rec = _cs.normalize_record(raw)
            cols = [rec.get("x_col"), rec.get("y_col")] + ([rec["z_col"]] if rec.get("z_col") else [])
            missing = [c for c in cols if not c or c not in self.cells.columns]
            if missing:
                issues.append(f"cell_spatial.{key} columns missing from cells: {missing}")
            if rec.get("status") not in _cs.STATUSES:
                issues.append(f"cell_spatial.{key} status={rec.get('status')!r} not in {_cs.STATUSES}")
            elif rec["status"] == "inferred" and not rec.get("source"):
                issues.append(f"cell_spatial.{key} is inferred but has no source")
            if rec.get("shapes") and rec["shapes"] not in self.cell_shapes:
                issues.append(f"cell_spatial.{key} names missing cell_shapes[{rec['shapes']!r}]")
        shape_recs = _linked_records(self.uns.get(_cs.SHAPES_FAMILY))
        for key in self.cell_shapes:
            if key not in shape_recs:
                issues.append(f"cell_shapes[{key!r}] has no uns['cell_shapes'] record")
        for key, rec in _linked_records(self.uns.get(_cs.SPATIALDATA_FAMILY)).items():
            for field in ("table", "instance_key"):
                if not rec.get(field):
                    issues.append(f"linked_spatialdata.{key} missing {field} (the cell map)")
            path = rec.get("path")
            if not (check_files and path and rec.get("table") and rec.get("instance_key")
                    and self.resolve_link_path(path).exists()):
                continue
            try:
                ids = _cs.spatialdata_instances(self.resolve_link_path(path), rec["table"], rec["instance_key"],
                                                rec.get("region_key"), rec.get("region"))
            except ImportError:
                issues.append("spatialdata is not installed; linked_spatialdata could not be checked")
                continue
            except Exception as exc:  # unreadable store, missing table / column
                issues.append(f"linked_spatialdata.{key} unreadable: {type(exc).__name__}: {exc}")
                continue
            if rec.get("cell_col"):
                if rec["cell_col"] not in self.cells.columns:
                    issues.append(f"linked_spatialdata.{key} cell_col {rec['cell_col']!r} is not a cells column")
                    continue
                ours = pd.Index(self.cells[rec["cell_col"]].dropna().astype(str))
            else:
                ours = self._cell_ids_axis() if len(self.cells) else self._spot_cell_ids()
            found = ours.isin(set(ids))
            if len(ours) and not found.any():
                issues.append(f"linked_spatialdata.{key}: no ChromData cell matches a "
                              f"{rec['instance_key']!r} value of table {rec['table']!r}")
            elif not found.all():
                issues.append(f"linked_spatialdata.{key}: {int((~found).sum())} of {len(ours)} ChromData "
                              f"cells have no row in table {rec['table']!r}")
        return issues

    @property
    def dataset_references(self) -> List[dict]:
        """Dataset-level source references used as auto-discovery priors.

        References are stored in ``uns['dataset_references']`` and round-trip
        with the store.  They are intended for primary dataset papers,
        data repositories, supplementary tables, method papers, and related
        biological priors.
        """
        return self._metadata_records("dataset_references")

    @property
    def user_annotations(self) -> List[dict]:
        """User-provided discovery context and analysis constraints.

        Annotations are stored in ``uns['user_annotations']`` and are treated
        as user-supplied priors or constraints by discovery agents, not as
        validated data evidence.
        """
        return self._metadata_records("user_annotations")

    def add_reference(
        self,
        *,
        reference_id: Optional[str] = None,
        role: str = "user_supplied_reference",
        title: Optional[str] = None,
        doi: Optional[str] = None,
        pmid: Optional[str] = None,
        url: Optional[str] = None,
        year: Optional[int] = None,
        notes: Optional[str] = None,
        **extra: Any,
    ) -> dict:
        """Add a source reference to ``uns['dataset_references']``.

        Parameters are intentionally metadata-oriented rather than tied to one
        publication database.  ``role`` should describe how the reference
        relates to the dataset, for example ``'primary_dataset_paper'``,
        ``'data_repository'``, ``'supplementary_table'``, or
        ``'related_biology_prior'``.
        """
        record = {
            "reference_id": reference_id,
            "role": role,
            "title": title,
            "doi": doi,
            "pmid": pmid,
            "url": str(url) if url is not None else None,
            "year": int(year) if year is not None else None,
            "notes": notes,
            **extra,
        }
        record = _clean_metadata_record(record)
        if "reference_id" not in record:
            record["reference_id"] = _stable_metadata_id("ref", record)
        self.dataset_references.append(record)
        return record

    def add_user_annotation(
        self,
        *,
        annotation_id: Optional[str] = None,
        scope: str,
        text: str,
        target: Optional[str] = None,
        tags: Optional[List[str]] = None,
        confidence: str = "user_asserted",
        **extra: Any,
    ) -> dict:
        """Add a user annotation to ``uns['user_annotations']``.

        Use annotations for cell-type notes, marker priors, analysis
        constraints, hypothesis seeds, negative constraints, field semantics,
        or quality warnings.  They are surfaced in the discovery schema and
        agent context but still require notebook validation before becoming
        evidence.
        """
        record = {
            "annotation_id": annotation_id,
            "scope": scope,
            "target": target,
            "text": text,
            "tags": tags or [],
            "confidence": confidence,
            **extra,
        }
        record = _clean_metadata_record(record)
        if "annotation_id" not in record:
            record["annotation_id"] = _stable_metadata_id("ann", record)
        self.user_annotations.append(record)
        return record

    def _metadata_records(self, key: str) -> List[dict]:
        raw = self.uns.get(key)
        if raw is None:
            self.uns[key] = []
            return self.uns[key]
        if isinstance(raw, Mapping):
            records = [_clean_metadata_record(dict(raw))]
        elif isinstance(raw, list):
            records = [_clean_metadata_record(item) for item in raw]
        elif isinstance(raw, tuple):
            records = [_clean_metadata_record(item) for item in raw]
        else:
            raise TypeError(f"uns['{key}'] must be a list of records, got {type(raw).__name__}")
        self.uns[key] = records
        return records

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
        self._check_bin_ids()
        if len(self._bin_tracks) != self.n_bins:
            raise ValueError(f"bin_tracks rows ({len(self._bin_tracks)}) != n_bins ({self.n_bins})")
        if len(self._spot_tracks) != self.n_spots:
            raise ValueError(f"spot_tracks rows ({len(self._spot_tracks)}) != n_spots ({self.n_spots})")
        for key, arr in self.binm.items():
            arr = np.asarray(arr)
            if arr.ndim == 0 or arr.shape[0] != self.n_bins:
                raise ValueError(f"binm['{key}'] first axis must be n_bins ({self.n_bins})")
        cell_axis_len = len(self.cells) if len(self.cells) > 0 else self.n_cells
        for key, arr in self.cellm.items():
            arr = np.asarray(arr)
            if arr.ndim == 0:
                raise ValueError(f"cellm['{key}'] must have at least one dimension")
            if cell_axis_len > 0 and arr.shape[0] != cell_axis_len:
                raise ValueError(
                    f"cellm['{key}'] rows ({arr.shape[0]}) != n_cells ({cell_axis_len})"
                )
        for key, arr in self.layers.items():
            if arr.shape != self.coords.shape:
                raise ValueError(
                    f"layers['{key}'] shape {arr.shape} != coords shape {self.coords.shape}"
                )
        for key, df in self.points.items():
            if not isinstance(df, pd.DataFrame):
                raise TypeError(f"points['{key}'] must be a DataFrame")
            missing = [c for c in ("x", "y", "z") if c not in df.columns]
            if missing:
                raise ValueError(f"points['{key}'] missing coordinate columns {missing}")
        for key, df in self.cell_shapes.items():
            if not isinstance(df, pd.DataFrame) or not {"cell_id", "geometry"} <= set(df.columns):
                raise ValueError(f"cell_shapes['{key}'] must be a DataFrame with cell_id and geometry (WKB)")
        for key, table in self.clusters.items():
            if not isinstance(table, ClusterTable):
                raise TypeError(f"clusters['{key}'] must be a ClusterTable, not {type(table).__name__}")

    def _categorify(self):
        for col in _CATEGORICAL_COLUMNS:
            if col in self.spots.columns and not hasattr(self.spots[col].dtype, "categories"):
                self.spots[col] = self.spots[col].astype("category")

    # ------------------------------------------------------------------
    # Subsetting
    # ------------------------------------------------------------------

    def __getitem__(self, index) -> "ChromData":
        return self._take(index)

    def _take(self, index, columns=None, tracks=None) -> "ChromData":
        """Rows ``index`` (slice, integer or boolean array) as a new object,
        with an optional ``columns`` / ``tracks`` selection
        (:func:`resolve_selection`)."""
        if isinstance(index, slice):
            index = np.arange(*index.indices(self.n_spots))
        if isinstance(index, (pd.Series, np.ndarray)):
            if index.dtype == bool:
                index = np.where(index)[0]
        idx = np.asarray(index)
        if idx.dtype.kind not in "iu":
            idx = idx.astype(np.int64)

        spot_cols, track_cols, layer_keys = resolve_selection(
            list(self.spots.columns), list(self._spot_tracks.columns), list(self.layers),
            columns, tracks)
        new_coords = self.coords[idx]
        spots = self.spots if len(spot_cols) == len(self.spots.columns) else self.spots[spot_cols]
        new_spots = spots.iloc[idx].reset_index(drop=True)
        st = self._spot_tracks
        if len(track_cols) != len(st.columns):
            st = st[track_cols] if track_cols else _empty_frame(len(st))
        new_spot_tracks = st.iloc[idx].reset_index(drop=True)
        new_layers = {k: self.layers[k][idx] for k in layer_keys}

        # Filter traces/cells to those still referenced
        new_traces = self._filter_traces(new_spots)
        new_cells, new_cellm = self._filter_cells(new_spots)
        new_points = self._filter_points(new_spots)
        new_shapes = self._filter_cell_shapes(new_spots)

        out = ChromData(
            new_coords,
            new_spots,
            bins=self._bins,
            cells=new_cells,
            cellm=new_cellm,
            binm=self.binm,
            intervals=self._intervals,
            traces=new_traces,
            layers=new_layers,
            results=self.results,
            uns=self.uns,
            points=new_points,
            cell_shapes=new_shapes,
            clusters=self.clusters,
            linked_adata=None,
            validate=False,
        )
        out._bin_tracks = self._bin_tracks
        out._spot_tracks = new_spot_tracks
        out._link_origin = self._links_from()
        if self._spot_view_order and len(track_cols) != len(self._spot_tracks.columns):
            keep = set(self._bin_tracks.columns) | set(track_cols)
            out._spot_view_order = [c for c in self._spot_view_order if c in keep] or None
        else:
            out._spot_view_order = self._spot_view_order
        return out

    def _filter_points(self, spots: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """Keep points of the cells that still have spots (sets without a
        ``cell_id`` column, or data without cells, are kept whole)."""
        if not self.points or "cell_id" not in spots.columns:
            return dict(self.points)
        keep = {str(x) for x in spots["cell_id"].unique()}
        out = {}
        for key, df in self.points.items():
            if "cell_id" in df.columns:
                df = df[df["cell_id"].astype(str).isin(keep)].reset_index(drop=True)
            out[key] = df
        return out

    def _filter_cell_shapes(self, spots: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """Keep the outlines of the cells that still have spots."""
        if not self.cell_shapes or "cell_id" not in spots.columns:
            return dict(self.cell_shapes)
        keep = {str(x) for x in spots["cell_id"].unique()}
        return {k: df[df["cell_id"].astype(str).isin(keep)].reset_index(drop=True)
                for k, df in self.cell_shapes.items()}

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
        keep = {str(x) for x in spots["cell_id"].unique()}
        axis_ids = self._cells_axis_ids()
        if axis_ids is None:
            return self.cells, self.cellm
        mask = axis_ids.isin(keep)
        new_cells = self.cells[mask]
        new_cellm = {}
        for k, v in self.cellm.items():
            new_cellm[k] = v[mask.values] if hasattr(mask, "values") else v[mask]
        return new_cells, new_cellm

    def _spot_cell_ids(self) -> pd.Index:
        if "cell_id" not in self.spots.columns:
            return pd.Index([], name="cell_id")
        return pd.Index([str(x) for x in self.spots["cell_id"].unique()], name="cell_id")

    def _cells_axis_ids(self) -> Optional[pd.Index]:
        """Return the cell ids that define rows of cells/cellm, if known."""
        if len(self.cells) == 0:
            return None

        spot_ids = set(self._spot_cell_ids())
        candidates = []
        if not isinstance(self.cells.index, pd.RangeIndex) or self.cells.index.name is not None:
            candidates.append(self.cells.index)
        for col in ("cell_id", "cell_name"):
            if col in self.cells.columns:
                candidates.append(self.cells[col])

        for values in candidates:
            ids = pd.Index([str(x) for x in values], name="cell_id")
            if not spot_ids or spot_ids.intersection(set(ids)):
                return ids

        if len(self.cells) == len(self._spot_cell_ids()):
            return self._spot_cell_ids()
        return pd.Index([str(x) for x in self.cells.index], name="cell_id")

    def get_cell(self, cell_id, *, columns=None, tracks=None) -> "ChromData":
        """The spots of one cell (a new object).

        ``columns`` / ``tracks`` select the spot-aligned columns to keep —
        ``columns="coords"`` keeps the coordinates and the key columns
        only, ``columns=[...]`` adds the named spot columns / spot tracks /
        layers, ``tracks=[...]`` picks spot tracks (see
        :func:`resolve_selection`).  The default keeps everything.  On a
        backed object the selection decides what is read from disk.
        """
        if "cell_id" not in self.spots.columns:
            raise KeyError("spots has no 'cell_id' column")
        mask = self.spots["cell_id"] == cell_id
        return self._keep_requested_cells(self._take(mask.values, columns, tracks), [cell_id])

    def get_cells(self, cell_ids, *, columns=None, tracks=None) -> "ChromData":
        """The spots of several cells (ids compared as strings; unknown ids are
        ignored).  See :meth:`get_cell` for ``columns`` / ``tracks``."""
        if "cell_id" not in self.spots.columns:
            raise KeyError("spots has no 'cell_id' column")
        keep = {str(c) for c in cell_ids}
        mask = self.spots["cell_id"].astype(str).isin(keep)
        return self._keep_requested_cells(self._take(mask.values, columns, tracks), keep)

    def _keep_requested_cells(self, out: "ChromData", ids) -> "ChromData":
        """Cells asked for by id stay in ``cells`` / ``cellm`` of a subset even without spots (sequencing
        data: cells with contact maps or RNA but no coordinates)."""
        axis = self._cells_axis_ids()
        if axis is None:
            return out
        have = out._cells_axis_ids() if len(out.cells) else None
        mask = axis.isin({str(i) for i in ids}) | axis.isin(set(have) if have is not None else set())
        if int(mask.sum()) == len(out.cells):
            return out
        out.cells = self.cells[np.asarray(mask)]
        out.cellm = {k: np.asarray(v)[np.asarray(mask)] for k, v in self.cellm.items()}
        return out

    def get_trace(self, trace_id, *, columns=None, tracks=None) -> "ChromData":
        """The spots of one trace (see :meth:`get_cell` for ``columns`` /
        ``tracks``)."""
        mask = self.spots["trace_id"] == trace_id
        return self._take(mask.values, columns, tracks)

    def get_chrom(self, chrom: str, *, columns=None, tracks=None) -> "ChromData":
        """The spots of one chromosome (see :meth:`get_cell` for ``columns``
        / ``tracks``)."""
        ids = np.where(self._bins["chrom"].astype(str).to_numpy() == str(chrom))[0]
        mask = np.isin(self.spots[BIN_ID].to_numpy(), ids)
        return self._take(mask, columns, tracks)

    # ------------------------------------------------------------------
    # Streaming access (same batches in memory and backed)
    # ------------------------------------------------------------------

    @property
    def backed(self) -> bool:
        """``True`` for a :class:`~chromdata.backed.BackedChromData`."""
        return False

    def to_memory(self, *, columns=None, tracks=None) -> "ChromData":
        """An in-memory ``ChromData``: ``self`` (this object already is), or
        a copy restricted to a ``columns`` / ``tracks`` selection."""
        if columns is None and tracks is None:
            return self
        return self._take(slice(None), columns, tracks)

    def _stream_layout(self):
        """Stored (format 2.1) order of the spots and its runs.

        Returns ``(order, chrom, cell, seg)``: the stable permutation sorting
        spots by (chromosome, cell, trace, bin) (``None`` when already
        sorted), the sorted chromosome / cell codes (cell = -1 without
        ``cell_id``) and the offsets of the (chromosome, cell, trace) runs.
        """
        from .zarrcd import _segments, _spot_keys, sort_order

        cell, trace, bin_id = _spot_keys(self)
        chrom_codes = np.asarray(self._bins["chrom"].cat.codes, dtype=np.int64)
        chrom = chrom_codes[bin_id] if len(bin_id) else np.zeros(0, dtype=np.int64)
        order = sort_order(cell, trace, bin_id, chrom=chrom)
        if order is not None:
            cell, trace, chrom = cell[order], trace[order], chrom[order]
        seg, _ = _segments(cell, trace, chrom)
        return order, chrom, cell, seg

    def _bytes_per_spot(self, columns=None, tracks=None) -> float:
        spot_cols, track_cols, layer_keys = resolve_selection(
            list(self.spots.columns), list(self._spot_tracks.columns), list(self.layers),
            columns, tracks)
        return 3.0 * (8 * 3 + 8 * (len(spot_cols) + len(track_cols)) + 24 * len(layer_keys))

    def iter_traces(self, batch=1024, *, chrom=None, columns=None, tracks=None):
        """Yield in-memory ``ChromData`` chunks of ``batch`` traces.

        Traces are visited in the order a ``.chromdata.zarr`` store holds
        them — chromosome › cell › trace, with the spots of a trace in bin
        order; a trace id shared by several cells (or a trace spanning
        several chromosomes) counts once per (chromosome, cell) run.  A
        backed object yields identical chunks while reading one row range
        per chunk.

        Parameters
        ----------
        batch : int or ``"auto"``
            Traces per chunk; ``"auto"`` sizes chunks from
            :data:`chromdata.settings.memory_budget`.
        chrom : str, optional
            Only the traces of this chromosome.
        columns, tracks
            Column selection of the chunks (see :meth:`get_cell`), e.g.
            ``columns="coords"`` for coordinates and keys only.
        """
        order, chrom_s, _, seg = self._stream_layout()
        lo, hi = 0, len(seg) - 1
        if chrom is not None:
            names = np.asarray(self._bins["chrom"].cat.categories.astype(str))
            codes = np.flatnonzero(names == str(chrom))
            sel = np.flatnonzero(np.isin(chrom_s[seg[:-1]], codes)) if hi else np.zeros(0, np.int64)
            if not len(sel):
                return
            lo, hi = int(sel[0]), int(sel[-1]) + 1
        size = resolve_batch(batch, (seg[hi] - seg[lo]) / max(1, hi - lo),
                             self._bytes_per_spot(columns, tracks))
        for i in range(lo, hi, size):
            a, b = int(seg[i]), int(seg[min(i + size, hi)])
            yield self._take(order[a:b] if order is not None else np.arange(a, b), columns, tracks)

    def iter_cells(self, batch=64, *, columns=None, tracks=None):
        """Yield in-memory ``ChromData`` chunks of ``batch`` cells (cell code
        order; the rows of a chunk in stored order, see :meth:`iter_traces`)."""
        if "cell_id" not in self.spots.columns:
            raise KeyError("spots has no 'cell_id' column")
        order, chrom_s, cell_s, _ = self._stream_layout()
        uniq = np.unique(cell_s[cell_s >= 0])
        if not len(uniq):
            return
        size = resolve_batch(batch, self.n_spots / len(uniq), self._bytes_per_spot(columns, tracks))
        n = len(cell_s)
        bounds = np.r_[0, np.flatnonzero(chrom_s[1:] != chrom_s[:-1]) + 1, n]
        for i in range(0, len(uniq), size):
            c0, c1 = uniq[i], uniq[min(i + size, len(uniq)) - 1]
            rows = []
            for a, b in zip(bounds[:-1], bounds[1:]):
                k0 = a + int(np.searchsorted(cell_s[a:b], c0, side="left"))
                k1 = a + int(np.searchsorted(cell_s[a:b], c1, side="right"))
                if k1 > k0:
                    rows.append(order[k0:k1] if order is not None else np.arange(k0, k1))
            idx = np.concatenate(rows) if rows else np.zeros(0, dtype=np.int64)
            yield self._take(idx, columns, tracks)

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
    # AnnData integration
    # ------------------------------------------------------------------

    def link_anndata(
        self,
        adata,
        *,
        cell_id_col: Optional[str] = None,
        copy_obs: bool = True,
        copy_obsm: bool = True,
    ) -> int:
        """Import cell-level metadata from an AnnData into this ChromData.

        Matches cells by ``cell_id``: each unique value in
        ``spots['cell_id']`` is looked up in ``adata.obs`` (by index, or
        by the column *cell_id_col* if given).  Matched cells get their
        ``adata.obs`` columns merged into ``self.cells`` and their
        ``adata.obsm`` arrays copied into ``self.cellm``.

        If ``self.cells`` already exists, its row order is preserved and
        AnnData rows are aligned onto that cell axis.  This is important
        for multi-omics loaders such as Takei 2025, where chromatin
        tracing coordinates live in ``coords/spots``, RNA/IF signals live
        in spot-level ``tracks``, and mRNA clustering/UMAP already live
        in ``cells`` / ``cellm``.

        Parameters
        ----------
        adata : anndata.AnnData
            The single-cell dataset to link (e.g. scRNA-seq).
        cell_id_col : str, optional
            Column in ``adata.obs`` that holds cell identifiers matching
            ``spots['cell_id']``.  If ``None``, ``adata.obs.index`` is
            used as the key.
        copy_obs : bool
            If True (default), copy ``adata.obs`` columns into
            ``self.cells``.
        copy_obsm : bool
            If True (default), copy ``adata.obsm`` arrays into
            ``self.cellm``.

        Returns
        -------
        int
            Number of cells matched.

        Raises
        ------
        KeyError
            If ``spots`` has no ``cell_id`` column.
        """
        if "cell_id" not in self.spots.columns:
            raise KeyError(
                "spots has no 'cell_id' column — cannot match cells. "
                "Add cell_id to spots before calling link_anndata()."
            )

        cd_cell_ids = self._spot_cell_ids()

        if cell_id_col is not None:
            if cell_id_col not in adata.obs.columns:
                raise KeyError(f"adata.obs has no column '{cell_id_col}'")
            adata_index = pd.Index(adata.obs[cell_id_col].values)
        else:
            adata_index = adata.obs.index

        # Cast both sides to string for robust matching.
        cd_set = set(cd_cell_ids)
        adata_str = pd.Index([str(x) for x in adata_index])
        if adata_str.has_duplicates:
            dupes = adata_str[adata_str.duplicated()].unique().tolist()
            raise ValueError(
                "AnnData cell identifiers are not unique; duplicate ids: "
                f"{dupes[:5]}"
            )

        matched_set = cd_set & set(adata_str)
        if len(self.cells) > 0:
            existing_axis = self._cells_axis_ids()
            if existing_axis is not None:
                matched = [c for c in existing_axis if c in matched_set]
            else:
                matched = [c for c in cd_cell_ids if c in matched_set]
        else:
            matched = [c for c in cd_cell_ids if c in matched_set]
        if not matched:
            import warnings
            warnings.warn(
                "No cell_id overlap between ChromData and AnnData. "
                "Check that cell_id values match.",
                stacklevel=2,
            )
            return 0

        adata_pos = {cell_id: i for i, cell_id in enumerate(adata_str)}
        order = [adata_pos[cell_id] for cell_id in matched]

        # Build / update the cell table keyed by the matched ids.
        new_index = pd.Index(matched, name="cell_id")
        if len(self.cells) > 0:
            old_axis = self._cells_axis_ids()
            if old_axis is None:
                cells = pd.DataFrame(index=new_index)
            else:
                cells = self.cells.copy()
                cells.index = old_axis
                cells = cells.loc[new_index].copy()
                cells.index.name = "cell_id"
        else:
            cells = pd.DataFrame(index=new_index)

        old_cellm = self.cellm
        if len(self.cells) > 0 and old_cellm:
            old_axis = self._cells_axis_ids()
            if old_axis is not None:
                old_pos = {cell_id: i for i, cell_id in enumerate(old_axis)}
                keep = [old_pos[cell_id] for cell_id in matched]
                old_cellm = {k: np.asarray(v)[keep].copy() for k, v in old_cellm.items()}

        if copy_obs:
            obs = adata.obs.iloc[order].copy()
            obs.index = new_index
            for col in obs.columns:
                cells[col] = obs[col].values
        self.cells = cells

        self.cellm = old_cellm
        if copy_obsm:
            for key in adata.obsm:
                arr = np.asarray(adata.obsm[key])
                if arr.shape[0] != adata.n_obs:
                    raise ValueError(
                        f"adata.obsm['{key}'] rows ({arr.shape[0]}) != adata.n_obs ({adata.n_obs})"
                    )
                self.cellm[key] = arr[order].copy()

        return len(matched)

    def to_anndata(self):
        """Export cell-level data as an AnnData object.

        Creates an AnnData where each observation is a cell, ``obs`` is
        ``self.cells``, and ``obsm`` is ``self.cellm``.  The ``X`` matrix
        is left empty (zeros) because ChromData has no cell-by-feature
        expression matrix.  Spot-level RNA-FISH / IF / epigenomic
        signals, such as Takei 2025 tracks, remain in ``self.tracks`` and
        are not flattened into AnnData.X.  Cell positions (the ``default``
        set of :meth:`cell_positions`, x / y in its units) become
        ``obsm["spatial"]``, the key scanpy / squidpy read, unless
        ``cellm`` already has one.

        Returns
        -------
        anndata.AnnData

        Raises
        ------
        ImportError
            If anndata is not installed.
        """
        import anndata as ad

        if len(self.cells) > 0:
            obs = self.cells.copy()
            axis_ids = self._cells_axis_ids()
            if axis_ids is not None:
                obs.index = axis_ids
                obs.index.name = "cell_id"
        elif self.n_cells > 0:
            obs = pd.DataFrame(index=self._spot_cell_ids())
        else:
            raise ValueError(
                "No cell-level data to export. "
                "Use link_anndata() first or populate cd.cells."
            )

        obsm = {}
        for key, value in self.cellm.items():
            arr = np.asarray(value)
            if arr.shape[0] != len(obs):
                raise ValueError(
                    f"cellm['{key}'] rows ({arr.shape[0]}) != exported cells ({len(obs)})"
                )
            obsm[key] = arr.copy()
        if "spatial" not in obsm and len(self.cells) > 0:
            try:
                pos = self.cell_positions("default")
            except KeyError:
                pos = None
            if pos is not None:
                obsm["spatial"] = pos.reindex(obs.index.astype(str))[["x", "y"]].to_numpy(float)

        adata = ad.AnnData(
            X=np.zeros((len(obs), 0)),
            obs=obs,
            obsm=obsm,
        )
        return adata

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def write(
        self,
        path: PathLike,
        *,
        format: Optional[str] = None,
        coord_dtype: str = "float64",
        row_group_rows: Optional[int] = None,
        compression_level: Optional[int] = None,
        keep_source_order: bool = True,
        embed: bool = False,
    ) -> None:
        """Write to disk; the format follows the path.

        * ``<name>.chromdata.zarr`` (any ``*.zarr``) — **the format 2.0
          container** (format 2.1): a Zarr v3 directory whose large tables
          are Parquet (see :mod:`chromdata.zarrcd` and ``spec.md``).  The
          spot-aligned tables are partitioned by chromosome and sorted by
          (cell, trace, bin) within a partition, with ``index/`` offsets,
          so :meth:`read` can open the store backed.
        * ``<name>.cdz`` — the same tree in one uncompressed zip file.

        ``format="zarr" | "cdz"`` overrides the suffix.  The HDF5 ``.h5cd``
        container is no longer written (convert old files with
        ``python -m uchrom.io.upgrade``).

        **Row order.**  The zarr / cdz writer stores spots sorted by
        (chromosome, ``cell_id`` code, ``trace_id`` code, ``bin_id``) — a
        stable sort, so ties keep their order.  Reading returns that order; every spot
        keeps its values (compare round trips after sorting by a stable
        key).  ``index/source_row`` records each spot's row in the written
        object, and ``ChromData.read(path, original_order=True)`` restores
        it.  Objects that are already sorted are written unchanged.

        Parameters (zarr / cdz)
        -----------------------
        coord_dtype : ``"float64"`` (default) or ``"float32"``
            Storage dtype of ``coords`` and ``layers`` (always float64 in
            memory).  float32 halves their size; see the format notes.
        row_group_rows : int, optional
            Target rows per Parquet row group of the spot-aligned tables
            (default 16,384).  Groups end on cell boundaries within a
            chromosome partition.
        compression_level : int, optional
            zstd level for Parquet and Zarr (default 3).
        keep_source_order : bool
            Store ``index/source_row`` when the writer had to sort.
        embed : bool
            Also embed the linked contact maps and AnnData this object can reach — its linked files, or the
            embedded copies of the store it was read from — limited to its cells
            (:func:`chromdata.embedded.embed_reachable`): a subset of an atlas store written to a new path keeps
            its maps.  Directory stores (``.chromdata.zarr``) only.

        """
        from .zarrcd import DEFAULT_ZSTD_LEVEL, container_kind, write_zarr

        path = Path(path)
        kind = format or container_kind(path)
        if kind == "h5cd":
            raise ValueError(f"{path.name}: the HDF5 .h5cd container is no longer supported; "
                             f"write '<name>.chromdata.zarr' (or '.cdz')")
        if kind not in ("zarr", "cdz"):
            raise ValueError(f"{path.name}: write '<name>.chromdata.zarr' or '<name>.cdz' "
                             f"(format must be 'zarr' or 'cdz')")
        if kind == "cdz" and not path.name.lower().endswith(".cdz"):
            raise ValueError("a .cdz store needs a path ending in .cdz")
        if kind == "zarr" and not path.name.lower().endswith(".zarr"):
            raise ValueError("a zarr store needs a path ending in .chromdata.zarr (or .zarr)")
        if embed and kind != "zarr":
            raise ValueError("embed=True needs a directory store (.chromdata.zarr)")
        write_zarr(self, path, coord_dtype=coord_dtype,
                   row_group_rows=row_group_rows,
                   compression_level=(DEFAULT_ZSTD_LEVEL if compression_level is None
                                      else compression_level),
                   keep_source_order=keep_source_order)
        if embed:
            from .embedded import embed_reachable

            embed_reachable(self, path)

    @classmethod
    def read(cls, path: PathLike, *, backed: bool = False,
             original_order: bool = False, columns=None, tracks=None) -> "ChromData":
        """Read a ChromData file; the format follows the path.

        * ``.chromdata.zarr`` / ``.cdz`` (format 2.x container) — with
          ``backed=True`` returns a :class:`~chromdata.backed.BackedChromData`:
          small tables are loaded, ``coords`` / ``spots`` / ``spot_tracks``
          / ``layers`` stay on disk, and ``get_cell`` / ``get_trace`` /
          ``get_chrom`` / ``iter_traces`` / ``iter_cells`` read only the
          rows they need.  Spots come back in the stored order —
          chromosome › cell › trace › bin (format 2.1; cell › trace › bin
          for 2.0 stores); ``original_order=True`` restores the order of
          the object that was written (in-memory reads only).
          ``columns`` / ``tracks`` select the spot-aligned columns (see
          :meth:`get_cell`): an in-memory read loads only those, a backed
          object uses them as the default of ``get_*`` / ``iter_*``.  The
          default reads everything.

        The HDF5 ``.h5cd`` container (format 1.x / 2.0) is no longer read:
        convert it once with ``python -m uchrom.io.upgrade old.h5cd``
        (:func:`uchrom.io.upgrade_h5cd`).

        Forward compatibility:

        - Same MAJOR, higher MINOR  → read with a warning; unknown fields
          are ignored silently by the lower-level helpers.
        - Different MAJOR           → raise ``ValueError`` with guidance.
        """
        from .remote import is_url
        from .zarrcd import container_kind

        remote = is_url(path)
        path = str(path).rstrip("/") if remote else Path(path)
        kind = container_kind(path)
        if kind in ("zarr", "cdz"):
            from .backed import BackedChromData

            if remote and not backed:
                raise ValueError("a remote store is read backed: pass backed=True")
            if not remote and not path.exists():
                raise FileNotFoundError(path)
            b = BackedChromData(path, columns=columns, tracks=tracks)
            _check_zarr_version(path, b._c.meta.get("format_version", "2.0"))
            if backed:
                if original_order:
                    raise ValueError("original_order=True needs an in-memory read (backed=False)")
                return b
            cd = b.to_memory(columns=columns, tracks=tracks)
            if original_order and b._c.meta.get("has_source_row"):
                src = b._c.array("index/source_row")
                _permute_spot_rows(cd, np.argsort(src, kind="stable"))
            return cd
        if kind == "h5cd":
            raise ValueError(
                f"{path}: the HDF5 .h5cd container is no longer supported; convert it once with "
                f"`python -m uchrom.io.upgrade {path}` (writes <name>.chromdata.zarr next to it)"
            )
        raise ValueError(f"{path}: not a ChromData store (.chromdata.zarr or .cdz)")

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

        # Carry over extra columns (e.g. contact_count); a bin_id from
        # to_dataframe(include_bin_id=True) is re-derived, not copied
        skip = required | {"index", "cell_id", BIN_ID}
        for col in df.columns:
            if col not in skip and col not in spots.columns:
                spots[col] = df[col].values

        return cls(coords, spots, **kwargs)

    @classmethod
    def from_fofct(
        cls,
        core_path: PathLike,
        *,
        cell_table: Optional[PathLike] = None,
        rna_table: Optional[PathLike] = None,
        mapping_table: Optional[PathLike] = None,
        cell_value_prefix: Optional[str] = "rna.",
        out: Optional[PathLike] = None,
        chunksize: Union[int, str] = "auto",
        memory_budget=None,
        **kwargs,
    ) -> "ChromData":
        """Read a FOF-CT core table, optionally with its companion tables.

        Parameters
        ----------
        core_path : path
            Path to the FOF-CT core table (CSV/TSV/TXT).
        cell_table : path, optional
            FOF-CT *cell data* table (``4dn_FOF-CT_cell``).  Loaded into
            :attr:`cells` indexed by ``cell_id``: ``cent_ROI_x/y`` become
            ``centroid_x/y``, ``area(um2)`` / ``area_cyto(um2)`` become
            ``nucleus_area_um2`` / ``cytoplasm_area_um2``, and every other
            numeric column (per-cell RNA copy numbers in 4DN tables) is
            prefixed with ``cell_value_prefix`` (``Nanog`` → ``rna.Nanog``).
            Centroid columns become the cell positions
            (``uns['cell_spatial']``, :meth:`cell_positions`):
            ``Cent_ROI_x/y[/z]`` (as ``centroid_x/y[/z]``) or
            ``cell_center_x_global`` / ``cell_center_y_global`` (Liu et al.
            2025, global frame), in the table's ``XYZ_unit``.
        mapping_table : path, optional
            FOF-CT *Cell/ROI mapping* table (``4dn_FOF-CT_mapping``):
            ``ROI_Boundaries`` of each ``Cell_ID`` in global coordinates, as
            OME polygon points strings (``"x1,y1 x2,y2 …"``) →
            ``cell_shapes['cell']`` (``uns['cell_shapes']['cell']``: frame
            ``"global"``).  Rows keyed by sub- / extra-cell ROI ids and OBJ
            meshes are skipped with a warning.
        rna_table : path, optional
            FOF-CT *RNA spot* table (``4dn_FOF-CT_rna``).  Loaded into
            ``points['rna']`` with columns ``x, y, z, gene, gene_id,
            cell_id, spot_id, …`` in the same frame as ``coords``.
        cell_value_prefix : str or None
            Prefix for unrecognised numeric cell-table columns; ``None``
            keeps their names.
        out : path, optional
            **Streaming import**: read the core table in chunks of
            ``chunksize`` rows and write them to this ``.chromdata.zarr``
            store with :class:`~chromdata.stream.ChromDataWriter`; returns
            the store opened backed.  Peak memory is one chunk plus the
            writer's merge pieces (bounded by ``memory_budget``), not the
            table.  The store equals ``from_fofct(core_path, ...).write(out)``
            (same spots, order, dtypes, small tables).  Without ``out`` the
            table is read into memory (a ``ResourceWarning`` is issued when
            the file is larger than a fifth of the memory budget).
        chunksize : int or ``"auto"``
            Rows per chunk of a streaming import (``"auto"``: from the
            memory budget).
        memory_budget : int or str, optional
            Defaults to :data:`chromdata.settings.memory_budget`.
        **kwargs
            Additional keyword arguments passed to ChromData constructor
            (e.g. cells, tracks, uns).  A streaming import accepts
            ``cells``, ``cellm``, ``traces``, ``points`` and ``uns``.
        """
        path = Path(core_path)
        if out is not None:
            return _from_fofct_streaming(cls, path, out=Path(out), cell_table=cell_table,
                                         rna_table=rna_table, mapping_table=mapping_table,
                                         cell_value_prefix=cell_value_prefix,
                                         chunksize=chunksize, memory_budget=memory_budget, **kwargs)
        from .settings import format_bytes, settings

        budget = settings.resolve_budget(memory_budget)
        if path.exists() and path.stat().st_size * 5 > budget:
            import warnings
            warnings.warn(
                f"{path.name} ({format_bytes(path.stat().st_size)}) is read into memory, "
                f"which takes several times its size (memory budget "
                f"{format_bytes(budget)}); pass out='<name>.chromdata.zarr' for a streaming import.",
                ResourceWarning, stacklevel=2)
        df, header_meta = _read_fofct_table(path)
        coords, spots = _fofct_core_parts(df)
        del df
        uns = _fofct_uns(kwargs.pop("uns", {}), header_meta)
        companions = _fofct_companions(kwargs, cell_table, rna_table, cell_value_prefix, mapping_table)
        if companions:
            uns["fofct_companions"] = companions
            _fofct_cell_spatial(uns, kwargs, companions)
            _warn_unmatched_cells(spots, companions, kwargs)

        return cls(coords, spots, uns=uns, **kwargs)

    @classmethod
    def writer(cls, path: PathLike, **kwargs):
        """A streaming :class:`~chromdata.stream.ChromDataWriter` for a
        ``.chromdata.zarr`` store larger than memory::

            with ChromData.writer("big.chromdata.zarr", memory_budget="4GB") as w:
                for chunk in chunks:
                    w.append(chunk)      # a ChromData, or coords= / spots= / spot_tracks=
            cd = ChromData.read("big.chromdata.zarr", backed=True)
        """
        from .stream import ChromDataWriter
        return ChromDataWriter(path, **kwargs)

    def to_fofct(
        self,
        path: PathLike,
        *,
        cell_table: Optional[PathLike] = None,
        rna_table: Optional[PathLike] = None,
        mapping_table: Optional[PathLike] = None,
        spot_tracks: bool = True,
        bin_tracks: bool = False,
        header: Optional[Mapping[str, Any]] = None,
        cell_value_prefix: Optional[str] = "rna.",
    ) -> Dict[str, Path]:
        """Write a 4DN FOF-CT core table, optionally with its companion
        cell and RNA-spot tables — the inverse of :meth:`from_fofct`.

        The core table has the ``##`` / ``#`` header lines, then
        ``Spot_ID, Trace_ID, X, Y, Z, Chrom, Chrom_Start, Chrom_End`` (+
        ``Cell_ID`` / ``Sub_Cell_ROI_ID`` / ``Extra_Cell_ROI_ID`` when
        present) and every other spot column, one row per spot in the
        object's row order.

        Parameters
        ----------
        path : path
            Core table (``.csv``).
        cell_table : path, optional
            Also write :attr:`cells` as a ``4dn_FOF-CT_cell`` table
            (``Cell_ID`` first; ``centroid_x/y/z`` → ``Cent_ROI_x/y/z``,
            ``nucleus_area_um2`` → ``area(um2)``, ``cytoplasm_area_um2`` →
            ``area_cyto(um2)``, and ``cell_value_prefix`` removed, so
            ``rna.Nanog`` → ``Nanog``).
        rna_table : path, optional
            Also write ``points['rna']`` as a ``4dn_FOF-CT_rna`` table
            (``Spot_ID, X, Y, Z, RNA_name, Gene_ID, Cell_ID, …``).
        mapping_table : path, optional
            Also write ``cell_shapes['cell']`` as a ``4dn_FOF-CT_mapping``
            table (``Cell_ID, ROI_Boundaries``: the exterior ring as an OME
            polygon points string, ``##ROI_Boundaries_Format``).
        spot_tracks : bool
            Append :attr:`spot_tracks` as extra columns (default).  They
            come back as spot columns from :meth:`from_fofct`.
        bin_tracks : bool
            Also append :attr:`bin_tracks`, broadcast to spots.
        header : mapping, optional
            Header entries to add or override.  Defaults come from
            ``uns['fofct_header']`` (what :meth:`from_fofct` read), else
            ``FOF-CT_version=v0.1``, ``Table_namespace``, and
            ``genome_assembly`` / ``XYZ_unit`` from :attr:`uns`.  The
            required fields (``FOF-CT_version``, ``Table_namespace``,
            ``genome_assembly``, ``XYZ_unit``) are written as ``##key=value``,
            the others as ``#key: value``.

        Returns
        -------
        dict
            ``{"core": path, "cells": path, "rna": path}`` of the files
            written.

        Notes
        -----
        FOF-CT has no place for ``bins`` rows without spots, ``cellm``,
        ``binm``, ``layers``, ``intervals``, ``results`` or other ``uns``
        keys; those are not written.  Spots without ``spot_id`` get
        ``Spot_ID = 0 .. n_spots - 1``.  Categorical extra columns come
        back as plain columns.
        """
        written: Dict[str, Path] = {}
        path = Path(path)
        spots = self.spots_with_loci()
        n = len(spots)
        table = pd.DataFrame(index=pd.RangeIndex(n))
        table["Spot_ID"] = (spots["spot_id"].to_numpy() if "spot_id" in spots.columns
                            else np.arange(n, dtype=np.int64))
        table["Trace_ID"] = _plain_values(spots["trace_id"])
        coords = np.asarray(self.coords)
        table["X"], table["Y"], table["Z"] = coords[:, 0], coords[:, 1], coords[:, 2]
        table["Chrom"] = _plain_values(spots["chrom"])
        table["Chrom_Start"] = spots["start"].to_numpy()
        table["Chrom_End"] = spots["end"].to_numpy()
        for col, name in (("cell_id", "Cell_ID"), ("sub_cell_roi_id", "Sub_Cell_ROI_ID"),
                          ("extra_cell_roi_id", "Extra_Cell_ROI_ID")):
            if col in spots.columns:
                table[name] = _plain_values(spots[col])
        skip = {"spot_id", "trace_id", "chrom", "start", "end", "cell_id", "sub_cell_roi_id",
                "extra_cell_roi_id", BIN_ID}
        for col in spots.columns:
            if col not in skip:
                table[str(col)] = _plain_values(spots[col])
        extra = []
        if spot_tracks:
            extra += [(c, self._spot_tracks[c]) for c in self._spot_tracks.columns]
        if bin_tracks and len(self._bin_tracks.columns):
            bid = spots[BIN_ID].to_numpy()
            extra += [(c, self._bin_tracks[c].iloc[bid].reset_index(drop=True))
                      for c in self._bin_tracks.columns]
        for col, values in extra:
            if str(col) in table.columns:
                raise ValueError(f"track {col!r} clashes with a FOF-CT / spot column")
            table[str(col)] = _plain_values(values)
        meta = _fofct_header_defaults(self.uns, "4dn_FOF-CT_core",
                                      (self.uns.get("fofct_header") or {}), header)
        _write_fofct_table(path, table, meta)
        written["core"] = path

        companions = self.uns.get("fofct_companions") or {}
        if cell_table is not None:
            cells = _fofct_cells_frame(self.cells, cell_value_prefix)
            meta = _fofct_header_defaults(self.uns, "4dn_FOF-CT_cell",
                                          (companions.get("cells") or {}).get("header") or {}, None)
            _write_fofct_table(Path(cell_table), cells, meta)
            written["cells"] = Path(cell_table)
        if rna_table is not None:
            if "rna" not in self.points:
                raise ValueError("rna_table= needs points['rna']")
            rna = _fofct_rna_frame(self.points["rna"])
            meta = _fofct_header_defaults(self.uns, "4dn_FOF-CT_rna",
                                          (companions.get("rna") or {}).get("header") or {}, None)
            _write_fofct_table(Path(rna_table), rna, meta)
            written["rna"] = Path(rna_table)
        if mapping_table is not None:
            from . import cellspatial as _cs

            if "cell" not in self.cell_shapes:
                raise ValueError("mapping_table= needs cell_shapes['cell']")
            shp = self.cell_shapes["cell"]
            table = pd.DataFrame({"Cell_ID": shp["cell_id"].astype(str).to_numpy(),
                                  "ROI_Boundaries": [_cs.format_ome_polygon(w) for w in shp["geometry"]]})
            stored = dict((companions.get("mapping") or {}).get("header") or {})
            rec = _linked_records(self.uns.get(_cs.SHAPES_FAMILY)).get("cell") or {}
            stored.setdefault("ROI_Boundaries_Format", _cs.OME_POLYGON_FORMAT)
            if rec.get("unit"):
                stored.setdefault("XYZ_unit", rec["unit"])
            meta = _fofct_header_defaults(self.uns, "4dn_FOF-CT_mapping", stored, None)
            _write_fofct_table(Path(mapping_table), table, meta)
            written["mapping"] = Path(mapping_table)
        return written

    @classmethod
    def from_pyhim_trace(
        cls,
        ecsv_path: PathLike,
        barcode_dict: dict | pd.DataFrame | None = None,
        **kwargs,
    ) -> "ChromData":
        """Read a PyHiM chromatin-trace ECSV table into a ChromData.

        PyHiM (Devos et al. 2024) emits one ECSV file per trace-building
        run.  Schema (from ``chromatin_trace_table.py`` upstream):

            Spot_ID, Trace_ID, x, y, z, Chrom, Chrom_Start, Chrom_End,
            ROI #, Mask_id, Barcode #, label

        ``meta['comments']`` carries ``xyz_unit=...`` and
        ``genome_assembly=...``.

        Parameters
        ----------
        ecsv_path : path
            Path to the ECSV file written by PyHiM.
        barcode_dict : dict[int, (chrom, start, end)] or DataFrame, optional
            Required when ``Chrom``/``Chrom_Start``/``Chrom_End`` are empty
            in the ECSV (PyHiM does not always populate them).  As a
            DataFrame, expects columns ``barcode, chrom, start, end``.
            If ``Chrom`` is populated, ``barcode_dict`` is ignored.
        **kwargs
            Additional keyword arguments passed to the ChromData
            constructor (``cells``, ``tracks``, ``uns``, ...).

        Notes
        -----
        - ``Mask_id`` becomes ``cell_id`` (PyHiM convention).
        - ECSV header comments are captured in
          ``cd.uns['pyhim']['ecsv_comments']`` and any
          ``xyz_unit`` / ``genome_assembly`` entries are also promoted
          to ``cd.uns`` directly (matching :meth:`from_fofct`).
        """
        try:
            from astropy.table import Table
        except ImportError as e:
            raise ImportError(
                "astropy is required to read PyHiM ECSV trace tables. "
                "Install with `pip install chromdata[im]` (or u-chrom[im], or astropy)."
            ) from e

        path = Path(ecsv_path)
        table = Table.read(path, format="ascii.ecsv")
        df = table.to_pandas()

        # Astropy can decode byte-string columns as bytes — decode to str.
        for col in df.columns:
            if df[col].dtype == object and df[col].apply(
                lambda v: isinstance(v, bytes)
            ).any():
                df[col] = df[col].apply(
                    lambda v: v.decode() if isinstance(v, bytes) else v
                )

        missing_coord = {"x", "y", "z"} - set(df.columns)
        if missing_coord:
            raise ValueError(
                f"PyHiM ECSV missing coordinate columns {missing_coord}. "
                f"Got: {list(df.columns)}"
            )

        # Decide whether Chrom is filled.  PyHiM writes empty strings (which
        # astropy round-trips as NaN) when the barcode→genome mapping wasn't
        # supplied at trace-building time.
        chrom_filled = (
            "Chrom" in df.columns
            and df["Chrom"].notna().any()
            and df["Chrom"].astype(str).str.strip().ne("").any()
        )

        if not chrom_filled:
            if barcode_dict is None:
                raise ValueError(
                    "PyHiM ECSV has no Chrom/Chrom_Start/Chrom_End data; "
                    "pass `barcode_dict={barcode: (chrom, start, end)}` "
                    "or a DataFrame[barcode, chrom, start, end]."
                )
            df = _apply_pyhim_barcode_dict(df, barcode_dict)

        # Canonical column names for ChromData.
        rename = {
            "Chrom": "chrom",
            "Chrom_Start": "start",
            "Chrom_End": "end",
            "Trace_ID": "trace_id",
            "Spot_ID": "spot_id",
            "Mask_id": "cell_id",
            "ROI #": "roi_id",
            "Barcode #": "barcode",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

        coords = df[["x", "y", "z"]].values.astype(np.float64)

        spot_cols = ["chrom", "start", "end", "trace_id"]
        for extra in ("spot_id", "cell_id", "roi_id", "barcode", "label"):
            if extra in df.columns:
                spot_cols.append(extra)
        spots = df[spot_cols].copy()

        # Capture ECSV meta into uns.
        uns = kwargs.pop("uns", None) or {}
        ecsv_comments = list(table.meta.get("comments") or [])
        uns.setdefault("pyhim", {})["ecsv_comments"] = ecsv_comments
        for c in ecsv_comments:
            if "=" in c:
                k, _, v = c.partition("=")
                k = k.strip(); v = v.strip()
                if k in ("xyz_unit", "genome_assembly"):
                    uns.setdefault(k, v)

        return cls(coords, spots, uns=uns, **kwargs)

    @classmethod
    def from_seqfish_multiomics(cls, spot_glob, **kwargs) -> "ChromData":
        """Load Takei 2025 DNA seqFISH+ cerebellum data.

        Thin shim around :func:`uchrom.io.seqfish_multiomics.read_seqfish_multiomics`.
        See that function for the full parameter list.
        """
        read_seqfish_multiomics = _uchrom_io("seqfish_multiomics", "read_seqfish_multiomics")
        return read_seqfish_multiomics(spot_glob, **kwargs)

    @classmethod
    def from_seqfish_multiomics_linked(cls, spot_glob, **kwargs):
        """Load linked Takei 2025 DNA tracing + RNA AnnData artifacts.

        Thin shim around
        :func:`uchrom.io.seqfish_multiomics.load_seqfish_multiomics_linked`.
        Returns a ``ChromData`` with RNA expression available at
        ``cd.linked_adata`` and can write a paired ``.chromdata.zarr`` /
        ``.h5ad``.
        """
        load_seqfish_multiomics_linked = _uchrom_io("seqfish_multiomics", "load_seqfish_multiomics_linked")
        return load_seqfish_multiomics_linked(spot_glob, **kwargs)

    @classmethod
    def from_takei2025_cerebellum(cls, **kwargs):
        """Load linked Takei 2025 cerebellum data.

        Thin shim around
        :func:`uchrom.io.seqfish_multiomics.load_takei2025_cerebellum`.
        Returns a ``ChromData`` with RNA expression available at
        ``cd.linked_adata``.
        """
        load_takei2025_cerebellum = _uchrom_io("seqfish_multiomics", "load_takei2025_cerebellum")
        return load_takei2025_cerebellum(**kwargs)

    def to_dataframe(self, include_bin_id: bool = False) -> pd.DataFrame:
        """Export as a flat DataFrame: ``chrom, start, end, x, y, z`` (loci
        derived from ``bins``) followed by the other spot columns.
        ``bin_id`` is left out unless ``include_bin_id=True``."""
        df = self.spots_with_loci()
        if not include_bin_id:
            df = df.drop(columns=[BIN_ID])
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
        out = ChromData(
            self.coords.copy(),
            self.spots.copy(),
            bins=self._bins.copy(),
            cells=self.cells.copy() if len(self.cells) > 0 else None,
            cellm={k: v.copy() for k, v in self.cellm.items()} or None,
            binm={k: np.array(v, copy=True) for k, v in self.binm.items()} or None,
            traces=self.traces.copy() if len(self.traces) > 0 else None,
            layers={k: v.copy() for k, v in self.layers.items()} or None,
            uns=deepcopy(self.uns) or None,
            points={k: v.copy() for k, v in self.points.items()} or None,
            cell_shapes={k: v.copy() for k, v in self.cell_shapes.items()} or None,
            clusters={k: v.copy() for k, v in self.clusters.items()} or None,
            linked_adata=self._linked_adata.copy() if self._linked_adata is not None else None,
            validate=False,
        )
        out._bin_tracks = self._bin_tracks.copy()
        out._spot_tracks = self._spot_tracks.copy()
        out._spot_view_order = list(self._spot_view_order) if self._spot_view_order else None
        # results and intervals share interval tables ("same object"): copy
        # them together so the link survives
        memo: dict = {}
        out._intervals = deepcopy(self._intervals, memo)
        out.results = deepcopy(self.results, memo)
        out._link_origin = self._links_from()
        return out

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        parts = [
            f"ChromData: n_spots={self.n_spots}, n_traces={self.n_traces}",
        ]
        if self.n_cells > 0:
            parts[0] += f", n_cells={self.n_cells}"
        parts[0] += f", n_bins={self.n_bins}"

        spot_cols = list(self.spots.columns)
        parts.append(f"  spots:   {spot_cols}")

        if len(self.cells) > 0:
            parts.append(f"  cells:   {list(self.cells.columns)} ({len(self.cells)} cells)")
        if self.cellm:
            shapes = {k: v.shape for k, v in self.cellm.items()}
            parts.append(f"  cellm:   {shapes}")
        if len(self._bin_tracks.columns):
            parts.append(f"  tracks (bins):  {list(self._bin_tracks.columns)}")
        if len(self._spot_tracks.columns):
            parts.append(f"  spot_tracks:    {list(self._spot_tracks.columns)}")
        if self.binm:
            parts.append(f"  binm:    {list(self.binm.keys())}")
        if len(self._intervals):
            parts.append(f"  intervals: {list(self._intervals.keys())}")
        if len(self.traces) > 0:
            parts.append(f"  traces:  {list(self.traces.columns)} ({len(self.traces)} traces)")
        if self.layers:
            parts.append(f"  layers:  {list(self.layers.keys())}")
        if self.points:
            sizes = {k: len(v) for k, v in self.points.items()}
            parts.append(f"  points:  {sizes}")
        if self.cell_shapes:
            sizes = {k: len(v) for k, v in self.cell_shapes.items()}
            parts.append(f"  cell_shapes: {sizes}")
        if self.clusters:
            sizes = {k: v.n_clusters for k, v in self.clusters.items()}
            parts.append(f"  clusters: {sizes}")
        if self.results:
            parts.append(f"  results: {list(self.results.keys())}")
        if self.uns:
            parts.append(f"  uns:     {list(self.uns.keys())}")
        if self._linked_adata is not None:
            parts.append(f"  linked_adata: {self._linked_adata.shape}")
        elif self.uns.get("linked_anndata", {}).get("path"):
            parts.append("  linked_adata: lazy")

        return "\n".join(parts)

    def __len__(self) -> int:
        return self.n_spots


# ======================================================================
# Utilities
# ======================================================================

def _clean_metadata_record(record: Any) -> dict:
    """Return a JSON-friendly metadata record with empty values removed."""
    if not isinstance(record, Mapping):
        raise TypeError(f"metadata record must be a mapping, got {type(record).__name__}")
    out = {}
    for key, value in record.items():
        if value is None or value == "":
            continue
        out[str(key)] = _metadata_jsonable(value)
    return out


def _metadata_jsonable(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, Mapping):
        return {
            str(k): _metadata_jsonable(v)
            for k, v in value.items()
            if v is not None and v != ""
        }
    if isinstance(value, (list, tuple, set)):
        return [_metadata_jsonable(v) for v in value]
    if isinstance(value, (pd.Index, pd.Series)):
        return [_metadata_jsonable(v) for v in value.tolist()]
    return value


def _stable_metadata_id(prefix: str, record: Mapping[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    return f"{prefix}_{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:10]}"


#: spot columns every selection keeps (derived loci included)
_REQUIRED_SPOT_COLUMNS = ("chrom", "start", "end", "trace_id", "cell_id", BIN_ID)


def resolve_selection(spot_columns: Sequence[str], track_columns: Sequence[str],
                      layer_keys: Sequence[str], columns=None, tracks=None):
    """Spot-aligned columns of a ``columns=`` / ``tracks=`` selection.

    Returns ``(spot columns, spot tracks, layer keys)`` to keep, each in the
    object's own order.

    * ``columns=None`` — everything (the default);
    * ``columns="coords"`` (or ``[]``) — the coordinates and the key columns
      (``trace_id``, ``cell_id``, ``bin_id`` and the derived loci) only;
    * ``columns=[...]`` — the key columns plus the named spot columns, spot
      tracks and layers (``"x"``, ``"y"``, ``"z"``, ``"coords"`` are
      accepted and implied);
    * ``tracks=`` (``None`` / a list / ``[]`` / ``False``) overrides the spot
      tracks the ``columns`` choice implies.
    """
    spot_columns, track_columns, layer_keys = list(spot_columns), list(track_columns), list(layer_keys)
    required = [c for c in spot_columns if c in _REQUIRED_SPOT_COLUMNS]
    if columns is None:
        spots, trk, lay = spot_columns, track_columns, layer_keys
    else:
        if isinstance(columns, str):
            if columns != "coords":
                columns = [columns]
            else:
                columns = []
        names = [str(c) for c in columns]
        known = set(spot_columns) | set(track_columns) | set(layer_keys) | {"x", "y", "z", "coords"}
        missing = [c for c in names if c not in known]
        if missing:
            raise KeyError(f"unknown column(s) {missing}: not a spot column, spot track or layer")
        want = set(names)
        spots = [c for c in spot_columns if c in want or c in required]
        trk = [c for c in track_columns if c in want]
        lay = [k for k in layer_keys if k in want]
    if tracks is not None:
        if tracks is False:
            tracks = []
        elif isinstance(tracks, str):
            tracks = [tracks]
        want_t = [str(t) for t in tracks]
        missing = [t for t in want_t if t not in track_columns]
        if missing:
            raise KeyError(f"unknown spot track(s) {missing}")
        trk = [c for c in track_columns if c in set(want_t)]
    return spots, trk, lay


def resolve_batch(batch, units_mean: float, bytes_per_spot: float,
                  memory_budget=None, fraction: float = 0.25) -> int:
    """Units (traces / cells) per batch: an int as given, or ``"auto"`` —
    as many as fit ``fraction`` of the memory budget
    (:data:`chromdata.settings.memory_budget`)."""
    from .settings import settings

    if batch is None:
        batch = settings.default_batch
    if isinstance(batch, str):
        if batch != "auto":
            raise ValueError("batch must be a positive int or 'auto'")
        budget = settings.resolve_budget(memory_budget) * float(fraction)
        per_unit = max(1.0, float(units_mean)) * max(1.0, float(bytes_per_spot))
        return max(1, int(budget // per_unit))
    batch = int(batch)
    if batch < 1:
        raise ValueError("batch must be a positive int or 'auto'")
    return batch


def _pdist_matrix(coords: np.ndarray) -> np.ndarray:
    """Compute pairwise Euclidean distance matrix from (n, 3) coords."""
    diff = coords[:, None, :] - coords[None, :, :]
    return np.sqrt((diff ** 2).sum(axis=-1))


def _apply_pyhim_barcode_dict(
    df: pd.DataFrame,
    barcode_dict,
) -> pd.DataFrame:
    """Fill Chrom / Chrom_Start / Chrom_End from a Barcode # → (chrom, start, end) map.

    Accepts a Python ``dict`` keyed by integer barcode, or a DataFrame
    with columns ``barcode, chrom, start, end``.  Unmapped barcodes
    raise ``KeyError`` listing the offenders.
    """
    if isinstance(barcode_dict, pd.DataFrame):
        bdf = barcode_dict
        required = {"barcode", "chrom", "start", "end"}
        missing_cols = required - set(bdf.columns)
        if missing_cols:
            raise ValueError(
                f"barcode_dict DataFrame missing columns: {sorted(missing_cols)}"
            )
        mapping = {
            int(row.barcode): (str(row.chrom), int(row.start), int(row.end))
            for row in bdf.itertuples(index=False)
        }
    else:
        mapping = {int(k): tuple(v) for k, v in dict(barcode_dict).items()}

    if "Barcode #" not in df.columns:
        raise ValueError(
            "PyHiM ECSV has no 'Barcode #' column — cannot apply barcode_dict."
        )

    barcodes = df["Barcode #"].astype(int)
    unknown = sorted(set(barcodes) - set(mapping))
    if unknown:
        raise KeyError(
            f"barcode_dict missing entries for barcodes: {unknown}"
        )

    df = df.copy()
    df["Chrom"] = barcodes.map(lambda b: mapping[b][0])
    df["Chrom_Start"] = barcodes.map(lambda b: mapping[b][1]).astype("int64")
    df["Chrom_End"] = barcodes.map(lambda b: mapping[b][2]).astype("int64")
    return df


def _check_zarr_version(path, version_str: str) -> None:
    """MAJOR / MINOR rules of the zarr container (whose
    own version, :data:`chromdata.zarrcd.ZARR_FORMAT_VERSION`, is 2.2:
    2.0 stores are read as one unpartitioned table)."""
    import warnings

    from .zarrcd import ZARR_FORMAT_VERSION

    major, minor = _parse_version(str(version_str))
    cur_major, cur_minor = _parse_version(ZARR_FORMAT_VERSION)
    if major != cur_major:
        raise ValueError(
            f"{path}: format version {version_str} has incompatible MAJOR with this "
            f"uchrom (supports {cur_major}.x). Upgrade chromdata or convert the file."
        )
    if minor > cur_minor:
        warnings.warn(
            f"{path}: written with format version {version_str} (reader supports up "
            f"to {ZARR_FORMAT_VERSION}). Forward-compatible — unknown fields will be ignored.",
            stacklevel=3,
        )


def _permute_spot_rows(cd: "ChromData", pos: np.ndarray) -> None:
    """Reorder the spot-aligned data of an in-memory object in place."""
    cd.coords = cd.coords[pos]
    cd.spots = cd.spots.iloc[pos].reset_index(drop=True)
    if len(cd._spot_tracks.columns):
        cd._spot_tracks = cd._spot_tracks.iloc[pos].reset_index(drop=True)
    else:
        cd._spot_tracks = _empty_frame(len(pos))
    cd.layers = {k: np.asarray(v)[pos] for k, v in cd.layers.items()}


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

def _is_number(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


def _fofct_column_names(value: str) -> list:
    """The names of a ``##columns=`` value.  One enclosing pair of brackets is removed (``str.strip("()")`` would
    also eat the ")" of a last column such as "n_per_dist(um)"), and so is a lone bracket of a pair whose other half
    is missing (Patterson et al. 2023: ``##columns=Spot_ID,...,Chrom_End)``)."""
    v = value.strip()
    if v.startswith("(") and v.endswith(")"):
        v = v[1:-1]
    elif v.endswith(")") and "(" not in v:
        v = v[:-1]
    elif v.startswith("(") and ")" not in v:
        v = v[1:]
    return [c.strip() for c in v.split(",")]


def _read_fofct_table(path: Path):
    """Parse a FOF-CT table: ``##key=value`` / ``#key: value`` headers,
    a ``##columns=(...)`` line and CSV data.  Returns ``(df, header_meta)``
    with the file's own column names (unknown → ``col_i``)."""
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
            if stripped.lower().lstrip("#").startswith("columns=") and stripped.startswith("#"):   # also "#columns="
                # an empty value: the names follow on a line of their own (Le et al. 2024: "##columns=" over
                # "(Spot_ID,barcodeID,...,hyb)"), read as a CSV header row
                value = stripped.split("=", 1)[1]
                columns = _fofct_column_names(value) if value.strip() else None
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
    # the first non-comment line starts with a non-numeric token, treat it
    # as a CSV header.
    first_token = data_lines[0].split(",", 1)[0].strip().strip('"')
    has_csv_header = bool(first_token) and not (
        first_token[0].isdigit() or first_token[0] in ("-", "+", ".")
    )
    header_names = [c.strip('"') for c in _fofct_column_names(data_lines[0].rstrip(","))]
    all_names = all(n and not _is_number(n) for n in header_names)
    if has_csv_header and columns is not None and first_token not in columns and not all_names:
        has_csv_header = False  # e.g. cell tables whose first column is an id like "0_1"
    if has_csv_header:
        data_lines = data_lines[1:]
        if columns is None:
            columns = header_names
        elif len(columns) != len(header_names) and data_lines and \
                len(header_names) == len(data_lines[0].split(",")):
            # the ``##columns`` line disagrees with the header row, which matches the rows (Hafner et al. 2023:
            # ``##columns=(Spot_ID, ..., Chrom_End)`` over ``spotID,traceID,x,y,z,readout,Chrom,...``)
            columns = header_names

    if not data_lines:
        raise ValueError(f"No data rows found in {path}")

    from io import StringIO as _StringIO
    # round_trip: the float in the file, exactly (the default parser can be 1 ulp off)
    df = pd.read_csv(_StringIO("\n".join(data_lines)), header=None, skipinitialspace=True,
                     float_precision="round_trip")
    if columns is not None and len(columns) == len(df.columns):
        df.columns = columns
    elif columns is not None:
        # Column count mismatch — trust the data and label the extras
        df.columns = (columns + [f"col_{i}" for i in range(len(columns), len(df.columns))])[: len(df.columns)]
        # extras that are only the commas a writer pads every row with (Chen et al. 2023: "1,3008.24,,,") go
        extra = [c for c in df.columns[len(columns):] if df[c].isna().all()]
        df = df.drop(columns=extra)
    return df, header_meta


def read_fofct_table(path) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """Read any FOF-CT table (core, spot quality, trace data, cell data, RNA spots, ...) as it is.

    Returns ``(table, header)``: the rows under the file's own column names (``##columns=(...)`` or a CSV header
    row; unnamed columns ``col_<i>``) and the ``##key=value`` / ``#key: value`` header lines as a dict.  Quoted
    header lines and the trailing commas some writers pad them with are handled.  :meth:`ChromData.from_fofct`
    reads core tables into a ``ChromData``; this is for the companion tables a caller joins itself.
    """
    return _read_fofct_table(Path(path))


_FOFCT_CANONICAL = {
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
_FOFCT_DEFAULT_COLUMNS = ["Spot_ID", "Trace_ID", "X", "Y", "Z", "Chrom", "Chrom_Start", "Chrom_End"]


def _fofct_core_parts(df: pd.DataFrame):
    """A parsed FOF-CT core table (file column names) → ``(coords, spots)``."""
    if not any(str(c).lower() == "x" for c in df.columns):
        # no column names in the file: assume the core-table order
        n = len(df.columns)
        df.columns = (_FOFCT_DEFAULT_COLUMNS[:n]
                      + [f"col_{i}" for i in range(len(_FOFCT_DEFAULT_COLUMNS), n)])

    # Map FOF-CT columns to ChromData — case-insensitive.
    rename = {c: _FOFCT_CANONICAL[str(c).lower()] for c in df.columns
              if str(c).lower() in _FOFCT_CANONICAL}
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
    return coords, spots


def _fofct_uns(uns: Optional[dict], header_meta: Mapping[str, str]) -> dict:
    """FOF-CT header metadata into ``uns`` (case-insensitive promotion of the
    unit and assembly)."""
    uns = dict(uns or {})
    if header_meta:
        uns["fofct_header"] = header_meta
    lower_meta = {k.lower(): v for k, v in header_meta.items()}
    if "xyz_unit" in lower_meta:
        uns["xyz_unit"] = lower_meta["xyz_unit"]
    if "genome_assembly" in lower_meta:
        uns["genome_assembly"] = lower_meta["genome_assembly"]
    return uns


def _fofct_companions(kwargs: dict, cell_table, rna_table, cell_value_prefix, mapping_table=None) -> dict:
    """Load the companion tables into ``kwargs`` (``cells``, ``points``,
    ``cell_shapes``); returns their header metadata."""
    companions = {}
    if mapping_table is not None:
        shapes, meta = _fofct_mapping_table(Path(mapping_table))
        if len(shapes):
            cs = dict(kwargs.pop("cell_shapes", None) or {})
            cs["cell"] = shapes
            kwargs["cell_shapes"] = cs
        companions["mapping"] = meta
    if cell_table is not None:
        cells, meta = _fofct_cell_table(Path(cell_table), cell_value_prefix)
        if kwargs.get("cells") is not None:
            raise ValueError("pass either cells= or cell_table=, not both")
        kwargs["cells"] = cells
        companions["cells"] = meta
    if rna_table is not None:
        rna, meta = _fofct_rna_table(Path(rna_table))
        points = dict(kwargs.pop("points", None) or {})
        points["rna"] = rna
        kwargs["points"] = points
        companions["rna"] = meta
    return companions


def _fofct_mapping_table(path: Path):
    """FOF-CT Cell/ROI mapping table → (cell_shapes frame, meta): the
    ``ROI_Boundaries`` of the ``Cell_ID`` rows as WKB polygons."""
    import warnings

    from . import cellspatial as _cs

    df, meta = _read_fofct_table(path)
    cols = {str(c).strip().lower(): c for c in df.columns}
    if "roi_boundaries" not in cols:
        raise ValueError(f"{path}: mapping table has no ROI_Boundaries column; columns: {list(df.columns)}")
    id_col = cols.get("cell_id")
    if id_col is None:
        warnings.warn(f"{path}: mapping table is not keyed by Cell_ID (sub- / extra-cell ROIs); "
                      f"no cell outlines read", UserWarning, stacklevel=4)
        return pd.DataFrame(columns=["cell_id", "geometry"]), {"source": path.name, "header": meta, "n": 0}
    fmt = next((v for k, v in meta.items() if str(k).lower() == "roi_boundaries_format"), "")
    ids, geoms, skipped = [], [], 0
    for cid, text in zip(df[id_col].astype(str), df[cols["roi_boundaries"]]):
        try:
            geoms.append(_cs.polygon_wkb(_cs.parse_ome_polygon(text)))
            ids.append(cid)
        except ValueError:
            skipped += 1
    if skipped:
        warnings.warn(f"{path}: {skipped} ROI_Boundaries value(s) are not OME polygon points strings "
                      f"(e.g. OBJ meshes) and were skipped", UserWarning, stacklevel=4)
    shapes = _cs.to_wkb(geoms, ids)
    extra = [c for c in df.columns if c not in (id_col, cols["roi_boundaries"])]
    if extra and len(shapes):
        keep = df[df[id_col].astype(str).isin(set(ids))].drop_duplicates(id_col)
        shapes = pd.concat([shapes, keep[extra].reset_index(drop=True)], axis=1)
    return shapes, {"source": path.name, "header": meta, "n": int(len(shapes)), "format": fmt,
                    "n_skipped": skipped}


#: FOF-CT cell-table centroid columns (after renaming) → (frame, source label)
_FOFCT_CENTROIDS = (
    (("centroid_x", "centroid_y", "centroid_z"), None, "FOF-CT cell table Cent_ROI_x / Cent_ROI_y [/ Cent_ROI_z]"),
    (("cell_center_x_global", "cell_center_y_global", None), "global",
     "FOF-CT cell table cell_center_x_global / cell_center_y_global"),
)


def _fofct_cell_spatial(uns: dict, kwargs: dict, companions: Mapping) -> None:
    """Records for the cell positions / outlines a FOF-CT import found:
    ``uns['cell_spatial']['default']`` for centroid columns of the cell
    table, ``uns['cell_shapes']['cell']`` for mapping-table outlines."""
    from . import cellspatial as _cs

    def unit_of(meta):
        header = (meta or {}).get("header") or {}
        for k, v in header.items():
            if str(k).lower() == "xyz_unit":
                return str(v)
        return uns.get("xyz_unit")

    cells = kwargs.get("cells")
    shapes = (kwargs.get("cell_shapes") or {}).get("cell")
    if shapes is not None and len(shapes):
        rec = {"geometry_types": sorted({_cs.wkb_type(w) for w in shapes["geometry"]}), "n": int(len(shapes)),
               "unit": unit_of(companions.get("mapping")), "frame": "global", "status": "measured",
               "source": f"FOF-CT Cell/ROI mapping table ROI_Boundaries ({companions['mapping']['source']})"}
        _set_linked_record(uns, _cs.SHAPES_FAMILY, "cell", _clean_metadata_record(rec))
    if cells is None or not len(cells):
        return
    for (x, y, z), frame, source in _FOFCT_CENTROIDS:
        if x in cells.columns and y in cells.columns:
            cols = [x, y] + ([z] if z and z in cells.columns else [])
            rec = _cs.position_record(cols, unit=unit_of(companions.get("cells")), frame=frame,
                                      status="measured", source=source,
                                      shapes="cell" if shapes is not None and len(shapes) else None)
            _set_linked_record(uns, _cs.POSITIONS_FAMILY, "default", rec)
            return


def _scan_fofct_header(path: Path):
    """The header of a FOF-CT table without reading its data: returns
    ``(header_meta, columns, n_skip)`` where ``n_skip`` is the number of lines
    before the first data row (the ``##`` / ``#`` lines, blank lines and a
    CSV header row).  Same rules as :func:`_read_fofct_table`; comment lines
    must precede the data."""
    header_meta = {}
    columns = None
    n_skip = 0
    with open(path, "r") as fh:
        for line in fh:
            raw = line.strip()
            if not raw:
                n_skip += 1
                continue
            stripped = raw.rstrip(",").strip()
            if stripped.startswith('"') and stripped.endswith('"') and len(stripped) >= 2:
                stripped = stripped[1:-1]
            if stripped.lower().lstrip("#").startswith("columns=") and stripped.startswith("#"):   # also "#columns="
                # an empty value: the names follow on a line of their own (Le et al. 2024: "##columns=" over
                # "(Spot_ID,barcodeID,...,hyb)"), read as a CSV header row
                value = stripped.split("=", 1)[1]
                columns = _fofct_column_names(value) if value.strip() else None
            elif stripped.startswith("##"):
                key, _, val = stripped[2:].partition("=")
                header_meta[key.strip()] = val.strip()
            elif stripped.startswith("#"):
                key, _, val = stripped[1:].partition(":")
                header_meta[key.strip()] = val.strip()
            else:
                first_token = raw.split(",", 1)[0].strip().strip('"')
                has_csv_header = bool(first_token) and not (
                    first_token[0].isdigit() or first_token[0] in ("-", "+", "."))
                if has_csv_header and columns is not None and first_token not in columns:
                    has_csv_header = False
                if has_csv_header:
                    if columns is None:
                        columns = [c.strip('"') for c in _fofct_column_names(raw.rstrip(","))]
                    n_skip += 1
                break
            n_skip += 1
    return header_meta, columns, n_skip


def _from_fofct_streaming(cls, path: Path, *, out: Path, cell_table, rna_table, cell_value_prefix,
                          chunksize, memory_budget, mapping_table=None, **kwargs):
    """``ChromData.from_fofct(..., out=)``: chunked read → streaming writer."""
    from .settings import settings

    from .stream import ChromDataWriter

    allowed = {"cells", "cellm", "traces", "points", "uns", "cell_shapes"}
    bad = set(kwargs) - allowed
    if bad:
        raise TypeError(f"streaming from_fofct does not take {sorted(bad)}")
    header_meta, columns, n_skip = _scan_fofct_header(path)
    budget = settings.resolve_budget(memory_budget)
    if chunksize == "auto":
        n_cols = len(columns) if columns else 16
        chunksize = int(min(4_000_000, max(50_000, budget // (8 * 96 * max(n_cols, 1)))))
    reader = pd.read_csv(path, header=None, skiprows=n_skip, chunksize=int(chunksize),
                         skipinitialspace=True, float_precision="round_trip")
    uns = _fofct_uns(kwargs.pop("uns", {}), header_meta)
    companions = _fofct_companions(kwargs, cell_table, rna_table, cell_value_prefix, mapping_table)
    w = ChromDataWriter(out, memory_budget=budget)
    try:
        n_rows = 0
        for df in reader:
            if columns is not None and len(columns) == len(df.columns):
                df.columns = columns
            elif columns is not None:
                df.columns = (columns + [f"col_{i}" for i in range(len(columns), len(df.columns))]
                              )[: len(df.columns)]
            coords, spots = _fofct_core_parts(df)
            del df
            w.append(coords=coords, spots=spots)
            n_rows += len(spots)
            del coords, spots
        if n_rows == 0:
            raise ValueError(f"No data rows found in {path}")
        if companions:
            uns["fofct_companions"] = companions
            _fofct_cell_spatial(uns, kwargs, companions)
            if w._has_cells:
                _warn_unmatched_cells(pd.DataFrame({"cell_id": w.unique("cell_id")}), companions, kwargs)
        w.finish(cells=kwargs.get("cells"), cellm=kwargs.get("cellm"), traces=kwargs.get("traces"),
                 points=kwargs.get("points"), uns=uns, cell_shapes=kwargs.get("cell_shapes"))
    except BaseException:
        if not w._closed:
            w.abort()
        raise
    return cls.read(out, backed=True)


# FOF-CT cell-table columns with a fixed meaning → ChromData.cells names.
_FOFCT_CELL_COLUMNS = {
    "cell_id": "cell_id",
    "extra_cell_roi_id": "extra_cell_roi_id",
    "cent_roi_x": "centroid_x",
    "cent_roi_y": "centroid_y",
    "cent_roi_z": "centroid_z",
    "area(um2)": "nucleus_area_um2",
    "area_cyto(um2)": "cytoplasm_area_um2",
    "keep1": "keep1",
}


def _fofct_cell_table(path: Path, value_prefix: Optional[str]):
    """FOF-CT cell data table → (cells DataFrame indexed by cell_id, meta)."""
    df, meta = _read_fofct_table(path)
    rename = {}
    for col in df.columns:
        key = str(col).strip().lower()
        if key in _FOFCT_CELL_COLUMNS:
            rename[col] = _FOFCT_CELL_COLUMNS[key]
        elif value_prefix and pd.api.types.is_numeric_dtype(df[col]):
            rename[col] = f"{value_prefix}{str(col).strip()}"
    df = df.rename(columns=rename)
    if "cell_id" not in df.columns:
        raise ValueError(f"{path}: cell table has no Cell_ID column; columns: {list(df.columns)}")
    df["cell_id"] = df["cell_id"].astype(str)
    if df["cell_id"].duplicated().any():
        raise ValueError(f"{path}: duplicate Cell_ID values in cell table")
    cells = df.set_index("cell_id")
    return cells, {"source": path.name, "header": meta, "n": int(len(cells))}


# FOF-CT RNA-spot columns → ChromData.points['rna'] names.
_FOFCT_RNA_COLUMNS = {
    "spot_id": "spot_id",
    "x": "x", "y": "y", "z": "z",
    "rna_name": "gene",
    "gene_id": "gene_id",
    "cell_id": "cell_id",
    "extra_cell_roi_id": "extra_cell_roi_id",
    "peak_intensity": "peak_intensity",
}


def _fofct_rna_table(path: Path):
    """FOF-CT RNA spot table → (points DataFrame, meta)."""
    df, meta = _read_fofct_table(path)
    df = df.rename(columns={c: _FOFCT_RNA_COLUMNS.get(str(c).strip().lower(), str(c).strip().lower())
                            for c in df.columns})
    missing = {"x", "y", "z"} - set(df.columns)
    if missing:
        raise ValueError(f"{path}: RNA table missing coordinate columns {missing}")
    if "gene_id" in df.columns:  # 4DN writes lists like "NM_001363480,"
        df["gene_id"] = df["gene_id"].astype(str).str.strip().str.rstrip(",")
    for col in ("cell_id", "gene"):
        if col in df.columns:
            df[col] = df[col].astype(str)
    front = [c for c in ("x", "y", "z", "gene", "gene_id", "cell_id", "spot_id") if c in df.columns]
    df = df[front + [c for c in df.columns if c not in front]]
    return df, {"source": path.name, "header": meta, "n": int(len(df))}


# FOF-CT header fields written as ``##key=value`` (the rest as ``#key: value``).
_FOFCT_REQUIRED_HEADER = ("FOF-CT_version", "Table_namespace", "genome_assembly", "XYZ_unit",
                          "ROI_Boundaries_Format")


def _plain_values(values) -> np.ndarray:
    """Column values for a CSV: categoricals as their values."""
    s = values if isinstance(values, pd.Series) else pd.Series(values)
    if isinstance(s.dtype, pd.CategoricalDtype):
        return np.asarray(s.astype(s.cat.categories.dtype if len(s.cat.categories) else object))
    return s.to_numpy()


def _fofct_header_defaults(uns: Mapping, namespace: str, stored: Mapping,
                           override: Optional[Mapping]) -> Dict[str, str]:
    """Header entries for one table: the stored ones (what ``from_fofct``
    read), filled in from ``uns`` and FOF-CT defaults, then ``override``."""
    lower = {str(k).lower(): k for k in stored}
    meta: Dict[str, str] = {}

    def put(key, value):
        k = lower.get(key.lower(), key)
        meta[k] = str(value)

    for k, v in stored.items():
        meta[str(k)] = str(v)
    if "fof-ct_version" not in lower:
        put("FOF-CT_version", "v0.1")
    if "table_namespace" not in lower:
        put("Table_namespace", namespace)
    if "genome_assembly" not in lower and uns.get("genome_assembly") is not None:
        put("genome_assembly", uns["genome_assembly"])
    if "xyz_unit" not in lower and uns.get("xyz_unit") is not None:
        put("XYZ_unit", uns["xyz_unit"])
    for k, v in (override or {}).items():
        put(str(k), v)
    # required fields first, in the FOF-CT order
    req = {r.lower() for r in _FOFCT_REQUIRED_HEADER}
    first = [k for r in _FOFCT_REQUIRED_HEADER for k in meta if k.lower() == r.lower()]
    return {**{k: meta[k] for k in first}, **{k: v for k, v in meta.items() if k.lower() not in req}}


def _fofct_header_line(key: str, value: str) -> str:
    required = key.lower() in {r.lower() for r in _FOFCT_REQUIRED_HEADER}
    line = f"##{key}={value}" if required else f"#{key}: {value}"
    if "," in line or '"' in line:
        line = '"' + line.replace('"', '""') + '"'   # the 4DN files quote such lines
    return line


def _write_fofct_table(path: Path, table: pd.DataFrame, meta: Mapping[str, str]) -> None:
    """``##`` / ``#`` header lines, ``##columns=(…)`` and the CSV rows."""
    for col in table.columns:
        if "," in str(col) or "\n" in str(col):
            raise ValueError(f"FOF-CT column names cannot contain ',': {col!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        for key, value in meta.items():
            if str(key).lower() == "columns":
                continue
            fh.write(_fofct_header_line(str(key), str(value)) + "\n")
        fh.write("##columns=(" + ",".join(str(c) for c in table.columns) + ")\n")
        table.to_csv(fh, header=False, index=False, lineterminator="\n")


_FOFCT_CELL_NAMES = {v: k for k, v in {
    "Cell_ID": "cell_id", "Extra_Cell_ROI_ID": "extra_cell_roi_id",
    "Cent_ROI_x": "centroid_x", "Cent_ROI_y": "centroid_y", "Cent_ROI_z": "centroid_z",
    "area(um2)": "nucleus_area_um2", "area_cyto(um2)": "cytoplasm_area_um2",
}.items()}


def _fofct_cells_frame(cells: pd.DataFrame, value_prefix: Optional[str]) -> pd.DataFrame:
    """``cd.cells`` → a FOF-CT cell table (``Cell_ID`` first)."""
    if len(cells) == 0 and len(cells.columns) == 0:
        raise ValueError("cell_table= needs cd.cells")
    df = cells.copy()
    if "cell_id" in df.columns:
        df = df.set_index("cell_id")
    out = pd.DataFrame({"Cell_ID": [str(c) for c in df.index]})
    for col in df.columns:
        name = _FOFCT_CELL_NAMES.get(str(col), str(col))
        if value_prefix and name == str(col) and str(col).startswith(value_prefix):
            name = str(col)[len(value_prefix):]
        if name in out.columns:
            raise ValueError(f"cell table column {col!r} maps onto an existing column {name!r}")
        out[name] = _plain_values(df[col].reset_index(drop=True))
    return out


_FOFCT_RNA_NAMES = {"spot_id": "Spot_ID", "x": "X", "y": "Y", "z": "Z", "gene": "RNA_name",
                    "gene_id": "Gene_ID", "cell_id": "Cell_ID",
                    "extra_cell_roi_id": "Extra_Cell_ROI_ID", "peak_intensity": "Peak_Intensity"}


def _fofct_rna_frame(points: pd.DataFrame) -> pd.DataFrame:
    """``points['rna']`` → a FOF-CT RNA spot table."""
    df = points.reset_index(drop=True)
    out = pd.DataFrame(index=pd.RangeIndex(len(df)))
    out["Spot_ID"] = df["spot_id"].to_numpy() if "spot_id" in df.columns else np.arange(len(df))
    for col in ("x", "y", "z"):
        out[_FOFCT_RNA_NAMES[col]] = df[col].to_numpy()
    for col in df.columns:
        if col in ("spot_id", "x", "y", "z"):
            continue
        out[_FOFCT_RNA_NAMES.get(str(col), str(col))] = _plain_values(df[col])
    return out


def _warn_unmatched_cells(spots: pd.DataFrame, companions: dict, kwargs: dict) -> None:
    """Warn when companion tables mention cells the core table lacks (or vice versa)."""
    import warnings

    if "cell_id" not in spots.columns:
        return
    core = {str(x) for x in spots["cell_id"].unique()}
    cells = kwargs.get("cells")
    if "cells" in companions and cells is not None:
        extra = set(cells.index.astype(str)) - core
        missing = core - set(cells.index.astype(str))
        if extra or missing:
            warnings.warn(
                f"FOF-CT cell table: {len(extra)} cells not in the core table, "
                f"{len(missing)} core cells without a cell-table row",
                stacklevel=3,
            )
    rna = (kwargs.get("points") or {}).get("rna")
    if rna is not None and "cell_id" in rna.columns:
        orphan = set(rna["cell_id"]) - core
        if orphan:
            warnings.warn(
                f"FOF-CT RNA table: spots in {len(orphan)} cells not in the core table",
                stacklevel=3,
            )


class _TracksView(pd.DataFrame):
    """The deprecated ``cd.tracks`` view.  ``view[col] = values`` writes
    through to the owning ChromData; other mutations (``.loc[...] = ``)
    only change the view.  Derived frames are plain DataFrames."""

    _metadata = ["_uchrom_owner"]

    @property
    def _constructor(self):
        return pd.DataFrame

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        owner = getattr(self, "_uchrom_owner", None)
        if owner is not None and isinstance(key, str):
            owner._set_track_column(key, self[key].to_numpy())


def _nonempty(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    return df if len(df) > 0 else None


def _empty_frame(n: int, name: Optional[str] = None) -> pd.DataFrame:
    """A column-less DataFrame with ``n`` rows (the empty track tables)."""
    return pd.DataFrame(index=pd.RangeIndex(n, name=name))


def _is_bin_level(table: pd.DataFrame, n_bins: int, n_spots: int) -> bool:
    """Is a ``tracks=`` table bin-aligned?  Yes when its index is named
    ``bin_id``, or when it has ``n_bins`` rows and ``n_bins != n_spots``."""
    if table.index.name == BIN_ID:
        return True
    return len(table) == n_bins and n_bins != n_spots


def _attach_bins(spots: pd.DataFrame, bins: Optional[pd.DataFrame], *, validate: bool = True,
                 copy: bool = True):
    """Return ``(spots, bins)`` with ``spots.bin_id`` and loci derived from bins.

    * no ``bins``: bins are the unique spot loci (spots need
      ``chrom/start/end``).  A ``bin_id`` column is then re-derived — it
      refers to some other object's bins (e.g. spots concatenated from two
      ChromData) — and without loci it is an error;
    * ``bins`` given: ``spots.bin_id`` is used (range-checked), else spot
      loci are looked up in ``bins``.
    """
    if copy:
        spots = spots.copy()
    if bins is None:
        if BIN_ID in spots.columns:
            if not all(c in spots.columns for c in LOCI):
                raise ValueError("spots has a 'bin_id' column but no bins= table was given")
            spots = spots.drop(columns=[BIN_ID])
        bins, bin_id = bins_from_loci(spots)
    else:
        if validate or not (isinstance(bins.index, pd.RangeIndex) and bins.index.name == BIN_ID):
            bins = normalise_bins(bins)
        if BIN_ID in spots.columns:
            bin_id = spots[BIN_ID].to_numpy().astype(np.int64)
            if len(bin_id) and (bin_id.min() < 0 or bin_id.max() >= len(bins)):
                raise ValueError(f"spots.bin_id out of range [0, {len(bins)})")
            if validate and all(c in spots.columns for c in LOCI):
                have = map_loci_to_bins(spots, bins)
                if not np.array_equal(have, bin_id):
                    raise ValueError("spots chrom/start/end disagree with bins[spots.bin_id]")
        else:
            bin_id = map_loci_to_bins(spots, bins)
            if (bin_id < 0).any():
                bad = spots.loc[bin_id < 0, list(LOCI)].head(3).to_dict("records")
                raise ValueError(f"{int((bin_id < 0).sum())} spot locus/loci not in bins, e.g. {bad}")
    spots[BIN_ID] = bin_id
    derived = loci_of(bins, bin_id)
    for pos, col in enumerate(LOCI):
        if col in spots.columns:
            spots[col] = derived[col]
        else:
            spots.insert(pos, col, derived[col])
    return spots, bins


def _linked_records(raw: Any) -> dict[str, dict]:
    """Normalize linked modality metadata to ``key -> record``."""
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        return {"default": {"value": raw}}
    raw_dict = dict(raw)
    if "path" in raw_dict:
        return {"default": _clean_metadata_record(raw_dict)}
    records = {}
    for key, value in raw_dict.items():
        if isinstance(value, Mapping):
            records[str(key)] = _clean_metadata_record(dict(value))
        else:
            records[str(key)] = {"value": value}
    return records


def _linked_record(raw: Any, key: str) -> dict:
    records = _linked_records(raw)
    if key in records:
        return records[key]
    if key == "default" and len(records) == 1:
        return next(iter(records.values()))
    raise KeyError(f"No linked modality record for key {key!r}")


def _set_linked_record(uns: dict, family: str, key: str, record: dict) -> None:
    records = _linked_records(uns.get(family))
    records[str(key)] = record
    uns[family] = records
