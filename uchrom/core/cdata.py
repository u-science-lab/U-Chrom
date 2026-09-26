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
``uchrom.fea``, ``uchrom.emb``, ``uchrom.pl``, ``uchrom.browser``)
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
                                              (raw / corrected / aligned)
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
                            :mod:`uchrom.core.zarrcd` and ``spec.md``.
    <name>.cdz              the same store in one uncompressed zip file.
    <name>.h5cd             HDF5 (below): format 1.x and 2.0 are read;
                            writing it is deprecated.

Both carry two root attributes:

    uchrom_format_version    "MAJOR.MINOR" contract of the file layout
    uchrom_version           uchrom package version that wrote the file

Semantics:

    * **Same MAJOR**  — readable.  Higher MINOR triggers a warning but
      unknown fields are ignored (forward-compatible additive changes).
    * **Different MAJOR** — :exc:`ValueError` on read, with guidance to
      upgrade uchrom or convert the file.
    * **Missing attribute** (pre-versioning files) — warn and assume
      legacy 1.0 layout.

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

New MAJOR versions should add a ``_read_vN`` function at the bottom of
this module and extend the dispatch in :meth:`ChromData.read`.  1.x files
(``coords, spots`` with loci, spot-aligned ``tracks``) are read by
:func:`_read_v1` and upgraded in memory; ``uchrom.io.upgrade_h5cd``
rewrites them as 2.0.

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

See also :mod:`uchrom.core.spec` for a short human-oriented description
of the format, and ``docs/source/guide/chromdata.md`` for tutorial-style
material.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Union, Optional, Dict, List, Mapping

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
from .intervals import IntervalStore, IntervalTable
from .results import ResultRecord, ResultsStore, jsonable as _results_jsonable, validate_value


PathLike = Union[str, Path]

_SPOTS_REQUIRED_COLUMNS = ("bin_id", "trace_id")
_CATEGORICAL_COLUMNS = ("chrom", "trace_id", "cell_id")
_UNS_JSON_PREFIX = "__uchrom_json__:"
_SERIES_COLUMN = "_value"

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
#      :class:`~uchrom.core.results.ResultsStore`).  Each top-level item of
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


class ChromData:
    """Chromatin Data — the core container for U-Chrom.

    See the module docstring of :mod:`uchrom.core.cdata` for the full
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
        Typed interval tables (see :mod:`uchrom.core.intervals`).
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
    results : dict or ResultsStore, optional
        Analysis outputs, stored as a :class:`~uchrom.core.results.ResultsStore`
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

    Attributes
    ----------
    n_spots, n_traces, n_cells, chroms : derived accessors

    Key methods
    -----------
    from_dataframe, from_fofct, read, write, to_dataframe,
    get_cell, get_trace, get_chrom, compute_distances

    On-disk format — ``.h5cd``
    --------------------------
    Versioned HDF5.  See :mod:`uchrom.core.cdata` module docstring for
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
        """Analysis outputs — a :class:`~uchrom.core.results.ResultsStore`.

        Behaves like a ``dict`` of values; assigning a plain ``dict``
        converts it.  Values that cannot be written to ``.h5cd`` raise
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
        :mod:`uchrom.core.intervals`."""
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
                path = Path(path)
                if path.exists():
                    import anndata as ad
                    self._linked_adata = ad.read_h5ad(path)
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
        self._linked_adata = ad.read_h5ad(path)
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
            "path": str(path),
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

    def resolve_link_path(self, path: PathLike) -> Path:
        """Linked-file path; relative paths resolve against the directory of
        the ``.h5cd`` this object was read from (else the working directory),
        so a dataset folder can be moved or shipped as a whole."""
        p = Path(path).expanduser()
        src = getattr(self, "_source_path", None)
        if not p.is_absolute() and src is not None:
            p = Path(src).parent / p
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
        one matrix per file).  The file stays external."""
        path = Path(path)
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

        if cell is None:
            path = str(self.resolve_link_path(path))
            cells = cooler.fileops.list_scool_cells(path)
            return {"path": str(path), "cells": cells, "record": record}

        cell_uri = str(cell)
        if not cell_uri.startswith("/cells/"):
            cell_uri = f"/cells/{cell_uri}"
        return cooler.Cooler(f"{self.resolve_link_path(path)}::{cell_uri}")

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
        """Store cell-level 2D spatial coordinates in ``cells``.

        These coordinates describe cells, not chromatin spots.  They are
        therefore stored in ``cells`` with provenance in
        ``uns['cell_spatial']`` rather than in ``coords``.
        """
        arr = np.asarray(xy, dtype=np.float64)
        if arr.ndim != 2 or arr.shape[1] != 2:
            raise ValueError("xy must have shape (n_cells, 2).")

        if cell_ids is not None:
            axis_ids = self._cells_axis_ids()
            ids = pd.Index([str(x) for x in cell_ids], name="cell_id")
            if len(ids) != arr.shape[0]:
                raise ValueError("cell_ids length must match xy rows.")
            if len(self.cells) == 0:
                self.cells = pd.DataFrame(index=ids)
            else:
                current = pd.Index(axis_ids.astype(str) if axis_ids is not None else self.cells.index.astype(str))
                positions = current.get_indexer(ids)
                if np.any(positions < 0):
                    missing = ids[positions < 0]
                    raise ValueError(f"cell_ids are not present in cells: {list(missing[:5])}")
                aligned = np.full((len(self.cells), 2), np.nan, dtype=np.float64)
                aligned[positions] = arr
                arr = aligned
        elif len(self.cells) == 0:
            raise ValueError("cell_ids are required when cells is empty.")
        elif len(self.cells) != arr.shape[0]:
            raise ValueError("xy rows must match cells rows when cell_ids is not provided.")

        prefix = "" if key == "default" else f"{key}_"
        x_name = x_col or f"{prefix}spatial_x"
        y_name = y_col or f"{prefix}spatial_y"
        self.cells[x_name] = arr[:, 0]
        self.cells[y_name] = arr[:, 1]

        record = {
            "x_col": x_name,
            "y_col": y_name,
            "source": source,
            "method": method,
            "coordinate_system": coordinate_system,
            "inferred": bool(inferred),
            **metadata,
        }
        record = _clean_metadata_record(record)
        _set_linked_record(self.uns, "cell_spatial", key, record)
        return record

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

        for family, expected_format in (("linked_mudata", "h5mu"), ("linked_scool", "scool"),
                                        ("linked_cool", "cool|mcool")):
            records = _linked_records(self.uns.get(family))
            for key, record in records.items():
                path = record.get("path")
                if not path:
                    issues.append(f"{family}.{key} missing path")
                    continue
                if check_files and not self.resolve_link_path(path).exists():
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

        return issues

    @property
    def dataset_references(self) -> List[dict]:
        """Dataset-level source references used as auto-discovery priors.

        References are stored in ``uns['dataset_references']`` and round-trip
        with ``.h5cd`` files.  They are intended for primary dataset papers,
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
    # Deprecated auto-discovery hooks — moved to ``uchrom_discovery``
    # ------------------------------------------------------------------

    @property
    def discovery_schema(self) -> dict:
        """Deprecated: use ``uchrom_discovery.get_discovery_schema(cd)``."""
        return _discovery("get_discovery_schema", "discovery_schema")(self)

    @property
    def auto_discovery_schema(self) -> dict:
        """Deprecated: use ``uchrom_discovery.get_discovery_schema(cd)``."""
        return _discovery("get_discovery_schema", "auto_discovery_schema")(self)

    def build_discovery_schema(self, *, store: bool = True, **kwargs) -> dict:
        """Deprecated: use ``uchrom_discovery.build_discovery_schema(cd, ...)``."""
        return _discovery("build_discovery_schema", "build_discovery_schema")(
            self, store=store, **kwargs
        )

    def update_discovery_schema(self, schema: Optional[dict] = None, **kwargs) -> dict:
        """Deprecated: use ``uchrom_discovery.store_discovery_schema(cd, ...)``."""
        return _discovery("store_discovery_schema", "update_discovery_schema")(
            self, schema, **kwargs
        )

    def validate_discovery_schema(
        self,
        schema: Optional[dict] = None,
        *,
        raise_on_error: bool = False,
    ) -> List[str]:
        """Deprecated: use ``uchrom_discovery.validate_discovery_schema(...)``."""
        return _discovery("validate_discovery_schema", "validate_discovery_schema")(
            schema, self, raise_on_error=raise_on_error
        )

    def describe_for_agent(self, *, max_items: int = 40) -> str:
        """Deprecated: use ``uchrom_discovery.describe_for_agent(cd)``."""
        return _discovery("describe_for_agent", "describe_for_agent")(
            self, max_items=max_items
        )

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

    def _categorify(self):
        for col in _CATEGORICAL_COLUMNS:
            if col in self.spots.columns and not hasattr(self.spots[col].dtype, "categories"):
                self.spots[col] = self.spots[col].astype("category")

    # ------------------------------------------------------------------
    # Subsetting
    # ------------------------------------------------------------------

    def __getitem__(self, index) -> "ChromData":
        if isinstance(index, slice):
            index = np.arange(*index.indices(self.n_spots))
        if isinstance(index, (pd.Series, np.ndarray)):
            if index.dtype == bool:
                index = np.where(index)[0]
        idx = np.asarray(index)

        new_coords = self.coords[idx]
        new_spots = self.spots.iloc[idx].reset_index(drop=True)
        new_spot_tracks = self._spot_tracks.iloc[idx].reset_index(drop=True)
        new_layers = {k: v[idx] for k, v in self.layers.items()}

        # Filter traces/cells to those still referenced
        new_traces = self._filter_traces(new_spots)
        new_cells, new_cellm = self._filter_cells(new_spots)
        new_points = self._filter_points(new_spots)

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
            linked_adata=None,
            validate=False,
        )
        out._bin_tracks = self._bin_tracks
        out._spot_tracks = new_spot_tracks
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

    def get_cell(self, cell_id) -> "ChromData":
        if "cell_id" not in self.spots.columns:
            raise KeyError("spots has no 'cell_id' column")
        mask = self.spots["cell_id"] == cell_id
        return self[mask.values]

    def get_trace(self, trace_id) -> "ChromData":
        mask = self.spots["trace_id"] == trace_id
        return self[mask.values]

    def get_chrom(self, chrom: str) -> "ChromData":
        ids = np.where(self._bins["chrom"].astype(str).to_numpy() == str(chrom))[0]
        mask = np.isin(self.spots[BIN_ID].to_numpy(), ids)
        return self[mask]

    # ------------------------------------------------------------------
    # Streaming access (same batches in memory and backed)
    # ------------------------------------------------------------------

    @property
    def backed(self) -> bool:
        """``True`` for a :class:`~uchrom.core.backed.BackedChromData`."""
        return False

    def to_memory(self) -> "ChromData":
        """An in-memory ``ChromData`` (``self`` — this object already is)."""
        return self

    def _sorted_segments(self):
        from .zarrcd import _segments, _spot_keys, sort_order

        cell, trace, bin_id = _spot_keys(self)
        order = sort_order(cell, trace, bin_id)
        if order is not None:
            cell, trace = cell[order], trace[order]
        seg, cel = _segments(cell, trace)
        return order, seg, cel

    def iter_traces(self, batch: int = 1024):
        """Yield in-memory ``ChromData`` chunks of ``batch`` traces.

        Traces are visited in (cell, trace) order — a trace id shared by
        several cells counts once per cell — with the spots of a trace in
        bin order, exactly as a ``.chromdata.zarr`` store holds them; a
        backed object yields identical chunks while reading one row range
        per chunk.
        """
        order, seg, _ = self._sorted_segments()
        n_seg = len(seg) - 1
        for i in range(0, n_seg, max(1, int(batch))):
            a, b = int(seg[i]), int(seg[min(i + int(batch), n_seg)])
            yield self[order[a:b] if order is not None else np.arange(a, b)]

    def iter_cells(self, batch: int = 64):
        """Yield in-memory ``ChromData`` chunks of ``batch`` cells (cell id
        order; see :meth:`iter_traces`)."""
        if "cell_id" not in self.spots.columns:
            raise KeyError("spots has no 'cell_id' column")
        order, _, cel = self._sorted_segments()
        n = len(cel) - 1
        for i in range(0, n, max(1, int(batch))):
            a, b = int(cel[i]), int(cel[min(i + int(batch), n)])
            yield self[order[a:b] if order is not None else np.arange(a, b)]

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
        are not flattened into AnnData.X.

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
        compression: Optional[str] = "gzip",
        compression_opts: Optional[int] = 4,
        compress_floats: bool = False,
    ) -> None:
        """Write to disk; the format follows the path.

        * ``<name>.chromdata.zarr`` (any ``*.zarr``) — **the format 2.0
          container**: a Zarr v3 directory whose large tables are Parquet
          (see :mod:`uchrom.core.zarrcd` and ``spec.md``).  Spots are
          written sorted by (cell, trace, bin) with ``index/`` offsets, so
          :meth:`read` can open the store backed.
        * ``<name>.cdz`` — the same tree in one uncompressed zip file.
        * ``<name>.h5cd`` — HDF5 format 2.0 (**deprecated**; readable
          indefinitely, still written in this release, with a
          ``DeprecationWarning``).  Other suffixes also write HDF5, as
          before.

        ``format="zarr" | "cdz" | "h5cd"`` overrides the suffix.

        **Row order.**  The zarr / cdz writer stores spots sorted by
        (``cell_id`` code, ``trace_id`` code, ``bin_id``) — a stable sort,
        so ties keep their order.  Reading returns that order; every spot
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
            (default 65,536).  Groups end on cell boundaries.
        compression_level : int, optional
            zstd level for Parquet and Zarr (default 3).
        keep_source_order : bool
            Store ``index/source_row`` when the writer had to sort.

        Parameters (h5cd)
        -----------------
        compression : ``"gzip"`` (default), ``"lzf"`` or ``None``
            Filter for the large integer / string datasets (``bin_id``,
            categorical codes, string columns, integer tracks).  gzip is
            part of every HDF5 build; lzf ships with h5py.  Datasets below
            4,096 elements are stored contiguously, uncompressed.
        compression_opts : int, optional
            gzip level (default 4); ignored for ``"lzf"``.
        compress_floats : bool
            Also compress float datasets (``coords``, ``layers``, float
            tracks).  Off by default: on real tracing data it saves only
            ~15-20 % while making full reads ~4x slower (see the format
            2.0 notes in ``docs/source/guide/chromdata_2_0_design.md``).
        """
        import h5py

        from .zarrcd import container_kind, write_zarr

        path = Path(path)
        kind = format or container_kind(path) or "h5cd"
        if kind not in ("zarr", "cdz", "h5cd"):
            raise ValueError("format must be 'zarr', 'cdz' or 'h5cd'")
        if kind == "cdz" and not path.name.lower().endswith(".cdz"):
            raise ValueError("a .cdz store needs a path ending in .cdz")
        if kind == "zarr" and not path.name.lower().endswith(".zarr"):
            raise ValueError("a zarr store needs a path ending in .chromdata.zarr (or .zarr)")
        if kind in ("zarr", "cdz"):
            from .zarrcd import DEFAULT_ROW_GROUP_ROWS, DEFAULT_ZSTD_LEVEL
            write_zarr(self, path, coord_dtype=coord_dtype,
                       row_group_rows=row_group_rows or DEFAULT_ROW_GROUP_ROWS,
                       compression_level=(DEFAULT_ZSTD_LEVEL if compression_level is None
                                          else compression_level),
                       keep_source_order=keep_source_order)
            return
        import warnings
        warnings.warn(
            f"writing {path.name}: the HDF5 .h5cd format is deprecated; write "
            f"'<name>.chromdata.zarr' (or '.cdz') instead.  .h5cd files stay readable.",
            DeprecationWarning,
            stacklevel=2,
        )

        try:
            from uchrom import __version__ as _uchrom_version
        except Exception:
            _uchrom_version = "unknown"

        self._check_bin_ids()
        if compression not in (None, "gzip", "lzf"):
            raise ValueError("compression must be 'gzip', 'lzf' or None")
        _WRITE_OPTS.update(compression=compression, compress_floats=bool(compress_floats),
                           compression_opts=compression_opts if compression == "gzip" else None)
        try:
            self._write_h5(h5py, path, _uchrom_version)
        finally:
            _WRITE_OPTS.update(compression=None, compression_opts=None, compress_floats=False)

    def _write_h5(self, h5py, path: Path, _uchrom_version: str) -> None:
        spots = self.spots.drop(columns=[c for c in LOCI if c in self.spots.columns])
        spots[BIN_ID] = spots[BIN_ID].to_numpy().astype(
            np.int32 if self.n_bins < 2 ** 31 else np.int64)
        with h5py.File(path, "w") as f:
            f.attrs["uchrom_format_version"] = FORMAT_VERSION
            f.attrs["uchrom_version"] = _uchrom_version
            f.attrs["spot_order"] = "unsorted"
            _write_dataframe(f, "bins", self._bins.reset_index(drop=True))
            _create_dataset(f, "coords", self.coords)
            _write_dataframe(f, "spots", spots)
            f["spots"].attrs["_column_order"] = json.dumps([str(c) for c in self.spots.columns])
            _write_dataframe(f, "tracks", self._bin_tracks.reset_index(drop=True),
                             n_rows=self.n_bins)
            _write_dataframe(f, "spot_tracks", self._spot_tracks, n_rows=self.n_spots)
            if self._spot_view_order:
                f["spot_tracks"].attrs["_spot_view_order"] = json.dumps(self._spot_view_order)
            _write_dict_of_arrays(f, "binm", self.binm)
            _write_dataframe(f, "cells", self.cells)
            _write_dataframe(f, "traces", self.traces)
            _write_dict_of_arrays(f, "layers", self.layers)
            _write_dict_of_arrays(f, "cellm", self.cellm)
            grp = f.create_group("intervals")
            for key, table in self._intervals.items():
                _write_dataframe(grp, key, pd.DataFrame(table))
                grp[key].attrs["_kind"] = table.kind or ""
                grp[key].attrs["_source_result"] = table.source_result or ""
            _write_results(f, "results", self.results, intervals=self._intervals)
            _write_uns(f, "uns", self.uns)
            if self.points:
                grp = f.create_group("points")
                for key, df in self.points.items():
                    if "/" in key or not key:
                        raise ValueError(f"points key must be non-empty without '/': {key!r}")
                    _write_dataframe(grp, key, df)

    @classmethod
    def read(cls, path: PathLike, *, backed: bool = False,
             original_order: bool = False) -> "ChromData":
        """Read a ChromData file; the format follows the path.

        * ``.chromdata.zarr`` / ``.cdz`` (format 2.0 container) — with
          ``backed=True`` returns a :class:`~uchrom.core.backed.BackedChromData`:
          small tables are loaded, ``coords`` / ``spots`` / ``spot_tracks``
          / ``layers`` stay on disk, and ``get_cell`` / ``get_trace`` /
          ``get_chrom`` / ``iter_traces`` / ``iter_cells`` read only the
          rows they need.  Spots come back in the stored (cell, trace, bin)
          order; ``original_order=True`` restores the order of the object
          that was written (in-memory reads only).
        * ``.h5cd`` — HDF5, format 1.x or 2.0 (below); always in memory.

        HDF5 ``.h5cd``: dispatches to a version-specific reader based on
        ``f.attrs['uchrom_format_version']``: MAJOR 2 → :func:`_read_v2`,
        MAJOR 1 → :func:`_read_v1`, which upgrades the file in memory
        (bins derived from the spot loci; the spot-aligned 1.x ``tracks``
        split into ``bin_tracks`` / ``spot_tracks``).  Files written before
        versioning was introduced are read with a warning as 1.0.

        Forward compatibility:

        - Same MAJOR, higher MINOR  → read with a warning; unknown fields
          are ignored silently by the lower-level helpers.
        - Different MAJOR           → raise ``ValueError`` with guidance.
        """
        import warnings
        import h5py

        from .zarrcd import container_kind

        path = Path(path)
        kind = container_kind(path)
        if kind in ("zarr", "cdz"):
            from .backed import BackedChromData

            if not path.exists():
                raise FileNotFoundError(path)
            b = BackedChromData(path)
            _check_zarr_version(path, b._c.meta.get("format_version", "2.0"))
            if backed:
                if original_order:
                    raise ValueError("original_order=True needs an in-memory read (backed=False)")
                return b
            cd = b.to_memory()
            if original_order and b._c.meta.get("has_source_row"):
                src = b._c.array("index/source_row")
                _permute_spot_rows(cd, np.argsort(src, kind="stable"))
            return cd
        if backed:
            raise ValueError(
                f"{path}: backed mode needs the .chromdata.zarr / .cdz format; convert with "
                f"`python -m uchrom.io.upgrade {path} {path.with_suffix('.chromdata.zarr')}`"
            )
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
            cd = _read_v1(cls, f) if major == 1 else _read_v2(cls, f)
        cd._source_path = path
        return cd

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
        cell_value_prefix: Optional[str] = "rna.",
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
        rna_table : path, optional
            FOF-CT *RNA spot* table (``4dn_FOF-CT_rna``).  Loaded into
            ``points['rna']`` with columns ``x, y, z, gene, gene_id,
            cell_id, spot_id, …`` in the same frame as ``coords``.
        cell_value_prefix : str or None
            Prefix for unrecognised numeric cell-table columns; ``None``
            keeps their names.
        **kwargs
            Additional keyword arguments passed to ChromData constructor
            (e.g. cells, tracks, uns).
        """
        path = Path(core_path)
        df, header_meta = _read_fofct_table(path)
        if not any(str(c).lower() == "x" for c in df.columns):
            # no column names in the file: assume the core-table order
            default_cols = ["Spot_ID", "Trace_ID", "X", "Y", "Z",
                            "Chrom", "Chrom_Start", "Chrom_End"]
            n = len(df.columns)
            df.columns = default_cols[:n] + [f"col_{i}" for i in range(len(default_cols), n)]

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
        rename = {c: canonical_map[str(c).lower()] for c in df.columns if str(c).lower() in canonical_map}
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

        companions = {}
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
        if companions:
            uns["fofct_companions"] = companions
            _warn_unmatched_cells(spots, companions, kwargs)

        return cls(coords, spots, uns=uns, **kwargs)

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
                "Install with `pip install u-chrom[im]` or `pip install astropy`."
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
        from uchrom.io.seqfish_multiomics import read_seqfish_multiomics
        return read_seqfish_multiomics(spot_glob, **kwargs)

    @classmethod
    def from_seqfish_multiomics_linked(cls, spot_glob, **kwargs):
        """Load linked Takei 2025 DNA tracing + RNA AnnData artifacts.

        Thin shim around
        :func:`uchrom.io.seqfish_multiomics.load_seqfish_multiomics_linked`.
        Returns a ``ChromData`` with RNA expression available at
        ``cd.linked_adata`` and can write paired ``.h5cd`` / ``.h5ad``
        files.
        """
        from uchrom.io.seqfish_multiomics import load_seqfish_multiomics_linked
        return load_seqfish_multiomics_linked(spot_glob, **kwargs)

    @classmethod
    def from_takei2025_cerebellum(cls, **kwargs):
        """Load linked Takei 2025 cerebellum data.

        Thin shim around
        :func:`uchrom.io.seqfish_multiomics.load_takei2025_cerebellum`.
        Returns a ``ChromData`` with RNA expression available at
        ``cd.linked_adata``.
        """
        from uchrom.io.seqfish_multiomics import load_takei2025_cerebellum
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

def _discovery(func_name: str, method_name: str):
    """Resolve a ``uchrom_discovery`` function for a deprecated ChromData hook."""
    import warnings

    warnings.warn(
        f"ChromData.{method_name} is deprecated; use "
        f"uchrom_discovery.{func_name}(cd, ...) instead.",
        DeprecationWarning,
        stacklevel=3,
    )
    try:
        import uchrom_discovery
    except ImportError as exc:
        raise ImportError(
            f"ChromData.{method_name} needs the separate 'uchrom-discovery' "
            f"package (`pip install -e discovery/` from the U-Chrom repository)."
        ) from exc
    return getattr(uchrom_discovery, func_name)


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
    """Same MAJOR / MINOR rules as ``.h5cd`` for the zarr container."""
    import warnings

    major, minor = _parse_version(str(version_str))
    cur_major, cur_minor = _parse_version(FORMAT_VERSION)
    if major != cur_major:
        raise ValueError(
            f"{path}: format version {version_str} has incompatible MAJOR with this "
            f"uchrom (supports {cur_major}.x). Upgrade uchrom or convert the file."
        )
    if minor > cur_minor:
        warnings.warn(
            f"{path}: written with format version {version_str} (reader supports up "
            f"to {FORMAT_VERSION}). Forward-compatible — unknown fields will be ignored.",
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
            if stripped.lower().startswith("##columns="):
                cols_str = stripped.split("=", 1)[1].strip()
                # remove one enclosing pair only: str.strip("()") would also
                # eat the ")" of a last column such as "n_per_dist(um)"
                if cols_str.startswith("(") and cols_str.endswith(")"):
                    cols_str = cols_str[1:-1]
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
    # the first non-comment line starts with a non-numeric token, treat it
    # as a CSV header.
    first_token = data_lines[0].split(",", 1)[0].strip().strip('"')
    has_csv_header = bool(first_token) and not (
        first_token[0].isdigit() or first_token[0] in ("-", "+", ".")
    )
    if has_csv_header and columns is not None and first_token not in columns:
        has_csv_header = False  # e.g. cell tables whose first column is an id like "0_1"
    if has_csv_header:
        header_row = data_lines[0]
        data_lines = data_lines[1:]
        if columns is None:
            columns = [c.strip() for c in header_row.split(",")]

    if not data_lines:
        raise ValueError(f"No data rows found in {path}")

    from io import StringIO as _StringIO
    df = pd.read_csv(_StringIO("\n".join(data_lines)), header=None, skipinitialspace=True)
    if columns is not None and len(columns) == len(df.columns):
        df.columns = columns
    elif columns is not None:
        # Column count mismatch — trust the data and label the extras
        df.columns = (columns + [f"col_{i}" for i in range(len(columns), len(df.columns))])[: len(df.columns)]
    return df, header_meta


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
