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

    coords      (n_spots, 3) ndarray         x, y, z per spot
    spots       DataFrame (n_spots, ≥4)      chrom, start, end, trace_id,
                                              [cell_id, spot_id, ...]
    cells       DataFrame (n_cells, ?)       cell_type, position, ...
    cellm       dict[str, ndarray]            per-cell multi-dim
                                              (embedding, UMAP, ...)
    tracks      DataFrame (n_spots, n_track) epigenomic signals aligned
                                              to spots (ATAC, ChIP, ...)
    traces      DataFrame (n_traces, ?)      trace-level metadata
    layers      dict[str, (n_spots, 3)]      alt. coordinate sets
                                              (raw / corrected / aligned)
    results     dict                          analysis outputs
                                              (loops, tads, compartments)
    uns         dict                          unstructured metadata
                                              (genome_assembly, xyz_unit,
                                              fofct_header, ...)

See :attr:`_SPOTS_REQUIRED_COLUMNS` below for the contract on ``spots``.

Spot required columns
---------------------
    chrom      str (stored as ``pd.Categorical``)
    start      int, 0-based BED-style start
    end        int, non-inclusive end
    trace_id   int or str (stored as ``pd.Categorical``)

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

On-disk format — ``.h5cd``
--------------------------
HDF5 with two root-group attributes:

    uchrom_format_version    "MAJOR.MINOR" contract of the file layout
    uchrom_version           uchrom package version that wrote the file

Semantics:

    * **Same MAJOR**  — readable.  Higher MINOR triggers a warning but
      unknown fields are ignored (forward-compatible additive changes).
    * **Different MAJOR** — :exc:`ValueError` on read, with guidance to
      upgrade uchrom or convert the file.
    * **Missing attribute** (pre-versioning files) — warn and assume
      legacy 1.0 layout.

Layout::

    data.h5cd
    ├── @uchrom_format_version  = "1.0"
    ├── @uchrom_version         = "0.2.0"
    ├── coords               (n_spots, 3) float64
    ├── spots/               group — one dataset per DataFrame column
    ├── cells/               group
    ├── tracks/              group
    ├── traces/              group
    ├── cellm/               group of (n_cells, ...) ndarrays per key
    ├── layers/              group of (n_spots, 3) ndarrays per key
    ├── results/             group — DataFrames as sub-groups,
    │                         arrays as datasets
    └── uns/                 nested group — scalars as attrs,
                              dicts as sub-groups

New MAJOR versions should add a ``_read_vN`` function at the bottom of
this module and extend the dispatch in :meth:`ChromData.read`.

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


PathLike = Union[str, Path]

_SPOTS_REQUIRED_COLUMNS = ("chrom", "start", "end", "trace_id")
_CATEGORICAL_COLUMNS = ("chrom", "trace_id", "cell_id")
_UNS_JSON_PREFIX = "__uchrom_json__:"

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
FORMAT_VERSION = "1.1"
_SUPPORTED_MAJOR = 1


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
    spots : DataFrame, shape (n_spots, ≥4)
        Per-spot metadata.  **Required columns:**
        ``chrom`` (str, will be categorified),
        ``start`` (int, 0-based BED-style),
        ``end`` (int, non-inclusive),
        ``trace_id`` (int or str, will be categorified).
        Optional: ``cell_id`` (int or str), ``spot_id``, FOF-CT
        ``sub_cell_roi_id`` / ``extra_cell_roi_id``, and any
        experiment-specific annotation column (carried through
        verbatim).
    cells : DataFrame, optional
        Per-cell metadata indexed by cell_id.
    cellm : dict[str, ndarray], optional
        Per-cell multi-dimensional annotations (embeddings, UMAP, …).
        Each array's first axis length = ``n_cells``.
    tracks : DataFrame, optional
        Epigenomic signals (ATAC, ChIP-seq, …) row-aligned to ``spots``.
        Length must equal ``n_spots``.
    traces : DataFrame, optional
        Per-trace metadata indexed by trace_id.
    layers : dict[str, ndarray], optional
        Alternative coordinate sets, each with shape ``(n_spots, 3)`` —
        e.g. raw / drift-corrected / aligned.
    results : dict, optional
        Analysis outputs.  Conventional keys:
        ``'loops'`` → DataFrame (chrom1, start1, end1, …),
        ``'tads'`` → DataFrame (chrom, start, end, …),
        ``'compartments'`` → ndarray or DataFrame per bin.
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
        cells: Optional[pd.DataFrame] = None,
        cellm: Optional[Dict[str, np.ndarray]] = None,
        tracks: Optional[pd.DataFrame] = None,
        traces: Optional[pd.DataFrame] = None,
        layers: Optional[Dict[str, np.ndarray]] = None,
        results: Optional[dict] = None,
        uns: Optional[dict] = None,
        linked_adata=None,
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
        self._linked_adata = linked_adata

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
        return md.read_h5mu(path)

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
            cells = cooler.fileops.list_scool_cells(path)
            return {"path": str(path), "cells": cells, "record": record}

        cell_uri = str(cell)
        if not cell_uri.startswith("/cells/"):
            cell_uri = f"/cells/{cell_uri}"
        return cooler.Cooler(f"{path}::{cell_uri}")

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

        for family, expected_format in (("linked_mudata", "h5mu"), ("linked_scool", "scool")):
            records = _linked_records(self.uns.get(family))
            for key, record in records.items():
                path = record.get("path")
                if not path:
                    issues.append(f"{family}.{key} missing path")
                    continue
                if check_files and not Path(path).exists():
                    issues.append(f"{family}.{key} path does not exist: {path}")
                fmt = record.get("format")
                if fmt and str(fmt) != expected_format:
                    issues.append(f"{family}.{key} format={fmt!r} != {expected_format!r}")

        for key, record in _linked_records(self.uns.get("linked_scool")).items():
            if record.get("coordinate_status") in {None, ""}:
                issues.append(f"linked_scool.{key} missing coordinate_status")
            if check_files and record.get("path") and Path(record["path"]).exists():
                try:
                    import cooler

                    if not cooler.fileops.is_scool_file(record["path"]):
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

    @property
    def discovery_schema(self) -> dict:
        """Agent-readable auto-discovery schema for this ``ChromData``.

        If a schema is stored in ``uns['auto_discovery_schema']`` it is
        parsed and returned.  Otherwise a fresh in-memory schema is built
        without mutating ``uns``.
        """
        from uchrom.auto_discovery.schema import (
            DISCOVERY_SCHEMA_KEY,
            build_discovery_schema,
            unpack_schema,
        )

        raw = self.uns.get(DISCOVERY_SCHEMA_KEY)
        if raw is not None:
            return unpack_schema(raw)
        return build_discovery_schema(self)

    @property
    def auto_discovery_schema(self) -> dict:
        """Alias for :attr:`discovery_schema`."""
        return self.discovery_schema

    def build_discovery_schema(self, *, store: bool = True, **kwargs) -> dict:
        """Build the auto-discovery schema, optionally storing it in ``uns``.

        The stored representation is an HDF5-friendly JSON payload under
        ``uns['auto_discovery_schema']``, so it round-trips with ``.h5cd``.
        """
        from uchrom.auto_discovery.schema import (
            DISCOVERY_SCHEMA_KEY,
            build_discovery_schema,
            pack_schema,
        )

        schema = build_discovery_schema(self, **kwargs)
        if store:
            self.uns[DISCOVERY_SCHEMA_KEY] = pack_schema(schema)
        return schema

    def update_discovery_schema(self, schema: Optional[dict] = None, **kwargs) -> dict:
        """Store a supplied or newly built auto-discovery schema in ``uns``."""
        from uchrom.auto_discovery.schema import DISCOVERY_SCHEMA_KEY, pack_schema

        if schema is None:
            return self.build_discovery_schema(store=True, **kwargs)
        self.uns[DISCOVERY_SCHEMA_KEY] = pack_schema(schema)
        return schema

    def validate_discovery_schema(
        self,
        schema: Optional[dict] = None,
        *,
        raise_on_error: bool = False,
    ) -> List[str]:
        """Validate a discovery schema against this ``ChromData``.

        Returns a list of issues.  If ``raise_on_error=True``, raises
        ``ValueError`` when any issue is found.
        """
        from uchrom.auto_discovery.schema import validate_discovery_schema

        issues = validate_discovery_schema(schema or self.discovery_schema, cdata=self)
        if issues and raise_on_error:
            raise ValueError("; ".join(issues))
        return issues

    def describe_for_agent(self, *, max_items: int = 40) -> str:
        """Return a compact prompt-ready description of available data."""
        from uchrom.auto_discovery.schema import schema_to_agent_context

        return schema_to_agent_context(self.discovery_schema, max_items=max_items)

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
            linked_adata=None,
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
            linked_adata=self._linked_adata.copy() if self._linked_adata is not None else None,
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
    """Write a DataFrame to an HDF5 group, one dataset per column.

    Format 1.1: when the index is not a trivial ``RangeIndex`` or has a
    name, it is written to a reserved ``_index`` dataset with the name
    stored in ``_index_name``.  Old (1.0) readers ignore both and
    reconstruct a default RangeIndex — the historical behaviour.
    """
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
            data = np.array([str(x) for x in idx_vals]).astype("S")
        else:
            data = idx_vals
        grp.create_dataset("_index", data=data)
        grp.attrs["_index_name"] = idx.name if idx.name is not None else ""


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
    df = pd.DataFrame(data)
    # Format 1.1: restore the index if it was persisted.
    if "_index" in grp:
        idx_arr = grp["_index"][:]
        if idx_arr.dtype.kind == "S":
            idx_arr = np.array([x.decode("utf-8") for x in idx_arr])
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
