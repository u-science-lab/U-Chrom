# ChromData Specification

## Overview

`ChromData` is the core data container for U-Chrom, designed for chromatin 3D structure data. It follows the same philosophy as [AnnData](https://anndata.readthedocs.io/) — a single object that holds all data, metadata, and analysis results, and can be persisted to disk.

The central idea: **genomic bins mapped to 3D coordinates**, produced either from sequencing-based reconstruction (Hi-C, Dip-C) or imaging-based chromatin tracing (ORCA, MERFISH, seqFISH).

## Data Hierarchy

```
Cell
 └── Trace (one chromatin fiber / allele)
      └── Spot (one genomic bin with x, y, z)
```

- A **Spot** is one genomic bin (chrom, start, end) with a 3D position (x, y, z).
- A **Trace** is an ordered chain of Spots along a chromatin fiber.
- A **Cell** contains one or more Traces.

## Attributes

### Locus axis (format 2.0)

| Attribute | Type | Shape | Description |
|-----------|------|-------|-------------|
| `bins` | DataFrame | (n_bins, ≥3) | Index `bin_id` (0..n_bins-1). Columns `chrom` (categorical), `start`, `end` (int64), optional `resolution`, `name`, … One row per locus, shared by all cells. |
| `bin_tracks` | DataFrame | (n_bins, ?) | Per-locus signals (bulk ATAC / ChIP, GC, annotation features, compartment score). |
| `binm` | dict[str, ndarray] | (n_bins, …) | Per-locus multi-dimensional arrays. |
| `intervals` | dict[str, IntervalTable] | — | Typed interval tables: `domain` (chrom, start, end), `pair` (chrom1…end2), `peak`, `segment` (+ label). `attrs`: `kind`, `source_result`. |

### Core Table (FOF-CT compatible)

| Attribute | Type | Shape | Description |
|-----------|------|-------|-------------|
| `coords` | ndarray | (n_spots, 3) | 3D coordinates. Column order: x, y, z. |
| `spots` | DataFrame | (n_spots, ≥2) | Spot metadata. See columns below. |
| `spot_tracks` | DataFrame | (n_spots, ?) | Per-spot signals (IF intensity, seqFISH z-scores). |

**`spots` columns:**

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `bin_id` | int | yes | Row of `bins` this spot observes (derived from chrom/start/end when not given). |
| `trace_id` | int or str (categorical) | yes | Which Trace this Spot belongs to. |
| `chrom` / `start` / `end` | derived | — | Filled from `bins[bin_id]` (0-based, end-exclusive); not stored on disk. `cd.spots_with_loci()` is the stable accessor. |
| `cell_id` | int or str (categorical) | no | Which Cell this Spot belongs to. |
| `spot_id` | int or str | no | Globally unique Spot identifier. |

### Cell Table

| Attribute | Type | Shape | Description |
|-----------|------|-------|-------------|
| `cells` | DataFrame | (n_cells, ?) | Cell-level metadata. Index = cell_id. |
| `cellm` | dict[str, ndarray] | varies | Per-cell multi-dimensional annotations. |

`cells` can hold columns like `cell_type`, `x_centroid`, `y_centroid`, `z_centroid`, etc.

`cellm` stores arrays aligned to the cells axis, e.g.:
- `cellm['embedding']` — shape (n_cells, 128), single-cell structure embeddings.
- `cellm['umap']` — shape (n_cells, 2), UMAP coordinates.

### Tracks

`bin_tracks` (per locus) and `spot_tracks` (per spot) replace the 1.x
spot-aligned `tracks`.  During 2.x, `cd.tracks` is a deprecated
spot-aligned view of both (`cd.tracks_spot_view()` without the warning).

### Additional Storage

| Attribute | Type | Description |
|-----------|------|-------------|
| `traces` | DataFrame (n_traces) | Trace-level metadata. Index = trace_id. |
| `layers` | dict[str, ndarray] | Alternative coordinate representations, each (n_spots, 3). e.g. `layers['raw']` for uncorrected coordinates. |
| `points` | dict[str, DataFrame] | Non-genomic 3-D points in the `coords` frame (columns `x, y, z` + e.g. `cell_id`, `gene`): nascent RNA spots, IF puncta. Subsetting keeps the points of retained cells. Format ≥ 1.3. |
| `results` | `ResultsStore` | Analysis results with provenance. Dict-like: `cd.results[key]` is the value, `cd.results.record(key)` a `ResultRecord` (`kind, value, params, function, uchrom_version, inputs, created_utc`). Values may be DataFrames, Series, ndarrays, nested dicts of these, or JSON-compatible scalars / lists; anything else raises `TypeError` on assignment. |
| `uns` | dict | Unstructured metadata (genome assembly, coordinate unit, etc.). |

### Results Convention

Keys are `"<what>.<method>"`; the structure callers merge all
chromosomes into one table per key.

| Key | kind | Description |
|-----|------|-------------|
| `'tads.arcfish'` | intervals | chrom, start, end, level, score, pval, fdr |
| `'tads.fishnet'` (+ `'.ensemble'` mapping) | intervals | chrom, trace_id, domain_idx, start, end, start_bin, end_bin |
| `'tads.di'` | intervals | chrom, start, end, start_bin, end_bin |
| `'loops.axiswise_f'` | intervals | chrom1, start1, end1, chrom2, start2, end2, score, pval, fdr, … |
| `'compartments.axes_pc'` | table | one row per bin: chrom, start, end, bin_index, cluster, compartment, pc2 |

1.x keys (`'tads'`, `'loops'`, `'compartments'`) are still produced by
the deprecated call forms and still read by `add_structural_features`.

## API

### Construction

```python
from uchrom import ChromData

# Direct
cd = ChromData(coords, spots)
cd = ChromData(coords, spots, cells=cells, tracks=tracks, uns={'genome_assembly': 'GRCh38'})

# From reconstruction output CSV (chrom, start, end, x, y, z)
cd = ChromData.from_dataframe(df)

# From FOF-CT core table
cd = ChromData.from_fofct('4dn_FOF-CT_core.csv')
```

### Properties

```python
cd.n_spots      # Total number of spots
cd.n_traces     # Number of traces
cd.n_cells      # Number of cells
cd.chroms       # List of chromosome names
```

### Subsetting

All subsetting methods return a new `ChromData` with consistent filtering across all attributes.

```python
cd[0:100]                            # Slice by spot index
cd[cd.spots['chrom'] == 'chr1']      # Boolean mask

cd.get_chrom('chr1')                 # By chromosome
cd.get_trace(trace_id)               # By trace
cd.get_cell(cell_id)                 # By cell
```

### On-demand Computation

Pairwise distance matrices are computed per-trace, not stored globally.

```python
dist = cd.compute_distances(trace_id=0)   # (n_spots_in_trace, n_spots_in_trace)
```

### Export

```python
df = cd.to_dataframe()   # Flat DataFrame: chrom, start, end, x, y, z, trace_id, ...
```

### Persistence

```python
cd.write('data.chromdata.zarr')                    # format 2.1: Zarr v3 + Parquet (a directory)
cd.write('data.cdz')                               # the same store in one zip file
cd = ChromData.read('data.chromdata.zarr')         # in memory (spots in stored order)
cd = ChromData.read('data.chromdata.zarr', original_order=True)   # rows as written
cd = ChromData.read('data.chromdata.zarr', backed=True)           # out of core
cd = ChromData.read('data.chromdata.zarr', columns='coords')      # xyz + key columns only
with ChromData.writer('big.chromdata.zarr') as w:  # streaming writer (chunks larger than RAM)
    w.append(chunk)
cd = ChromData.read('old.h5cd')                    # HDF5 1.x / 2.0: still read
```

The format follows the path: `*.zarr` → Zarr directory, `*.cdz` → zip,
`*.h5cd` → HDF5 (deprecated for writing; `DeprecationWarning`).  An
existing path without one of these suffixes is sniffed.
`python -m uchrom.io.upgrade old.h5cd` converts to
`old.chromdata.zarr` (and rewrites a 2.0 `.chromdata.zarr` as 2.1).

### Backed mode

`ChromData.read(path, backed=True)` on a `.chromdata.zarr` / `.cdz`
returns a `BackedChromData` (`cd.backed is True`):

- **eager** (read on open): `bins`, `bin_tracks`, `binm`, `cells`, `cellm`,
  `traces`, `intervals`, `points`, `results`, `uns`, `index/`;
- **lazy**: `coords` / `layers[...]` (`BackedArray`: `shape`, row slicing,
  `np.asarray`) and `spots` / `spot_tracks` (`BackedFrame`: `columns`,
  `dtypes`, `frame[col]`, `frame.iloc[rows]`, `to_pandas()`), read from
  Parquet on access;
- `get_cell` / `get_trace` / `get_chrom` / `cd[rows]` read only the row
  ranges they need and return an in-memory `ChromData` (a trace: one slice
  of one partition; a chromosome: one partition; a cell: one slice per
  chromosome);
- `iter_traces(batch, chrom=None)` / `iter_cells(batch)` stream in-memory
  chunks (identical chunks on in-memory objects; `batch="auto"` from
  `uchrom.settings.memory_budget`);
- every one of these, `to_memory()` and `read()` take `columns=` /
  `tracks=`: `columns="coords"` reads coordinates and key columns only,
  `columns=[...]` adds spot columns / spot tracks / layers by name,
  `tracks=[...]` picks spot tracks (default: everything);
- `to_memory()` loads everything; `write()` loads, then writes.

Spot-aligned data are read-only on a backed object; the small tables can
be edited and are saved by `write()`.

## File Format

### Versioning

Every container records the data-model version and the package that
wrote it:

| Attribute | Example | Description |
|-----------|---------|-------------|
| `uchrom_format_version` | `"2.1"` | `MAJOR.MINOR` version of the ChromData format (`.chromdata.zarr`: 2.1; `.h5cd`: 2.0). MAJOR bumps are breaking; MINOR bumps keep old files readable. |
| `uchrom_version` | `"0.2.0"` | Version of the U-Chrom package that wrote the file. For provenance. |

In a `.chromdata.zarr` store they are root-group attributes (plus
`attrs["uchrom"]["format_version"]`); in `.h5cd` root HDF5 attributes.

Read semantics (implemented in `ChromData.read`, for both containers):

- **Same MAJOR**: read successfully. Higher MINOR triggers a warning; unknown fields are ignored.
- **Different MAJOR**: `ValueError` with guidance to upgrade or convert.
- **Missing attribute** (pre-versioning `.h5cd` files): warning, assumed to be the legacy 1.0 layout.

New MAJOR versions should add a `_read_vN` function in `cdata.py` and may include a migration helper that converts old on-disk data to the current in-memory form.

### `.chromdata.zarr` layout (format 2.1, the default)

A Zarr v3 group; everything with rows is Parquet (zstd), everything
n-dimensional is a Zarr array (zstd), metadata is JSON attributes:

```
data.chromdata.zarr/
├── zarr.json               attrs: uchrom_format_version "2.1", uchrom_version,
│                           uchrom = {format "chromdata.zarr", format_version,
│                           layout "partitioned", spot_order "chrom,cell,trace,bin",
│                           n_spots, n_bins, n_traces, n_cells, n_row_groups,
│                           n_partitions, has_source_row, has_cell_id}
├── tables/                 zarr group; attrs["tables"] = per-table metadata,
│   │                       incl. "partitions": [{chrom, code, dir, n_rows, files}]
│   ├── spots/chrom=<name>/part-0.parquet
│   │                       one partition per chromosome (category order);
│   │                       inside, one row per spot sorted by (cell, trace, bin):
│   │                       bin_id int32, trace_id / cell_id integer codes,
│   │                       x, y, z (float64, or float32 with coord_dtype=),
│   │                       extra spot columns; row groups of ~16,384 rows
│   │                       ending on cell boundaries; statistics on
│   ├── spot_tracks/chrom=<name>/part-0.parquet   row-aligned with spots (same row groups)
│   ├── layers/<key>/chrom=<name>/part-0.parquet  row-aligned x, y, z
│   ├── categories/<table>.<column>.parquet   the values of each coded column
│   ├── bins.parquet        chrom (dictionary), start, end, [name, resolution, …]
│   ├── bin_tracks.parquet  n_bins rows
│   ├── cells.parquet, traces.parquet   index kept (pandas metadata)
│   ├── intervals/<key>.parquet         kind + source_result in tables attrs
│   └── points/<key>.parquet
├── index/                  zarr arrays over the stored spot order (global row
│   │                       numbers: partition after partition)
│   ├── trace_offsets       int64 (n_runs + 1): rows of each (chrom, cell, trace) run
│   ├── trace_codes         int32 (n_runs): trace_id code of each run
│   ├── trace_cells         int32 (n_runs): cell_id code (-1: none)
│   ├── chrom_trace         int32 (n_runs): chrom code of the run's partition
│   ├── cell_offsets        int64 (n_cell_runs + 1): rows of each (chrom, cell) run
│   ├── cell_codes          int32 (n_cell_runs), cell_partition int32 (n_cell_runs)
│   ├── row_groups          int64: row offsets of all Parquet row groups
│   ├── partition_offsets   int64 (n_partitions + 1): rows of each partition
│   ├── partition_groups    int64 (n_partitions + 1): first row group of each
│   ├── partition_chrom     int32 (n_partitions): chrom code of each partition
│   └── source_row          int64 (n_spots), when the writer sorted: each spot's
│                           row in the object that was written
├── cellm/<key>, binm/<key> zarr arrays; attrs["keys"] maps key → node name
├── results/<key>           a zarr group or array per result; attrs = provenance
│                           (_kind, _function, _params, _inputs, _uchrom_version,
│                           _created_utc) + _type: dataframe / series (table.parquet
│                           inside), ndarray, dict (children), json, or ref
│                           (_value_ref = "intervals/<key>")
├── uns/                    attrs {values (JSON), nodes, order}; numeric arrays of
│                           > 64 elements as sub-arrays / groups
├── contacts/               attrs: uns["linked_cool"] / uns["linked_scool"] records
└── links/                  attrs: uns["linked_anndata"] / uns["linked_mudata"] records
```

- Partition directories are `chrom=<name>` (hive style: DuckDB / Polars /
  Arrow datasets prune on it); names that are not portable become
  `chrom=_<i>`, the attrs map them back.  A store without spots has one
  empty partition `empty/`.  A trace spanning several chromosomes is split
  into one run per partition.
- **Format 2.0** (still read): one `tables/spots.parquet`,
  `spot_tracks.parquet`, `layers/<key>.parquet`, sorted by (cell, trace,
  bin), row groups of ~65,536 rows; `index/` without the partition arrays,
  one entry per cell in `cell_offsets`, `chrom_trace = -1` for a run over
  several chromosomes.  Readers treat it as a single partition.  2.0
  readers cannot read 2.1 stores (the spot tables moved).
- Categorical spot-aligned columns are stored as integer codes with the
  categories in `tables/categories/`, so every row group decodes without
  string work; categoricals of the small tables use Parquet dictionaries.
- `spots.chrom / start / end` are derived from `bins` and not stored.
- Keys that are not portable file / node names (or that clash
  case-insensitively) get `_<i>` names; the attrs map the real keys.
- Linked-file records keep their paths verbatim; absolute paths that live
  next to the store also get a relative copy (`relpaths`), used when the
  absolute path no longer exists (a moved project folder).
- `x.cdz` is the same tree in one zip archive, uncompressed
  (`ZIP_STORED`) with `zarr.json` first; Parquet members are read in place.
- The writer builds the store in a temporary sibling directory and renames
  it into place, so readers never see a half-written store.

### HDF5 layout (`.h5cd`, format 2.0 — deprecated)

`.h5cd` files (1.x and 2.0) remain readable; writing them still works in
this release but warns.

```
data.h5cd
├── [attrs]
│   ├── uchrom_format_version   "2.0"
│   ├── uchrom_version          "0.2.0"
│   └── spot_order              "unsorted"
├── bins/               chrom {codes, categories}, start int64, end int64, …
├── coords              float64 (n_spots, 3)
├── spots/              bin_id int32, trace_id / cell_id {codes, categories}, extra columns
│                        (@_column_order keeps the in-memory column order)
├── tracks/             bin-level tracks, n_bins rows
├── spot_tracks/        spot-level tracks, n_spots rows
├── binm/               one (n_bins, …) dataset per key
├── intervals/<key>/    DataFrame group, @_kind, @_source_result
├── cells/, traces/     DataFrame groups
├── cellm/, layers/     one dataset per key
├── points/             optional group of DataFrames
├── results/            typed entries + provenance attrs; an interval result holds
│                        @_value_ref = "intervals/<key>" instead of a copy
└── uns/                scalars as attrs, arrays as datasets, dicts as sub-groups
```

Categorical columns are stored as `{codes, categories}` groups.  Datasets
of ≥ 4,096 elements are chunked (65,536 rows per chunk) and compressed —
gzip level 4 by default, `cd.write(path, compression="lzf" | None)` to
change it.  1.x files (spots with `chrom/start/end`, spot-aligned
`tracks/`) are read by `_read_v1` and upgraded in memory.  The HDF5
container has no `index/`, no sorted spots and no backed mode.

## FOF-CT Compatibility

`ChromData.from_fofct()` reads the [4DN FISH Omics Format - Chromatin Tracing](https://fish-omics-format.readthedocs.io/) core table.

Column mapping:

| FOF-CT | ChromData |
|--------|-----------|
| Spot_ID | spots.spot_id |
| Trace_ID | spots.trace_id |
| X, Y, Z | coords[:, 0], coords[:, 1], coords[:, 2] |
| Chrom | spots.chrom |
| Chrom_Start | spots.start |
| Chrom_End | spots.end |
| Cell_ID | spots.cell_id |

Header fields (`##Genome_Assembly`, `##XYZ_Unit`, `#Lab_Name`, etc.) are stored in `uns['fofct_header']`, with `genome_assembly` and `xyz_unit` promoted to top-level `uns` keys.

## Memory Considerations

- `chrom`, `trace_id`, `cell_id` are stored as pandas Categorical dtype, reducing memory ~10x compared to Python strings.
- Pairwise distance matrices are not stored. Use `compute_distances(trace_id=...)` to compute per-trace on demand.
- For datasets exceeding available RAM, write a `.chromdata.zarr` store and open it with `ChromData.read(path, backed=True)`: `get_cell` / `get_trace` / `get_chrom` and `iter_traces` / `iter_cells` read only the rows they need.
- Inputs larger than RAM: `ChromData.from_fofct(path, out=...)`, `read_seqfish_multiomics(..., out=...)` or `ChromData.writer(path)` stream into a store; `uchrom.fea.distance_map` and the ArcFISH callers (`streaming=True`) compute population statistics over `iter_traces` with memory `O(n_bins²)`; `uchrom.settings.memory_budget` bounds the working memory.
