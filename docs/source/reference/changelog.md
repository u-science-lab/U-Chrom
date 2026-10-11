# Changelog

## Unreleased

- **Proximity by genomic separation, from contacts or coordinates.**  `uchrom.fea.separation_profile`: per cell,
  the contacts at short (1-2 Mb) over long (19-54 Mb) separations of the linked per-cell maps, or the median 3-D
  distance of locus pairs at long over short separations of the traces, separations midpoint to midpoint in both
  (`log2_short_long`, higher when the short range is relatively closer); `SeparationParams(edges=...)` stores the
  whole profile per cell (`cd.cellm["separation.profile"]`).  On seven atlas stores (84,778 cells and spots) it
  gives the cross-assay pilot's counts for every cell, and on the Takei 2021 and Tan 2021 structure sets its pair
  counts and medians to float32 precision (`benchmarks/cross_assay`, which adds Liu et al. 2025's DNA-MERFISH).
- **Copy number from contacts.**  `uchrom.fea.chromosome_dosage`: per cell or spatial Hi-C spot, log2 of each
  chromosome's share of the contact legs over the median cell's (per section with `groupby=`), and optionally the
  profiles' principal components (`cd.cellm["contacts.dosage.pcs"]`), covariates for
  `uchrom.spatial.spatially_variable`.  The melanoma benchmark's copy-number profiles are unchanged with it
  (`benchmarks/spatial_variable`, stage cnv: largest difference 6e-15).
- **Structure calling from single cells.**  `uc.tl.call_loops(cd, method="snaphic")`
  (`uchrom.strc.loop.call_loops_snaphic`, Yu et al. 2021): loops across cells, each cell's map imputed by a
  random walk with restart (`uchrom.fea.impute_rwr`); `uc.tl.single_cell_boundaries` (insulation of each
  imputed map, consensus); `uc.tl.single_cell_compartments` (scA/B, Tan et al. 2021); the tracing callers on
  reconstructed structures (`uchrom.io.read_3dg_cells`; `ds.load("tan2018_gm12878")` holds the Dip-C
  structures; `call_compartments_axes_pc(centromeres=)`).  New loader `nagano2017_dip_serum`.  On the paper's
  742 mES cells SnapHiC recalls 0.60 of the bulk loops (paper 0.60) at precision 0.60 (0.66); on the same
  cells and contacts it gives the authors' 479 loops.  Docs: [calling structures from single
  cells](../schic/structures.md), tutorial `sc_structures`.
- **Structure calling on Hi-C maps, implemented in U-Chrom** (no cooltools / Mustache dependency):
  compartments by the cis eigenvector + saddle strength (`method="eig"`), insulation domains
  (`method="insulation"`), HiCCUPS and Mustache loops, pileups (APA), pseudo-bulk maps of cell groups
  (`uc.tl.pseudobulk`, `sample_cells_by_depth`), banded reads of large maps (`uchrom.fea.band`), `thin_map`,
  Juicer list readers.  Identical to cooltools where it is the reference (eigenvectors to 1e-14, insulation
  boundaries, HiCCUPS enriched pixels).  Docs: [calling structures from a map](../bulk/structures.md).
- **`uchrom-maps`: native kernels** (Rust, rayon; extra `u-chrom[maps]`) for HiCCUPS scoring, the Mustache
  scan and the single-cell imputation; `uchrom` imports it lazily and keeps the numpy code as reference and
  fallback (`BACKEND = "auto" | "native" | "numpy"`).
- **Data**: `uchrom.datasets.fetch(<atlas id>)` downloads an atlas store's one-file copy (`.cdz`) for offline
  work, which `load` then reads; `list_atlas()` gives study, organism, tissue, assembly and sizes.  A docs
  chapter on [datasets and the atlas](../datasets/index.md) and a [tutorial gallery](../gallery.md).
- **Licence**: MIT (`LICENSE`; `uchrom-recon` stays LGPL-3.0-or-later).

- **A monorepo, and no data in it.**  The packages live in `packages/`
  (`chromdata`, `u-chrom`, `uchrom-browser`, `uchrom-discovery` and the
  native engine `uchrom-recon`, formerly `u-chrom-nucdyn` / `uchrom_nucdyn`),
  the deployments in `apps/` (the atlas, the hosted web browser).  The Qt
  desktop browser, the Taichi NucDynamics port and GEM are removed (the web
  browser and the native engine replace them; PyVista tubes are the `plot3d`
  extra).  `example-data/` is gone: `uchrom.datasets.atlas(id)` opens a store
  of the public atlas over HTTP; `uchrom.datasets.fetch(name)` /
  `python -m uchrom.datasets fetch` downloads an original file from its
  source (4DN, GEO, Zenodo, GitHub, UCSC; md5-checked) into `$UCHROM_DATA`,
  else `~/.cache/uchrom` — some are built on first fetch (Rao 2014 Hi-C
  slices read from the GEO `.hic` over HTTP, the first cells of a Takei 2025
  field of view streamed from Zenodo); the recipes that build the atlas
  stores are in `apps/atlas/recipes/`; unit tests read small fixtures in
  `packages/*/tests/fixtures/`.  The tutorials read the atlas or fetch.
- **`chromdata.embedded.export_scool` reads each chromosome once for all the
  cells** (was cell by cell; 2,000 scHiCAR cells from the atlas over HTTP:
  21 s, identical pixels) and takes `trans=False` (intra-chromosomal
  contacts only).
- **`.h5cd` is no longer a ChromData format.**  `ChromData.read` / `write`
  (and every loader, CLI and the browser built on them) refuse the HDF5
  `.h5cd` container of format 1.x / 2.0 with a `ValueError` that names the
  converter; `python -m uchrom.io.upgrade old.h5cd` /
  `uchrom.io.upgrade_h5cd` convert a file once (targets: `.chromdata.zarr`,
  `.cdz`; the `--compression` / `--level` / `--compress-floats` options and
  `.h5cd` targets are gone).  The reader lives on in the private
  `uchrom.io._h5cd_legacy` (also used by the format benchmarks).  The
  in-repo Sox2 FISH examples are now `mESC_Sox2_5cells_*.chromdata.zarr`.
  `load_seqfish_multiomics_linked(h5cd_path=)` is renamed `cd_path=`
  (the old name warns).
- **Cell spatial position is first-class (`.chromdata.zarr` format 2.3).**
  Centroids are `cells` columns `centroid_x`, `centroid_y` [, `centroid_z`]
  with a record `uns['cell_spatial'][key]` (unit, frame fov / tissue /
  global, `region_col`, `in_coords_frame`, status measured / inferred,
  source, optional voxel size): `cd.set_cell_positions()`,
  `cd.cell_positions(key, physical=)`.  Optional outlines
  `cd.cell_shapes[key]` (`cell_id` + WKB polygons) are stored as GeoParquet
  (`tables/cell_shapes/<key>.parquet`, readable by `geopandas.read_parquet`);
  `cd.set_cell_shapes()` needs no geometry library,
  `cd.cell_shapes_geodataframe()` needs shapely + geopandas (new extra
  `u-chrom[spatial]`).  `cd.link_spatialdata()` records an external
  SpatialData store and its cell map (`region` / `instance_key` ↔
  `cell_id`), checked by `validate_links()`;
  `cd.load_linked_spatialdata(cells=)`, `cd.to_spatialdata()` (extra
  `u-chrom[spatialdata]`).  Loaders: `read_seqfish_multiomics` writes
  `centroid_x/y/z` (voxels, per FOV; **was `x_centroid` …**) and a `fov`
  cells column; `from_fofct(cell_table=)` registers `Cent_ROI_x/y[/z]` or
  `cell_center_x_global / _y_global`; `from_fofct(mapping_table=)` /
  `to_fofct(mapping_table=)` read / write the Cell/ROI Mapping table
  (`ROI_Boundaries`, OME polygons).  `set_cell_spatial_coordinates()` is
  deprecated and now writes the schema (`centroid_x`, was `spatial_x`);
  older columns stay readable through `cell_positions()`.  Format 2.3 =
  the 2.2 layout + these additive parts: 2.2 readers read 2.3 stores with a
  warning; 2.0–2.2 stores read unchanged.  Real data
  (`benchmarks/cell_spatial_validation.py`): Takei 2025 cerebellum 1,799 /
  1,799 cells, Takei 2021 201 / 201, Liu 2025 MOp 14,733 / 14,733, all equal
  to the source tables.

- **`.chromdata.zarr` format 2.2 — every spot value stored once.**
  Coordinates + keys in a chromosome-partitioned table
  (`tables/coords/chrom=<name>/`), every other spot-aligned column in
  cell-sorted primary tables without key columns (`tables/primary/`), and
  spot columns that are a function of the bin / cell / trace (probe names,
  sample ids) once per key (`tables/derived/`; exact round trip).  Float
  columns use Parquet dictionary pages; the lossless decimal codec
  (`chromdata.floatcodec`) is opt-in (`float_encoding=`).  Parallel full
  reads.  Takei 2025 (1e7 spots, 62 tracks): 1.81 GB (2.1: 2.58 GB; flat
  Parquet: 2.11 GB), full read 0.57 s (2.1: 0.81 s; Parquet 0.76 s),
  `get_cell` 8.5 ms (2.1: 25 ms), `get_chrom(columns="coords")` 15 ms;
  Liu 2025 MOp 255 MB (2.1: 272 MB).  **Regression:** `get_chrom` with
  spot tracks 0.53 s at 1e7 (2.1: 39 ms).  In-memory row order is now cell
  › trace › chromosome › bin (`iter_traces` / `iter_cells` still stream
  chromosome › cell › trace).  2.0 / 2.1 stores stay readable;
  `python -m uchrom.io.upgrade` rewrites them (keeping the original row
  order); the streaming writer and `benchmarks/fig2/replicate_store.py`
  write 2.2.
- **`.chromdata.zarr` format 2.1 — spot tables partitioned by
  chromosome.**  `tables/spots/chrom=<name>/part-0.parquet` (and the same
  for `spot_tracks` and `layers/<key>`), sorted cell › trace › bin inside a
  partition, 16,384-row row groups (was 65,536); `index/` gains
  `partition_offsets` / `partition_groups` / `partition_chrom` /
  `cell_partition` and one `cell_offsets` entry per (chromosome, cell).
  Backed `get_chrom` reads one partition (Takei 2025, 1e7 spots: 0.77 s →
  0.04 s; 1e8: 8.9 s → 0.49 s); `get_cell` reads one row group per
  chromosome and is slower (8 → 23 ms at 1e7; 22 → 42 ms at 1e8; with
  `columns="coords"` 4.4 / 22 ms).  Stores with many per-spot tracks grow
  (Takei: +35 %, the per-spot z-scores compress worse once a cell's
  chromosomes are apart; no Parquet option recovers it —
  `benchmarks/fig2/spot_tracks_encoding.py`); Liu 2025 MOp shrinks 3 %.
  Full reads: 0.98 → 1.11 s at 1e7.
  **Stored row order is now chromosome › cell › trace › bin**, also for
  in-memory `iter_traces` / `iter_cells`.  2.0 stores stay readable
  (in memory and backed); 2.0 readers cannot read 2.1 stores —
  `python -m uchrom.io.upgrade old.chromdata.zarr new.chromdata.zarr`
  rewrites them.
- **Column selection**: `get_cell` / `get_trace` / `get_chrom`,
  `iter_traces` / `iter_cells`, `to_memory` and `ChromData.read` take
  `columns=` / `tracks=` (`columns="coords"`: coordinates and key columns
  only); the web browser reads geometry with `columns="coords"`.
  `iter_traces(chrom=...)`; `batch="auto"`.
- **Streaming (roadmap step 7)**: `uchrom.settings.memory_budget`;
  `ChromData.writer(path)` (`chromdata.stream.ChromDataWriter`: append
  chunks, spill per chromosome, merge each partition in pieces within the
  budget — the store equals the in-memory writer's);
  `ChromData.from_fofct(..., out=...)` (chunked) and
  `read_seqfish_multiomics(..., out=...)` (FOV by FOV) return the store
  backed.  `uchrom.fea.distance_map`: exact per-chromosome median / mean
  distance maps streamed over the traces (median per row band; bitwise
  equal to the dense `mean_distance_matrix`).  `call_loops_axiswise_f` and
  `call_tads_by_pval` take `streaming=` (default on backed data;
  `uchrom.fea.arc_stream.axis_cube_streaming`): memory `O(n_bins²)`
  instead of `O(n_traces × n_bins²)`, same calls.
- **`.chromdata.zarr` — the format 2.0 container** (Zarr v3 + Parquet, the
  SpatialData approach) is the new default: `cd.write("x.chromdata.zarr")`
  (or `x.cdz`, the same store in one zip file).  Spots are stored sorted by
  (cell, trace, bin) with an `index/` of row offsets, so a round trip keeps
  every spot but may change the row order (`ChromData.read(path,
  original_order=True)` restores it).  **Backed mode**:
  `ChromData.read(path, backed=True)` loads the small tables only;
  `get_cell` / `get_trace` / `get_chrom` read the rows they need;
  `iter_traces(batch)` / `iter_cells(batch)` stream chunks (also on
  in-memory objects); `to_memory()` loads all.  `.h5cd` files (1.x and
  2.0) are still read; writing `.h5cd` is deprecated (it warns).
  `python -m uchrom.io.upgrade old.h5cd` converts to `old.chromdata.zarr`.
  The web browser opens stores backed; the example-data builders, tutorials
  and CLIs write the new format.  **Requires Python ≥ 3.11** and the new
  core dependencies `zarr>=3` and `pyarrow`.
- **FOF-CT writer**: `cd.to_fofct(path, cell_table=None, rna_table=None)`
  and `uchrom.io.write_fofct` write the 4DN FOF-CT core table (with its
  `##` / `#` header lines, from `uns['fofct_header']` or `uns`) and
  optionally the cell and RNA-spot companion tables — the inverse of
  `from_fofct`.  `from_fofct` now parses floats exactly
  (`float_precision="round_trip"`; the default parser could be 1 ulp off),
  so FOF-CT round trips are value-identical.
- `cd.results` is now a `ResultsStore` of `ResultRecord`s: every result
  carries its kind, producing function, parameters, inputs, uchrom
  version and timestamp.  Unwritable values raise `TypeError` at
  assignment.  `.h5cd` format 1.4 stores the provenance as attrs; older
  files still read.
- One calling convention for the structure callers
  (`call_tads_by_pval`, `call_domains_fishnet`, `call_loops_axiswise_f`,
  `call_compartments_axes_pc`, new `call_tads_di`): keyword-only
  `chrom=None` (all chromosomes, one merged table), `trace_ids`,
  `cells`, `params`, `key_added="<what>.<method>"`, `copy`.
  Positional `chrom`, `store=`, `result_key=` and
  `strc.call_*_multi` are deprecated (they warn and keep the 1.x keys).
- `uchrom.tl` / `uchrom.pp` alias namespaces.
- **`.h5cd` format 2.0 — the `bins` locus axis** (breaking on disk; 1.x
  files still read).  `cd.bins` (index `bin_id`), required
  `spots.bin_id` (derived from `chrom/start/end` by every constructor and
  loader), bin-level `cd.bin_tracks` vs per-spot `cd.spot_tracks`,
  `cd.binm`, typed `cd.intervals` (`domain | pair | peak | segment`, with
  `to_bins`).  Structure callers also fill `cd.intervals`; compartments add
  segments and a per-bin `pc2` track.  `fea` / `strc` feature writers
  project onto bins (`fea.project_interval_features_to_bins`; the spot
  version is deprecated).  `cd.tracks` is a deprecated spot-aligned view.
  `uchrom.io.upgrade_h5cd` and `python -m uchrom.io.upgrade` rewrite 1.x
  files; the web browser lists bin- and spot-level tracks and typed
  intervals.  Large integer / string datasets are chunked and gzip-4
  compressed (`write(compression=…, compress_floats=…)`); strings are
  encoded / decoded vectorised.
- Fix: `from_fofct` kept the last `##columns=` name intact when it ends in
  `)` (`n_per_dist(um)` was read as `n_per_dist(um`).
- seqFISH+ loader (Takei 2025): `traces` now reports `allele`, `n_spots`,
  `n_loci`, `n_duplicate_loci` and per-column allele majority / agreement
  instead of the first spot's `dbscan_*` values; the docstring warns that
  the default `allele_col="dbscan_ldp_nbr_allele"` often merges homologs
  (default unchanged).

## 0.2.0 — 2026-04

- Renamed package from `nucbox` to `uchrom` / `u-chrom`.
- New core container `ChromData` with HDF5 persistence (`.h5cd`) and
  format versioning (see [Concepts — on-disk format](../start/concepts.md)).
- `uchrom.io.save_particles` / extended `read_particles` — all
  reconstruction modules now write `.h5cd` by default.
- Bulk MDS reconstruction (`uchrom.recon.bulk.mds`) — PyTorch SMACOF
  with inter-chromosomal whole-genome support.
- Browser updates:
  - Trace-aware rendering (per `(chrom, trace_id)` polymer).
  - "Per Trace" colour mode.
  - Unified Chromosome / Region / Trace Management tab.
  - Trace Statistics panel (Distance Matrix / Contact Map / Rg
    Histogram / Split by Trace).
  - Click-to-identify trace overlay.
  - Draggable Layers / Properties divider.
  - macOS Dock icon + startup logo.
- ArcFISH-style axis-wise F-test loop caller
  (`uchrom.strc.loop.call_loops_axiswise_f`) — GPU-accelerated via
  PyTorch, CLI under `python -m uchrom.strc.loop`.
- New population-aggregate modules:
  - `uchrom.fea.distance` (median distance matrix, contact frequency,
    radius of gyration)
  - `uchrom.fea.arc` (axis variance cube, LOWESS filter+normalise,
    axis weights)
  - `uchrom.pl.trace_stats` (matplotlib helpers)
  - `uchrom.utils.stats` (Cauchy combination test, log-log LOWESS)
- Version stamp on `.h5cd` files with MAJOR/MINOR semantics and
  legacy-file handling.
