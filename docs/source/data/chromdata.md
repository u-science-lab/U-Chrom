# ChromData

`uchrom.ChromData` is the central container.  It is conceptually similar
to [AnnData](https://anndata.readthedocs.io/) but organises the data
around the chromatin-tracing hierarchy *Cell → Trace → Spot*, plus a
locus axis, `bins`, shared by all cells (format 2.0; the `.chromdata.zarr` container is at 2.3).

```text
spots   tell what was observed      (one row per observation)
bins    tell where on the genome    (one row per locus, shared by all cells)
cells   tell who                    (one row per cell)
results tell what was derived       (typed, with provenance)
```

## Construction

```python
import numpy as np
import pandas as pd
from uchrom import ChromData

coords = np.asarray([[1.0, 2.0, 3.0], [1.5, 2.3, 2.9]])
spots = pd.DataFrame({
    "chrom":    ["chr1", "chr1"],
    "start":    [0, 100_000],
    "end":      [100_000, 200_000],
    "trace_id": [0, 0],
})
cd = ChromData(coords, spots, uns={"genome_assembly": "GRCh38"})
```

The constructor derives the locus axis from the spot loci:

```python
cd.bins          # index = bin_id: chrom (category), start, end
cd.spots         # chrom, start, end, trace_id, bin_id
cd.n_bins        # 2
```

### Spot columns

| Column | Type | Required | FOF-CT field |
|--------|------|----------|--------------|
| `bin_id` | int → `bins.index` | yes (derived from `chrom/start/end` if absent) | — |
| `trace_id` | int/str (category) | yes | `Trace_ID` |
| `chrom` / `start` / `end` | derived from `bins` | give them instead of `bin_id` | `Chrom` / `Chrom_Start` / `Chrom_End` |
| `cell_id` | int/str (category) | no | `Cell_ID` |
| `spot_id` | int/str | no | `Spot_ID` |

`spots["chrom" / "start" / "end"]` are *derived* columns: they are
filled from `bins[spots.bin_id]`, kept in memory for convenience and not
stored on disk.  `cd.spots_with_loci()` is the stable way to get them;
`cd.to_dataframe()` includes them (and leaves `bin_id` out unless
`include_bin_id=True`).  If you edit spot loci in place, call
`cd.rebuild_bins()`; `write()` refuses spots whose loci disagree with
`bins`.

To use an explicit bin table (a probe panel with names, or a regular
grid that includes unobserved loci), pass `bins=` together with either
`bin_id` or loci in `spots`:

```python
bins = pd.DataFrame({"chrom": ["chr1"] * 3, "start": [0, 100_000, 200_000],
                     "end": [100_000, 200_000, 300_000], "name": ["p1", "p2", "p3"]})
cd = ChromData(coords, spots, bins=bins)       # spots loci are looked up in bins
```

String columns are auto-converted to `pd.Categorical` for ~10× memory
savings on large datasets.

## Attributes

| Attribute | Shape | Purpose |
|-----------|-------|---------|
| `bins` | `(n_bins, ≥3)` | locus axis: `chrom, start, end` (+ `name`, `resolution`, …), index `bin_id` |
| `bin_tracks` | `(n_bins, ?)` | per-locus signals: bulk ATAC / ChIP, GC, annotation features, compartment score |
| `binm` | dict | per-locus multi-dim arrays, first axis `n_bins` |
| `intervals` | dict of `IntervalTable` | typed TADs / loops / peaks / segments (see [Intervals](#intervals)) |
| `coords` | `(n_spots, 3)` | x, y, z for each spot |
| `spots` | `(n_spots, ≥2)` | per-spot metadata (`bin_id`, `trace_id`, …) |
| `spot_tracks` | `(n_spots, ?)` | per-spot signals: IF intensity, seqFISH z-scores |
| `tracks` | `(n_spots, ?)` | **deprecated** spot-aligned view of `bin_tracks` + `spot_tracks` |
| `cells` | `(n_cells, ?)` | per-cell metadata |
| `cellm` | dict | multi-dim cell annotations (embeddings, UMAP) |
| `traces` | `(n_traces, ?)` | per-trace metadata |
| `layers` | dict | alternative coordinate sets |
| `points` | dict of DataFrames | non-genomic 3-D points in the same frame (nascent RNA spots, IF puncta): `x, y, z`, `cell_id`, `gene`, … |
| `cell_shapes` | dict of DataFrames | cell outlines: `cell_id`, `geometry` (WKB polygons) — see [Cell spatial position](#cell-spatial-position) |
| `results` | `ResultsStore` | analysis outputs with provenance (loops, TADs, …) — see [Results](#results) |
| `uns` | dict | unstructured metadata |

Properties: `cd.n_spots`, `cd.n_bins`, `cd.n_traces`, `cd.n_cells`, `cd.chroms`.

## Tracks: per locus vs per spot

| data | lives in | aligned to |
|------|----------|-----------|
| bulk ATAC / ChIP / GC / annotation features | `cd.bin_tracks` | bins |
| per-spot IF intensity, seqFISH z-scores | `cd.spot_tracks` | spots |
| per-bin embeddings / loadings | `cd.binm[key]` | bins (first axis) |
| TADs, loops, peaks, compartment segments | `cd.intervals[key]` | typed interval tables |
| per-bin compartment score | `cd.bin_tracks["compartments.axes_pc.pc2"]` | bins |

```python
cd.bin_tracks["ATAC"] = atac_per_bin            # n_bins values
cd.spot_tracks = if_table                       # n_spots rows
cd.tracks_spot_view()                           # every track aligned to spots
cd.tracks_spot_view(["ATAC"])                   # (bin tracks broadcast via bin_id)
cd.track_names()                                # {"bin": [...], "spot": [...]}
```

`fea.add_sequence_features / add_annotation_features / add_peak_features`
and `strc.add_structural_features` write `cd.bin_tracks` (once per locus,
not once per spot); `fea.project_interval_features_to_bins` is the
underlying projection.

`cd.tracks` keeps working during the 2.x series as a spot-aligned view
with a `DeprecationWarning`.  `cd.tracks["x"] = values` writes through
(to `spot_tracks`, or `bin_tracks` for an existing bin track that stays
constant within every bin); assigning a whole spot-aligned table splits
it: columns constant within every bin become bin tracks, the rest spot
tracks.  (In 3.0 `cd.tracks` becomes the bin-level table.)

## Intervals

`cd.intervals` holds typed, validated interval tables (`IntervalTable`,
a DataFrame with `attrs["kind"]` and `attrs["source_result"]`):

| kind | required columns | examples |
|------|------------------|----------|
| `domain` | `chrom, start, end` | TADs, FISHnet domains |
| `pair` | `chrom1, start1, end1, chrom2, start2, end2` | loops |
| `peak` | `chrom, start, end` (+ `summit`, …) | MACS peaks |
| `segment` | `chrom, start, end, label` | A/B compartment runs |

```python
cd.intervals["tads.arcfish"]                          # set by call_tads_by_pval
cd.intervals["tads.arcfish"].to_bins(cd.bins)         # best-overlap row per bin (-1 = none)
cd.intervals["tads.arcfish"].to_bins(cd.bins, how="bool")
cd.intervals["compartments.axes_pc"].to_bins(cd.bins, column="label")
cd.intervals.add("peaks", peaks_df, kind="peak")
```

The structure callers store interval outputs in `cd.results` **and**
`cd.intervals` (the same object); on disk the result references
`intervals/<key>` instead of storing the table twice.

## Cell spatial position

Where each cell sits in the tissue or field of view is cell-level data,
kept apart from the per-spot `coords`.  Centroids are `cells` columns
(`centroid_x`, `centroid_y`, optionally `centroid_z`) described by a record
in `uns['cell_spatial']` (unit, frame, measured / inferred, source);
outlines are polygons in `cd.cell_shapes`, stored as GeoParquet — the
representation SpatialData uses for shapes.

```python
cd.set_cell_positions(xyz, cell_ids=ids, unit="um", frame="fov", region_col="fov",
                      status="measured", source="nuclear segmentation")
cd.cell_positions()                     # x, y, z (+ region) indexed by cell_id; record in .attrs
cd.set_cell_positions(xy_tangram, key="tangram", cell_ids=ids,     # a second, inferred set
                      frame="tissue", status="inferred", source="MERFISH atlas", method="Tangram")
cd.set_cell_shapes(polygons, cell_ids=ids, unit="um", frame="fov")  # vertex arrays, WKB or shapely
cd.cell_shapes_geodataframe("cell")     # GeoDataFrame (needs u-chrom[spatial])
```

- **Frames.** `frame="fov"` positions are local to one field of view
  (`region_col` names it); `"tissue"` / `"global"` are stitched frames.
  `in_coords_frame=True` says the positions share the frame of `coords`.
  Positions stored in voxels carry `voxel_size` / `voxel_unit`;
  `cell_positions(physical=True)` converts them.
- **Loaders.** `read_seqfish_multiomics(cell_clustering=…)` fills the
  Takei 2025 centroids (voxels, per FOV); `from_fofct(cell_table=…)`
  registers `Cent_ROI_x/y` (→ `centroid_x/y`) or Liu et al.'s
  `cell_center_x_global / _y_global`; `from_fofct(mapping_table=…)` reads
  the Cell/ROI Mapping table's `ROI_Boundaries` polygons into
  `cell_shapes['cell']`, and `to_fofct(mapping_table=…)` writes it.
- **SpatialData.**  `cd.link_spatialdata("sample.sdata.zarr")` records an
  external SpatialData store and the cell map (its table's `region` /
  `instance_key` ↔ `cell_id`); `cd.load_linked_spatialdata(cells=[...])`
  returns it, subset to those cells; `cd.to_spatialdata()` exports spots,
  centroids, outlines, the cell table and `points`.
- **Compatibility.**  `set_cell_spatial_coordinates()` is deprecated (it
  now writes the schema); columns written by older versions (`spatial_x`,
  the seqFISH+ loader's `x_centroid`) stay readable by `cell_positions()`.

On real data (`benchmarks/cell_spatial_validation.py`): Takei 2025
cerebellum rep 1, 1,799 / 1,799 cells with a 3-D position equal to the
clustering CSV, 0.86 µm median distance to the mean of the cell's spots
(xy 0.12 µm); Takei 2021 mESC, 201 / 201 cells (2-D, 0.50 µm to the spot
mean); Liu 2025 MOp, 14,733 / 14,733 cells in the global frame.  None of
these data sets ships cell outlines.

## Subsetting

Subset operations return **new** `ChromData` instances — they never
mutate the original.

```python
cd.get_chrom("chr1")           # all spots on chr1
cd.get_trace(5)                # only trace 5
cd.get_cell("cell_0")          # only cell "cell_0"
cd[cd.spots["chrom"] == "chr1"]  # boolean mask
cd[:100]                       # first 100 spots
```

All children (coords, spots, tracks, layers, cellm, and `points` /
`cell_shapes` via their `cell_id`) are filtered consistently; traces and cells that become empty are dropped.

## Results

`cd.results` is a `ResultsStore` — a dict-like mapping from a key to a
`ResultRecord` (value + provenance).  Indexing returns the value, so it
reads like a dict; analysis functions store their output with
provenance:

```python
from uchrom.strc.tad import call_tads_by_pval

tads = call_tads_by_pval(cd)              # chrom=None → all chromosomes, one table
cd.results["tads.arcfish"] is tads        # True
rec = cd.results.record("tads.arcfish")
rec.kind, rec.function, rec.params, rec.inputs, rec.uchrom_version, rec.created_utc

cd.results["my_table"] = df               # plain assignment: no provenance
cd.results.set("my_table", df, function="my.fn", params={"k": 3})
```

| kind | value |
|------|-------|
| `table` | `DataFrame` / `Series` |
| `intervals` | `DataFrame` of genomic intervals (TADs, loops, domains) |
| `array` | `ndarray` (not object dtype) |
| `mapping` | nested `dict` of the value types here |
| `scalar` | JSON-compatible scalar / list / tuple |

A value that cannot be written to disk raises `TypeError` **when it
is assigned**.  Values and provenance round-trip through
`.chromdata.zarr` / `.cdz`.  Results of converted `.h5cd` files older than
format 1.4 come with records that carry no provenance.

Analysis functions share one calling convention (`cd` first; then
keyword-only `chrom=None`, `trace_ids`, `cells`, `params`, `device`,
`key_added="<what>.<method>"`, `copy=False`) — see
[Structure identification](../structures/methods.md#calling-convention).  The
`uc.tl` / `uc.pp` namespaces are flat aliases:

```python
import uchrom as uc
uc.tl.call_tads(cd, method="arcfish")     # strc.tad.call_tads_by_pval
uc.tl.call_loops(cd)                      # strc.loop.call_loops_axiswise_f
uc.tl.call_compartments(cd)               # strc.comp.call_compartments_axes_pc
uc.pp.impute(cd, method="linear")         # im.impute.impute_coordinates
```

## On-demand distance matrix

Global `(n_spots, n_spots)` matrices are not stored — they are
meaningless across cells and scale poorly.  Compute per-trace on demand:

```python
D = cd.compute_distances(trace_id=0)  # (n_spots_in_trace, n_spots_in_trace)
```

## I/O

| Input | Method |
|-------|--------|
| Reconstruction CSV (chrom, start, end, x, y, z) | `ChromData.from_dataframe` |
| 4DN FOF-CT core table (+ cell / RNA tables) | `ChromData.from_fofct`; write with `cd.to_fofct` |
| `.chromdata.zarr` / `.cdz` | `ChromData.read` |
| legacy `.h5cd` (HDF5, format 1.x / 2.0) | convert once: `python -m uchrom.io.upgrade old.h5cd` |

```python
cd.write("data.chromdata.zarr")        # format 2.3: Zarr + Parquet (a directory)
cd.write("data.cdz")                   # the same store as one zip file
cd2 = ChromData.read("data.chromdata.zarr")
```

### Storage: `.chromdata.zarr`

A `.chromdata.zarr` store is a Zarr v3 directory whose tables are Parquet
files (zstd).  Every spot-aligned value is stored once: the coordinates
and key columns **partitioned by chromosome**
(`tables/coords/chrom=<name>/part-0.parquet`: `bin_id`, `trace_id`,
`cell_id`, `x, y, z`), every other spot-aligned column — extra spot
columns, `spot_tracks`, `layers` — in **cell-sorted primary tables**
(`tables/primary/`), and spot columns that only repeat a value of their
bin, cell or trace (a probe name, a sample id) once per key
(`tables/derived/`); the small tables (`bins`,
`bin_tracks`, `cells`, `traces`, `intervals/`, `points/`) are single
Parquet files; `cellm`, `binm`, result arrays and the `index/` offsets are
Zarr arrays; `results` provenance, `uns` and linked-file records are JSON
attributes.  The full layout is in `packages/chromdata/spec.md`.

- **Row order.**  Reading returns spots in the primary order, cell ›
  trace › chromosome › bin; every spot keeps its values.  A cell or a trace
  is one slice of the primary tables plus its coordinate runs (one per
  chromosome); a chromosome's coordinates are one partition.
  `ChromData.read(path, original_order=True)` restores the order of the
  object that was written (the store keeps the permutation in
  `index/source_row`).
- **Backed mode.**  `ChromData.read(path, backed=True)` loads only the
  small tables (bins, cells, traces, tracks per bin, results, uns) and the
  index; `coords`, `spots`, `spot_tracks` and `layers` stay on disk.
  `get_cell` / `get_trace` / `get_chrom` read the rows they need and
  return an ordinary in-memory `ChromData`; `iter_traces(batch=...,
  chrom=...)` / `iter_cells(batch=...)` stream chunks (in-memory objects
  yield the same chunks; `batch="auto"` sizes them from
  `uchrom.settings.memory_budget`); `to_memory()` loads everything.
- **Column selection.**  `get_*`, `iter_*`, `to_memory` and
  `read(..., backed=...)` take `columns=` / `tracks=`: `columns="coords"`
  reads the coordinates and the key columns (`trace_id`, `cell_id`,
  `bin_id`, loci) only — e.g. without the 62 per-spot z-scores of the
  Takei 2025 data; `columns=[...]` adds named spot columns, spot tracks or
  layers; `tracks=[...]` picks spot tracks.  The default reads everything.

```python
big = ChromData.read("cerebellum.chromdata.zarr", backed=True)   # ~0.03 s
cell = big.get_cell("R1_P0_C12")                 # one primary slice + a coordinate run per chromosome
chr7 = big.get_chrom("chr7", columns="coords")   # one partition, xyz + keys only
for chunk in big.iter_traces("auto", chrom="chr7", columns="coords"):   # bounded memory
    ...
```

- **Options.**  `cd.write(path, coord_dtype="float32")` halves the
  coordinate columns; `row_group_rows=` (primary tables, default 65,536,
  groups end on cell boundaries) and `compression_level=` (zstd, default
  3) tune the Parquet files.
- **Format 2.0 / 2.1 stores** stay readable, in memory and backed; rewrite
  them with `python -m uchrom.io.upgrade old.chromdata.zarr
  new.chromdata.zarr`.  Older readers cannot read newer stores.
- **`.h5cd`** (the HDF5 container of format 1.x / 2.0) is no longer read or
  written: `ChromData.read` / `write` raise a `ValueError` that names the
  converter below.

### Larger than memory: streaming import and analysis

```python
import uchrom
uchrom.settings.memory_budget = "8GB"        # default: half of the available RAM

# import in chunks, writing the store as it goes (returns it backed)
cd = ChromData.from_fofct("core.csv", cell_table="cells.csv", out="big.chromdata.zarr")
from uchrom.io import read_seqfish_multiomics
cd = read_seqfish_multiomics("raw/cerebellum_rep1_pos*.csv", locus_annotation=..., out="cerebellum.chromdata.zarr")

# any chunks: ChromData objects or arrays
with ChromData.writer("big.chromdata.zarr") as w:
    for chunk in chunks:
        w.append(chunk)                  # or w.append(coords=..., spots=..., spot_tracks=...)
    w.finish(cells=cells, uns={...})

# population statistics streamed over the traces
from uchrom.fea import distance_map
m = distance_map(cd, "chr7", "median")   # exact median distance per bin pair
loops = uchrom.strc.loop.call_loops_axiswise_f(cd, chrom="chr7")   # streams on a backed cd
```

- The streaming writer spills each chunk to temporary per-chromosome runs
  and merges each partition in pieces of whole cells that fit the budget;
  the store equals what `ChromData(...).write()` writes for the
  concatenated input (same rows, order, index).
- `distance_map` (median / mean) is exact: medians are taken one row band
  of the matrix at a time (the pair observations of a band fit the
  budget), means accumulate in trace order — both identical to the dense
  in-memory computation.  The ArcFISH callers (`call_loops_axiswise_f`,
  `call_tads_by_pval`) build their axis-variance cube the same way
  (`streaming=True`, default on backed data): exact medians and outlier
  masks, variances equal up to floating-point rounding.

### Converting `.h5cd` files

`upgrade_h5cd` reads an `.h5cd` (format 1.x or 2.0) and writes it as a
`.chromdata.zarr` / `.cdz`.  For 1.x files `bins` become the unique spot
loci, and the spot-aligned 1.x `tracks` table is split into `bin_tracks`
(columns constant within every bin) and `spot_tracks` (the rest):

```python
from uchrom.io import upgrade_h5cd
upgrade_h5cd("old.h5cd")               # → old.chromdata.zarr; the source is never modified
upgrade_h5cd("old.h5cd", "old.cdz")    # the target suffix picks the container
```

```bash
python -m uchrom.io.upgrade old.h5cd                 # → old.chromdata.zarr
python -m uchrom.io.upgrade data/*.h5cd --out-dir converted/ [--format cdz]
```

Code changes, if any:

- `cd.tracks[...]` → `cd.bin_tracks[...]` (per locus) or
  `cd.spot_tracks[...]` (per spot); `cd.tracks_spot_view()` gives the
  old spot-aligned table.
- `ChromData(..., tracks=spot_aligned)` → `spot_tracks=` (per spot) or a
  bins-aligned `tracks=`.
- `fea.project_interval_features_to_spots` →
  `project_interval_features_to_bins`.
- Reading spot loci keeps working; `cd.spots_with_loci()` is the stable
  form.
- 1.x readers cannot read 2.0 files.

### Multi-omics FOF-CT: cell table and RNA spots

4DN FOF-CT data sets can ship companion tables next to the core DNA
table.  Pass them to `from_fofct` to keep everything in one store:

```python
cd = ChromData.from_fofct(
    "4DNFIHF3JCBY.csv",                 # DNA spots / traces (core)
    cell_table="4DNFIFINA2U9.csv",      # per-cell: area, centroid, RNA counts
    rna_table="4DNFIJ52NVDV.csv",       # nascent RNA spots
)
cd.cells[["nucleus_area_um2", "rna.Nanog"]]   # genes are prefixed "rna."
cd.points["rna"].head()                        # x, y, z, gene, cell_id, …
cd.get_cell("0_2").points["rna"]               # RNA spots of one cell
cd.to_fofct("core.csv", cell_table="cell.csv", rna_table="rna.csv")   # and back to FOF-CT
cd.write("takei2021_multiomics.chromdata.zarr")
```

Cell embeddings from the RNA counts (stored in `cd.cellm`, parameters in
`cd.uns["embeddings"]`):

```python
from uchrom.emb import embed_cells

embed_cells(cd)          # rna_pca (10 PCs), rna_tsne, rna_umap (needs umap-learn)
cd.cellm["rna_umap"]     # (n_cells, 2), rows follow cd.cells
```

Counts are `log1p`-transformed and z-scored per gene.  Library-size
normalisation is **off** by default (`library_size=True` to enable): in
small targeted panels one housekeeping gene can dominate the total (Eef2
is ~16 % of all counts in Takei 2021), and dividing by it makes PC1 "Eef2
vs everything else".  Without it, PC1 on Takei 2021 is overall expression
level and PC2 separates naive (Nanog, Esrrb, Tfcp2l1, Tbx3) from primed /
formative (Otx2, Lin28a/b, Dnmt3a) pluripotency markers.

### Embeddings from other modalities

`embed_cells(cd, source=…)` embeds any `cd.cells` prefix group, or an
explicit cells × features matrix (`matrix=`, dense or `scipy.sparse`), with
a normalisation suited to the data (`normalization="auto"` picks it from
`source`; recorded in `uns["embeddings"][key]["normalization"]`):

| `source` | normalisation | linear step | keys |
|---|---|---|---|
| `rna` (and unknown) | `counts`: `log1p` + z-score (optionally library size) | PCA | `rna_pca`, `rna_tsne`, `rna_umap` |
| `if`, `protein` | `zscore` (`log=True` adds `log1p`) | PCA | `if_pca`, … |
| `atac` | `tfidf`: TF-IDF + truncated SVD (LSI); component 1 dropped if \|r\| with log depth > 0.5 | LSI | `atac_lsi`, `atac_tsne`, `atac_umap` |
| `hic` | `none` (features used as given) | PCA | `hic_pca`, … |

Each entry also records `modality` ("RNA", "Histone/IF", "ATAC", "Hi-C"),
which the web browser uses to group the Embedding picker.

Imaging data carry per-spot signals in `cd.spot_tracks`.
`aggregate_tracks` turns them into per-cell features:

```python
from uchrom.emb import aggregate_tracks, embed_cells
from uchrom.io.seqfish_multiomics import IF_COLUMNS   # 48 antibody channels

aggregate_tracks(cd, IF_COLUMNS, prefix="if")                  # cells["if.H3K27ac"], … (mean)
aggregate_tracks(cd, IF_COLUMNS, by="chrom", write=False)      # if.H3K27ac@chr1, …
aggregate_tracks(cd, IF_COLUMNS, by=10_000_000, write=False)   # if.H3K27ac@chr1:3 (10 Mb bins)
corr = aggregate_tracks(cd, IF_COLUMNS, stat="corr", write=False)  # if.H3K27ac~H3K9me3, …
embed_cells(cd, source="if", matrix=corr.to_numpy(), normalization="zscore")
```

On Takei 2025 cerebellum (47 cells, `example-data/takei2025_fov0/`) the
per-spot IF z-scores are already close to per-cell normalised (the spread
of per-cell means is ~0.1 of the within-cell SD), so per-cell means carry
little cell-type signal.  The within-cell mark–mark correlations (how marks
co-occur on the same loci) separated the cell types best — kNN-5 purity
0.61 vs 0.44 for means, 0.39 for mark × chromosome, ~0.5 for mark × 10 Mb;
chance ≈ 0.28 — and are what `build_takei2025_fov0.py` uses for
`if_pca / if_tsne / if_umap` (the per-cell means stay as `if.*` for
colouring).  With 47 cells these numbers are indicative only.

Single-cell contact maps (`.scool`) give a Hi-C embedding with the
scHiCluster recipe (convolution → random walk with restart → top-20 %
binarisation → per-chromosome PCA):

```python
from uchrom.emb import scool_cell_features

feats, cols, n_contacts = scool_cell_features("cells_1Mb.scool", cd.cells.index)
embed_cells(cd, source="hic", matrix=feats, normalization="none", n_pcs=20)
```

`example-data/build_schicar_mop.py` builds the scHiCAR dataset this way:
RNA (`rna_*`), ATAC (100 kb bins → LSI, `atac_*`; gene activity of the RNA
HVGs as `atac.<gene>`), Hi-C (`hic_*`) and the paper's UMAP.

The web browser (`python -m uchrom_browser`) can colour cells by any
of these cell fields, draw the RNA spots with the chromatin traces, and
show the embeddings as a 2-D view linked to the 3-D one.

Every ChromData file has a format version stamp; legacy files are read
and upgraded.  See [Concepts — On-disk format](../start/concepts.md) for details.

## Why not AnnData?

AnnData observations are flat (one row = one cell).  Chromatin tracing
has an extra hierarchy (Cell → Trace → Spot), and the natural "sample
axis" differs per operation — a distance matrix is per-trace, cell-type
embeddings are per-cell, TAD calls are per-locus.  `ChromData` exposes
that hierarchy directly while reusing the AnnData-like `obsm`/`uns`
conventions where they apply (`cellm`, `uns`).
