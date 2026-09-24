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

### Core Table (FOF-CT compatible)

| Attribute | Type | Shape | Description |
|-----------|------|-------|-------------|
| `coords` | ndarray | (n_spots, 3) | 3D coordinates. Column order: x, y, z. |
| `spots` | DataFrame | (n_spots, ≥4) | Spot metadata. See columns below. |

**`spots` columns:**

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `chrom` | str (categorical) | yes | Chromosome name (e.g. `chr1`). |
| `start` | int | yes | Start position on chromosome (0-based). |
| `end` | int | yes | End position (non-inclusive). |
| `trace_id` | int or str (categorical) | yes | Which Trace this Spot belongs to. |
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

### Chromatin Table (epigenomic tracks)

| Attribute | Type | Shape | Description |
|-----------|------|-------|-------------|
| `tracks` | DataFrame | (n_spots, n_tracks) | Epigenomic signal per bin, row-aligned to `spots`. |

Each column is a named track, e.g. `ATAC`, `H3K27ac`, `H3K27me3`. Data sourced from bed/bedgraph files, mapped to bins via genomic coordinates.

### Additional Storage

| Attribute | Type | Description |
|-----------|------|-------------|
| `traces` | DataFrame (n_traces) | Trace-level metadata. Index = trace_id. |
| `layers` | dict[str, ndarray] | Alternative coordinate representations, each (n_spots, 3). e.g. `layers['raw']` for uncorrected coordinates. |
| `results` | dict | Analysis results. Values may be DataFrames, Series, ndarrays, nested dicts of these, or JSON-compatible scalars / lists. Anything else raises `TypeError` on `write()`. |
| `uns` | dict | Unstructured metadata (genome assembly, coordinate unit, etc.). |

### Results Convention

| Key | Type | Description |
|-----|------|-------------|
| `'tads'` | DataFrame | Columns: chrom, start, end. |
| `'loops'` | DataFrame | Columns: chrom1, start1, end1, chrom2, start2, end2, score. |
| `'compartments'` | ndarray (n_spots,) | Per-bin A/B label or PC1 value. |

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

### HDF5 layout

```
data.h5cd
├── [attrs]
│   ├── uchrom_format_version   "1.0"
│   └── uchrom_version          "0.2.0"
├── coords              float64 (n_spots, 3)
├── spots/              group — one dataset per column
│   ├── chrom           bytes
│   ├── start           int64
│   ├── end             int64
│   ├── trace_id        bytes or int64
│   └── cell_id         bytes or int64 (optional)
├── cells/              group — one dataset per column
├── cellm/              group — one dataset per key
├── tracks/             group — one dataset per column
├── traces/             group — one dataset per column
├── layers/             group — one float64 (n_spots, 3) per key
├── results/            group — typed entries (`_type` attr): DataFrame / Series / dict as sub-groups, arrays as datasets, scalars & lists as JSON (format ≥ 1.2)
└── uns/                group — scalars as attrs, arrays as datasets, dicts as sub-groups
```

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
