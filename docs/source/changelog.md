# Changelog

## Unreleased

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
  (`uchrom.core.floatcodec`) is opt-in (`float_encoding=`).  Parallel full
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
  `ChromData.writer(path)` (`uchrom.core.stream.ChromDataWriter`: append
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
  format versioning (see [Concepts — on-disk format](concepts.md)).
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
