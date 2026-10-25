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

`cells` can hold any per-cell column (`cell_type`, volume, RNA counts, …).

`cellm` stores arrays aligned to the cells axis, e.g.:
- `cellm['embedding']` — shape (n_cells, 128), single-cell structure embeddings.
- `cellm['umap']` — shape (n_cells, 2), UMAP coordinates.

### Cell spatial position (format 2.3)

Where each cell sits in the tissue / field of view.  This is cell-level
data, kept apart from the chromatin `coords` (one row per spot).

**Centroids** are columns of `cells`, described by a record in
`uns['cell_spatial'][key]`:

| Column (key `"default"`) | Column (other key `k`) | Type | Required |
|---|---|---|---|
| `centroid_x`, `centroid_y` | `k_centroid_x`, `k_centroid_y` | float | yes |
| `centroid_z` | `k_centroid_z` | float | no (2-D positions) |

Record fields (`uns['cell_spatial'][key]`):

| Field | Description |
|---|---|
| `x_col`, `y_col`, `z_col` | the `cells` columns (the canonical names above unless registered otherwise, e.g. a loader's `cell_center_x_global`) |
| `ndim` | 2 or 3 |
| `unit` | length unit of the stored values (`"um"`, `"micron"`, `"nm"`, `"voxel"`, …) |
| `voxel_size`, `voxel_unit` | per-axis voxel size when `unit` is `"voxel"`; `cell_positions(physical=True)` multiplies by it |
| `frame` | coordinate system: `"fov"` (local to one field of view), `"tissue"` / `"global"` (one stitched frame per section / sample), or another name |
| `region_col` | `cells` column naming the FOV / region a local frame belongs to |
| `in_coords_frame` | `true` when the positions (in physical units) share the frame of `coords` |
| `status` | `"measured"` (imaged / segmented) or `"inferred"` (mapped, e.g. Tangram) |
| `source`, `method` | where the positions come from and how; `source` is required when `status` is `"inferred"` |
| `shapes` | key of `cell_shapes` holding the outlines of these cells |

`cd.set_cell_positions(positions, key=, cell_ids=, unit=, frame=, status=, source=, …)`
writes the columns and the record (rows aligned by `cell_ids`, NaN for
cells not given; `positions=None, columns=[…]` registers existing
columns); `cd.cell_positions(key)` returns `x, y[, z]` (+ `region`) indexed
by `cell_id`, the record in `.attrs['cell_spatial']`.  Without a record,
`cell_positions()` recognises `centroid_x/y/z` and the pre-2.3 names
`x_centroid/y_centroid/z_centroid` (seqFISH+ loader) and
`spatial_x/spatial_y` (the deprecated `set_cell_spatial_coordinates`); 1.x
records (`coordinate_system`, `inferred`) are read as `frame`, `status`.

**Outlines** (optional) are `cell_shapes[key]` (e.g. `"cell"`,
`"nucleus"`): a DataFrame with `cell_id` (str) and `geometry` (WKB bytes,
Polygon / Polygon Z), one row per cell, extra columns allowed; subsetting
keeps the outlines of the retained cells.  Stored as GeoParquet
(`tables/cell_shapes/<key>.parquet`, `geo` metadata: encoding WKB, CRS
null), the representation SpatialData uses for shapes, so
`geopandas.read_parquet` reads it.  `uns['cell_shapes'][key]` records
`geometry_types`, `n`, `unit`, `frame`, `in_coords_frame`, `status`,
`source`.  `cd.set_cell_shapes(...)` takes vertex arrays or WKB (no
geometry library needed), shapely geometries or a GeoDataFrame;
`cd.cell_shapes_geodataframe(key)` needs shapely + geopandas (optional
dependencies, `pip install u-chrom[spatial]`; a clear `ImportError`
otherwise).

**Linked SpatialData** (`uns['linked_spatialdata'][key]`, stored with the
other link records under `links/`): `path` (relative paths resolve next to
the store), `format: "spatialdata"`, `table`, `region`, `region_key`,
`instance_key` (the cell map: rows of `table` with `region_key == region`
are cells whose `instance_key` value is the ChromData `cell_id`, or the
value of the `cells` column `cell_col`), `coordinate_system`,
`spatialdata_version`.  `cd.link_spatialdata(path, ...)` fills the table
attributes from the store; `cd.validate_links()` checks the path, the
table, the instance key and how many ChromData cells the map finds;
`cd.load_linked_spatialdata(cells=[...])` returns the SpatialData object
(subset to those cells); `cd.to_spatialdata()` exports spots, centroids,
outlines, the cell table and `points`.

**Loaders**: `read_seqfish_multiomics(cell_clustering=…)` writes
`centroid_x/y/z` (voxels, frame `"fov"`, `region_col="fov"`, voxel size
0.103 / 0.103 / 0.25 µm); `from_fofct(cell_table=…)` registers
`Cent_ROI_x/y[/z]` (→ `centroid_*`) or `cell_center_x_global / _y_global`
(frame `"global"`), and `from_fofct(mapping_table=…)` reads the Cell/ROI
Mapping table's `ROI_Boundaries` (OME polygons) into `cell_shapes['cell']`;
`to_fofct(mapping_table=…)` writes it back.

### Clusters: multi-way contacts (format 2.4)

A *cluster* is a set of genomic fragments observed together: a SPRITE
barcode cluster, a Pore-C read, a ChIA-Drop GEM, a GAM nuclear profile —
a hyperedge whose nodes are fragments.  A pairwise contact map loses which
contacts happened together; a cluster keeps it.  `clusters[key]` is a
`ClusterTable` (`chromdata.clusters`) in compressed sparse rows:

| Part | Shape | Description |
|---|---|---|
| `members` | (3, n_members) unsigned | chrom code (into `chroms`), `start`, `end` of every fragment (0-based, end-exclusive, `end > start`); the fragments of a cluster are contiguous |
| `member_offsets` | (n_clusters + 1) int64 | cluster `k` = `members[:, member_offsets[k]:member_offsets[k + 1]]` |
| `cells`, `cell_offsets` | (n_cells), (n_cells + 1) | per-cell tables only: cell `i` owns clusters `cell_offsets[i]:cell_offsets[i + 1]`; bulk tables have neither |
| `chroms` | list of str | chromosome names |
| `member_columns` | dict[str, (n_members)] | optional numeric per-fragment values (strand, mapping quality, DNA / RNA read) |
| `cluster_columns` | DataFrame (n_clusters) | optional per-cluster values; `from_frame` keeps the input labels (barcodes, read ids) as `name` |
| `attrs` | dict | JSON metadata (assay, source, filters) |

- **Order.**  Clusters are sorted by (cell, first fragment: chrom, start,
  end, then size), the fragments of a cluster by (chrom, start, end); a
  cluster id is its position in that order.  A cell's clusters are one
  contiguous range — for spatial assays a "cell" is a spot (barcode pixel),
  its position in `cells` (`cell_spatial`).  Cell ids are strings; they name
  rows of `cells` when the object has them, but the table carries its own
  list.
- **Locus index.**  For region queries every chromosome also has its
  fragments sorted by start, one row each, with the context of their
  cluster: `start`, `end`, `cluster`, `size` (fragments of the cluster on
  all chromosomes), `chrom_size` (its fragments on this chromosome),
  `span_start` / `span_end` (its first and last fragment on this
  chromosome) and `cell`.  `region(chrom, start, end)` returns the
  fragments overlapping the window with these columns: everything a cluster
  track draws (group by `cluster`; a line from `span_start` to `span_end`,
  a box per fragment; `size > chrom_size` marks clusters that reach other
  chromosomes).  In memory the index is built on first use; on disk it is
  stored (below).
- **Pairwise views are derived**, not stored: the weight of a pair (1,
  SPRITE's 2/n, …) is a choice of the analysis.
- Subsetting spots keeps the clusters whole (like `bins`);
  `table.select_cells(ids)` makes a table of some cells.

```python
cd.set_clusters("sprite", df, cluster="barcode", cell="spot")   # one row per fragment
t = cd.clusters["sprite"]                       # ClusterTable
t.region("chr2", 5_423_000, 5_460_000, min_size=2, max_size=50)  # fragments in a window + context
t.get_cell("spot_17"); t.members([3, 8]); t.to_frame()
ClusterTable.from_frame(df, cell=None)          # bulk data
chromdata.clusters.add_clusters("x.chromdata.zarr", "sprite", t)  # into an existing store
```

### Tracks

`bin_tracks` (per locus) and `spot_tracks` (per spot) replace the 1.x
spot-aligned `tracks`.  During 2.x, `cd.tracks` is a deprecated
spot-aligned view of both (`cd.tracks_spot_view()` without the warning).

### Additional Storage

| Attribute | Type | Description |
|-----------|------|-------------|
| `traces` | DataFrame (n_traces) | Trace-level metadata. Index = trace_id. |
| `layers` | dict[str, ndarray] | Alternative coordinate representations, each (n_spots, 3). e.g. `layers['raw']` for uncorrected coordinates. |
| `cell_shapes` | dict[str, DataFrame] | Cell outlines: `cell_id` + `geometry` (WKB), one row per cell; see *Cell spatial position*. Format ≥ 2.3 (zarr). |
| `clusters` | dict[str, ClusterTable] | Multi-way contacts: clusters of genomic fragments; see *Clusters*. Format ≥ 2.4 (zarr). |
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
cd.write('data.chromdata.zarr')                    # format 2.4: Zarr v3 + Parquet (a directory)
cd.write('data.cdz')                               # the same store in one zip file
cd = ChromData.read('data.chromdata.zarr')         # in memory (spots in stored order)
cd = ChromData.read('data.chromdata.zarr', original_order=True)   # rows as written
cd = ChromData.read('data.chromdata.zarr', backed=True)           # out of core
cd = ChromData.read('data.chromdata.zarr', columns='coords')      # xyz + key columns only
with ChromData.writer('big.chromdata.zarr') as w:  # streaming writer (chunks larger than RAM)
    w.append(chunk)
```

The format follows the path: `*.zarr` → Zarr directory, `*.cdz` → zip.  An
existing path without one of these suffixes is sniffed.  The HDF5 `.h5cd`
container (format 1.x / 2.0) is no longer read or written — `read` / `write`
raise a `ValueError`; `python -m uchrom.io.upgrade old.h5cd` converts a file
once to `old.chromdata.zarr` (and rewrites a 2.0–2.3
`.chromdata.zarr` as 2.4).

### Backed mode

`ChromData.read(path, backed=True)` on a `.chromdata.zarr` / `.cdz`
returns a `BackedChromData` (`cd.backed is True`):

- **eager** (read on open): `bins`, `bin_tracks`, `binm`, `cells`, `cellm`,
  `traces`, `intervals`, `points`, `results`, `uns`, `index/`, and of each
  cluster table its attributes, `cells` and `cell_offsets`;
- **lazy**: `coords` / `layers[...]` (`BackedArray`: `shape`, row slicing,
  `np.asarray`) and `spots` / `spot_tracks` (`BackedFrame`: `columns`,
  `dtypes`, `frame[col]`, `frame.iloc[rows]`, `to_pandas()`), read from
  Parquet on access;
- `get_cell` / `get_trace` / `get_chrom` / `cd[rows]` read only the row
  ranges they need and return an in-memory `ChromData` (format 2.2: a
  trace or a cell is one primary slice plus its coordinate runs; a
  chromosome's coordinates are one partition);
- `iter_traces(batch, chrom=None)` / `iter_cells(batch)` stream in-memory
  chunks (identical chunks on in-memory objects; `batch="auto"` from
  `uchrom.settings.memory_budget`);
- cluster tables stay on disk: `region`, `get_cell` and `members` read
  only their ranges (`to_memory()` / an in-memory read loads them);
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
| `uchrom_format_version` | `"2.4"` | `MAJOR.MINOR` version of the ChromData format (`.chromdata.zarr`: 2.4). MAJOR bumps are breaking; MINOR bumps keep old files readable. |
| `uchrom_version` | `"0.2.0"` | Version of the U-Chrom package that wrote the file. For provenance. |

In a `.chromdata.zarr` store they are root-group attributes (plus
`attrs["uchrom"]["format_version"]`).

Read semantics (implemented in `ChromData.read`):

- **Same MAJOR**: read successfully. Higher MINOR triggers a warning; unknown fields are ignored.
- **Different MAJOR**: `ValueError` with guidance to upgrade or convert.

A new MINOR layout is read next to the old ones (as 2.2 reads 2.1 and 2.0); a new MAJOR comes with a converter (as `uchrom.io.upgrade` converts the old `.h5cd`).

### `.chromdata.zarr` layout (format 2.4, the default)

Format 2.4 is format 2.3 plus the optional multi-way contacts
(`clusters/<key>/`, see *Clusters on disk*) — additive: a 2.3 reader reads
a 2.4 store with the higher-MINOR warning and ignores the clusters
(rewriting it with that reader drops them); a 2.4 store without clusters
differs from 2.3 only by its version.  2.4 readers read 2.0–2.3 stores
unchanged.  (`zarrcd.write_zarr(..., _layout="2.2")`, the current layout,
is written as 2.4.)

Format 2.3 is the 2.2 layout below plus the optional cell outlines
(`tables/cell_shapes/<key>.parquet`, GeoParquet) and the cell-position
records (`uns['cell_spatial']`, `uns['cell_shapes']`, `links/` records
`linked_spatialdata`) — all additive.  A 2.2 reader reads a 2.3 store with
the usual higher-MINOR warning and ignores the outlines (rewriting it with
that reader drops them); 2.3 readers read 2.0–2.2 stores unchanged.

A Zarr v3 group; everything with rows is Parquet (zstd), everything
n-dimensional is a Zarr array (zstd), metadata is JSON attributes.  Every
spot-aligned value is stored **once**: the coordinates and the key columns
in a table partitioned by chromosome, every other spot-aligned column in
cell-sorted *primary* tables, and spot columns that are a function of the
bin, the cell or the trace once per key.

```
data.chromdata.zarr/
├── zarr.json               attrs: uchrom_format_version "2.4", uchrom_version,
│                           uchrom = {format "chromdata.zarr", format_version,
│                           layout "primary+coords", spot_order "cell,trace,chrom,bin",
│                           coords_order "chrom,cell,trace,bin", n_spots, n_bins,
│                           n_traces, n_cells, n_row_groups, n_partitions,
│                           row_group_rows, coords_row_group_rows,
│                           has_source_row, has_cell_id}
├── tables/                 zarr group; attrs["tables"] = per-table metadata
│   ├── coords/chrom=<name>/part-0.parquet
│   │                       coordinates + keys, one partition per chromosome
│   │                       (category order), sorted by (cell, trace, bin):
│   │                       bin_id int32, trace_id / cell_id integer codes,
│   │                       x, y, z (float64, or float32 with coord_dtype=);
│   │                       row groups of ~16,384 rows ending on cell boundaries
│   ├── primary/            cell-sorted tables, one row per spot in the primary
│   │   │                   order (cell, trace, chromosome, bin); no key columns
│   │   │                   (the rows map to the coordinate table run by run)
│   │   ├── spots.parquet          the other spot columns (when there are any)
│   │   ├── spot_tracks.parquet    per-spot signals
│   │   └── layers/<key>.parquet   alternative x, y, z
│   │                       row groups of ~65,536 rows ending on cell
│   │                       boundaries, shared by every primary table; float
│   │                       columns dictionary-encoded (Parquet falls back to
│   │                       plain pages per column chunk when that does not pay)
│   ├── derived/<key>.parquet   spot columns that are a function of bin_id /
│   │                       cell_id / trace_id: one row per key code (bins:
│   │                       n_bins rows); a column already in bins with the same
│   │                       values is referenced, not stored
│   ├── categories/<table>.<column>.parquet   the values of each coded column
│   ├── bins.parquet        chrom (dictionary), start, end, [name, resolution, …]
│   ├── bin_tracks.parquet  n_bins rows
│   ├── cells.parquet, traces.parquet   index kept (pandas metadata)
│   ├── intervals/<key>.parquet         kind + source_result in tables attrs
│   ├── points/<key>.parquet
│   └── cell_shapes/<key>.parquet       cell outlines (2.3): cell_id, geometry (WKB),
│                           GeoParquet "geo" metadata; tables attrs cell_shapes =
│                           {key: {file, n_rows, encoding, geometry_types}}
├── index/                  zarr arrays over the primary order
│   ├── trace_offsets       int64 (n_runs + 1): rows of each (cell, trace, chromosome) run
│   ├── trace_codes         int32 (n_runs): trace_id code of each run
│   ├── trace_cells         int32 (n_runs): cell_id code (-1: none)
│   ├── chrom_trace         int32 (n_runs): chrom code of the run
│   ├── cell_offsets        int64 (n_cells + 1), cell_codes int32 (n_cells)
│   ├── row_groups          int64: row offsets of the primary row groups
│   ├── coords/             the same arrays over the coordinate table (runs are
│   │                       (chromosome, cell, trace); cell_offsets per
│   │                       (chromosome, cell)) + cell_partition,
│   │                       partition_offsets, partition_groups, partition_chrom
│   │                       and primary_run (int64 per coordinate run: its
│   │                       primary run — the runs match one to one)
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
├── clusters/<key>/         multi-way contacts (2.4), see *Clusters on disk*
├── contacts/               attrs: uns["linked_cool"] / uns["linked_scool"] records
└── links/                  attrs: uns["linked_anndata"] / uns["linked_mudata"] /
                            uns["linked_spatialdata"] records
```

- **Two orders, one mapping.**  In memory (a full read) spots are in the
  primary order.  Every (cell, trace, chromosome) triple is one contiguous
  run in the primary tables and one run in its chromosome partition, with
  the rows in the same (bin) order, so `index/coords/primary_run` maps rows
  of either side to the other run by run.  A full read scatters the
  coordinate partitions into primary order; `get_cell` / `get_trace` read
  one primary slice and the matching coordinate runs (a cell: one slice per
  chromosome); `get_chrom(columns="coords")` reads one partition;
  `get_chrom` with other columns adds the chromosome's primary rows (a
  slice of every primary row group, decoded in parallel).  `iter_traces` /
  `iter_cells` stream in the coordinate order (chromosome › cell › trace),
  as in memory.
- **Derived spot columns.**  The writer stores a spot column once per key
  when every spot of a key holds the same value (bitwise for numbers, equal
  `str` for object columns, the same code for categoricals; keys tried in
  the order bin, cell, trace) — e.g. per-spot probe names that repeat the
  bin, or a sample id.  Readers rebuild the column with one gather; the
  round trip is exact (dtype and values).  `write(..., normalize_spot_columns=False)`
  stores them per spot.
- **Floats.**  Parquet dictionary pages for the float columns of the primary
  tables (`float_dictionary=True`); the lossless decimal encoding of
  `chromdata.floatcodec` is available with `float_encoding=True` (or a
  set of tables, e.g. `{"coords"}`): bitwise identical, smaller, slower to
  read.
- Partition directories are `chrom=<name>` (hive style: DuckDB / Polars /
  Arrow datasets prune on it); names that are not portable become
  `chrom=_<i>`, the attrs map them back.  A store without spots has one
  empty partition `empty/`.
- **Format 2.1** (still read): every spot-aligned table partitioned by
  chromosome — `tables/spots/chrom=<name>/part-0.parquet` (keys, x, y, z,
  extra spot columns), `spot_tracks/…`, `layers/<key>/…`, sorted by (cell,
  trace, bin) inside a partition; `index/` over that order with the
  partition arrays.  **Format 2.0** (still read): one `tables/spots.parquet`,
  `spot_tracks.parquet`, `layers/<key>.parquet`, sorted by (cell, trace,
  bin); read as a single partition.  Older readers cannot read newer
  stores; `python -m uchrom.io.upgrade old.chromdata.zarr new.chromdata.zarr`
  rewrites them.
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

### Clusters on disk (format 2.4)

```
clusters/                     attrs: keys = {key: node}
└── <node>/                   attrs: uchrom_clusters = {key, kind: per_cell|bulk, chroms,
    │                           n_cells, n_clusters, n_members, member_rows, locus_rows,
    │                           chunk, locus_chunk, locus: {chrom: {node, n, max_length}},
    │                           member_columns: {name: node}, cluster_columns, attrs}
    ├── members               (3, n_members) uint32 (uint64 when needed): chrom code,
    │                           start, end; clusters in the stored order
    ├── member_offsets        int64 (n_clusters + 1)
    ├── cells                 per_cell: string array, the order of cell_offsets
    ├── cell_offsets          per_cell: int64 (n_cells + 1)
    ├── member_columns/<name> (n_members) numeric
    ├── clusters.parquet      the per-cluster table (optional)
    └── by_locus/<chrom>/     the locus index of one chromosome (chromosomes with fragments)
        ├── rows              (8, n) unsigned — start, end, cluster, size, chrom_size,
        │                       span_start, span_end, cell (bulk: 7 rows, no cell);
        │                       sorted by (start, end, cluster)
        └── fence             int64: rows[0, ::locus_chunk], the first start of every chunk
```

- `members`, `member_offsets`, `member_columns` and the locus `rows` are
  chunked by 16,384 columns (`chunk` in the attrs; a `(rows, 16384)` chunk
  holds every row of its columns, each row contiguous) and **sharded** by
  4,194,304 columns, zstd 9 — the layout of the embedded contact pixels.
  The locus `rows` take their own chunk size (`locus_chunk`, default 16,384)
  and codec (`add_clusters(locus_chunk=, locus_compressor=)`); readers use
  the `locus_chunk` of the attrs (`chunk` when absent) and the codec the
  array records.  On the full Quinodoz 2018 SPRITE table (406 M fragments)
  16,384 columns with zstd 9 read 40 kb / 1 Mb windows over HTTP fastest;
  smaller chunks read fewer bytes in more requests, Blosc bitshuffle saved
  < 1 % (uchrom-reproducibility `extended_data_fig1/g_clusters_layout.py`).
  `fence`, `cells` and `cell_offsets` are one chunk each.  All values of a
  `rows` array share one unsigned dtype (uint32 unless a value needs
  uint64).
- **A window** `[s, e)` of a chromosome: with `L` = its `max_length` (the
  longest fragment), the fragments that can overlap the window start in
  `(s − L, e)`.  The fence (read once per chromosome) gives the chunks:
  from the last whose first start is `≤ s − L` to the last whose first start
  is `< e`; one range read of `rows`, then keep `s − L < start < e` and
  `end > s`.  The rows carry the cluster context, so drawing the window
  reads nothing else.
- **A cell**: `cell_offsets` → a slice of `member_offsets` → one slice of
  `members`.  **A cluster**: two offsets, one slice.
- Every fragment is stored twice (cluster order and position order), as
  BAM files are shipped sorted by name and by coordinate.
- `chromdata.clusters.add_clusters(store, key, table[, overwrite=True])`
  adds a table to an existing directory store without rewriting it (marks
  the store 2.4 and re-consolidates its metadata); the streaming writer
  takes `finish(clusters={key: table})`, and chunks of one object
  (`iter_cells`) carry its tables.

### Embedded contacts and AnnData (additive part of 2.3)

Linked `.cool` / `.mcool` / `.scool` / `.h5ad` files stay outside the store.  For an atlas, or any
store that must live alone on object storage, they can be *embedded* with
`python -m chromdata.embedded STORE` (`chromdata.embedded.embed_links`).  The link records stay in place;
a reader that finds an embedded copy uses it, otherwise it follows the link.  Stores without these
groups, and readers that do not know them, are unaffected (so this is not a format version bump).
`cd.write("x.cdz")` does not carry the groups, but a `.cdz` zipped from an embedded store
(`python -m chromdata.catalog pack`, the atlas downloads) keeps them and reads like the directory.  `cd.write(path)` onto the store the object was read from keeps
`embedded/` (the copies belong to the same data); writing any other object over a store, or to a new path,
does not carry them: embed after writing (re-embed with `--overwrite` if a linked file changed).

```
embedded/contacts/<name>/         attrs.uchrom_contacts = {key, kind: per_cell|bulk, label, source,
│                                   resolutions, chroms, chrom_first_bin{res: [first bin of each chrom]},
│                                   n_cells, n_pixels, count_max | has_weights, trans_min_resolution}
├── cells                         per_cell: string array (cell names, the order of cell_offset)
└── r<resolution>/                one per resolution (per_cell: one)
    ├── bins/{chrom,start,end[,weight]}     chrom = code into attrs.chroms; weight = cooler balancing
    ├── cis/<chrom>/pix           (3, n) unsigned ints, rows bin1, bin2 (chromosome-local), count; upper triangle
    ├── cis/<chrom>/cell_offset   per_cell: (n_cells + 1) pixel offsets; pixels sorted by (cell, bin1, bin2)
    ├── cis/<chrom>/bin1_offset   bulk: (n_bins_of_chrom + 1) offsets; pixels sorted by (bin1, bin2)
    └── trans/{pix, cell_offset | bin1_offset}    genome-wide bin ids; bulk: only for resolutions >= 250 kb
embedded/anndata/<name>/          an AnnData Zarr group (anndata >= 0.13 layout) +
                                  attrs.uchrom_anndata = {key, family: linked_anndata|linked_bin_matrices, ...}
embedded/images/<name>/data       the bytes of a linked section image (uint8 array), attrs.uchrom_image = {key, media_type, bytes}
```

- `pix` is chunked `(3, 16384)` and **sharded** (`(3, 4194304)` per shard, Zarr v3 sharding codec, zstd 9;
  a chunk holds each of the three rows contiguously, which compresses ~40 % better than interleaved columns), so
  one object on S3 holds many small chunks and a read fetches the shard index plus the chunks it
  needs; the group's metadata is consolidated (one request opens it).
- The partition is by chromosome, like the coordinates: one cell's cis contacts of a chromosome are
  one contiguous slice, the pseudo-bulk of a group is a few slices, a bulk region is a slice of the
  `bin1_offset` index.  Cells are sorted within a partition, so neighbouring cells of a group read as
  one range.
- Counts and bin ids are `uint16` (`uint32` when needed); a dense AnnData `X` (e.g. ssAB) is chunked
  `(1024, 256)`.  Bins must be uniform and start at 0 on every chromosome (checked when embedding).
- Round trip: the embedded pixels are exactly those of the cooler file (tested), and the web browser
  returns byte-identical matrices from either source.
- Back to cooler: `export_cool` / `export_mcool` / `export_scool` (`chromdata.embedded`) rebuild cooler
  files from the embedded pixels (a bulk map embedded without trans at a fine resolution exports cis only);
  `cd.linked_cool_path(key[, resolution=])` (only that level when given) and `cd.load_linked_scool(key=, cell=)`
  use them when the linked file is gone,
  and `cd.validate_links()` does not flag a missing file whose map is embedded.
- Remote reading: `embedded/contacts` and `embedded/anndata` carry consolidated metadata (the listing of
  their children without listing the bucket), so a store served by plain HTTP or S3 needs no directory
  listing.  See `chromdata/remote.py`.

### Legacy HDF5 container (`.h5cd`)

ChromData format 1.x and 2.0 were HDF5 files (`.h5cd`).  They are no longer
read or written by `ChromData`; `python -m uchrom.io.upgrade old.h5cd`
(`uchrom.io.upgrade_h5cd`) converts one to a `.chromdata.zarr`.  The reader
and the layout description live in `uchrom/io/_h5cd_legacy.py`.

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
