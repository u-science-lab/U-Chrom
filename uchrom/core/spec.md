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
cd.write('data.h5cd')              # Write to HDF5
cd = ChromData.read('data.h5cd')   # Read from HDF5
```

## File Format (.h5cd)

### Versioning

The on-disk format is versioned via two root-group HDF5 attributes:

| Attribute | Example | Description |
|-----------|---------|-------------|
| `uchrom_format_version` | `"1.0"` | `MAJOR.MINOR` version of the `.h5cd` format. MAJOR bumps are breaking; MINOR bumps are backwards-compatible (additive). |
| `uchrom_version` | `"0.2.0"` | Version of the U-Chrom package that wrote the file. For provenance. |

Read semantics (implemented in `ChromData.read`):

- **Same MAJOR**: read successfully. Higher MINOR triggers a warning; unknown fields are ignored.
- **Different MAJOR**: `ValueError` with guidance to upgrade or convert.
- **Missing attribute** (pre-versioning files): warning, assumed to be the legacy 1.0 layout.

New MAJOR versions should add a `_read_vN` function in `cdata.py` and may include a migration helper that converts old on-disk data to the current in-memory form.

### HDF5 layout (format 2.0)

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
change it.  1.x
files (spots with `chrom/start/end`, spot-aligned `tracks/`) are read by
`_read_v1` and upgraded in memory; `uchrom.io.upgrade_h5cd(src, dst)` /
`python -m uchrom.io.upgrade` rewrites them.  Not in 2.0 yet: sorted
spots + `index/` offsets and backed mode (2.1), `contacts/` / `links/`
(linked files stay in `uns["linked_*"]`), `binsets/`.

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
- For datasets exceeding available RAM, consider processing per-cell or per-chromosome via subsetting.
