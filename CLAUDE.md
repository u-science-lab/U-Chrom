# U-Chrom Development Guide

## Project Vision

U-Chrom (Universal Chromatin) is a general-purpose toolkit for chromatin 3D structure data analysis. The name reflects its goal: providing a **universal** framework that works across different data modalities and analysis tasks.

### Core Data Structure

The central data structure is a **structure table** — a DataFrame where each row represents a genomic bin with its 3D coordinates (in `ChromData` format 2.0 the loci live in a shared `bins` table and each spot points at one via `bin_id`):

| chrom | start | end | x | y | z |
|-------|-------|-----|---|---|---|

This table is the common interface between all modules. It can be produced from:
- **Sequencing-based data** (Hi-C, Dip-C, etc.) → `uchrom.recon` (3D reconstruction)
- **Imaging-based data** (DNA FISH, chromatin tracing) → `uchrom.im` (image processing) + tracing

### Downstream Analysis

From the structure table, downstream modules perform:
- Distance matrix reconstruction (3D coords → pairwise distances)
- Structure identification: A/B compartments (`uchrom.strc.comp`), TADs (`uchrom.strc.tad`), loops (`uchrom.strc.loop`)
- Single-cell embedding (`uchrom.emb`) — population-level analysis of single-cell structures
- Geometric feature computation (`uchrom.fea`)
- Visualization (`uchrom.browser`, `uchrom.pl`)

## Package Structure

A monorepo: every package in `packages/` (each with its own pyproject, README and `tests/`),
deployments in `apps/`; the root holds the repository (docs, benchmarks, tutorials, example-data, skills).

```
packages/
├── chromdata/         `chromdata` — the data model: ChromData (cdata.py), the .chromdata.zarr
│                      store (zarrcd.py), backed mode (backed.py), remote stores, embedded
│                      copies, the atlas catalog (catalog.py); format spec in spec.md.
│                      Depends on numpy / pandas / zarr / pyarrow only, never imports uchrom.
├── uchrom-browser/    `uchrom-browser` (import uchrom_browser) — the web browser: FastAPI server +
│                      React/Three.js SPA (frontend/, built into static/ and committed; API.md).
│                      Depends on chromdata only, never imports uchrom.
├── uchrom-discovery/  `uchrom-discovery` (import uchrom_discovery): LLM-driven multi-omics
│                      auto-discovery — ChromData schema → ideas → notebooks → verification →
│                      evidence; iterative idea graph, pre-discovery enrichment, Pantheon /
│                      Claude / Codex CLI backends, graph UI.
├── uchrom-recon/      `uchrom-recon` (import uchrom_recon; formerly u-chrom-nucdyn / uchrom_nucdyn):
│                      the native 3-D reconstruction engine, Rust + PyO3 (maturin, abi3) —
│                      contact preprocessing, hierarchical annealing, CPU (f64, rayon) and GPU
│                      (wgpu/WGSL, f32, feature `gpu`) backends, protocols nuc_dynamics_2017
│                      (default) / release_1.3 / robust (= EMber, alias "ember": noise-aware
│                      method, src/robust.rs; PREREG in benchmarks/screcon) / igm.  `cargo test`
│                      in packages/uchrom-recon; `pip install ./packages/uchrom-recon` (= extra
│                      `u-chrom[recon]`).  LGPL-3.0 (re-implementation of tjs23/nuc_dynamics).
└── uchrom/            `u-chrom` (import uchrom) — the analysis library (depends on chromdata);
                       the tree below is packages/uchrom/uchrom/
apps/
├── atlas/             the atlas: datasets.json, site + thumbnails (build.py, tests/), publishing (deploy/)
└── hosted-browser/    the public web browser: Cloudflare Worker + container (chromdata + uchrom-browser)

uchrom/                (packages/uchrom/uchrom)
├── core/            deprecated alias of chromdata (`from chromdata import ChromData`)
├── convention.py    the calling convention of analysis functions
├── io/              Data I/O (.pairs, .cool, .hic, .3dg, .csv, .pdb, seqFISH multi-omics)
├── recon/           3D reconstruction
│   ├── sc/          Single-cell reconstruction
│   │   ├── ember.py EMber: reconstruct_ember (noise-aware; native engine protocol
│   │   │            "robust", alias "ember"; PREREG / TEST_RESULTS in benchmarks/screcon)
│   │   ├── nucdyn/  NucDynamics: reconstruct_nucdyn / CLI on the native engine
│   │   │            (packages/uchrom-recon; required)
│   │   └── gem/     GEM (energy minimization, Taichi autodiff; extra `gem`)
│   ├── bulk/        Bulk reconstruction
│   │   ├── mds/     MDS/SMACOF (PyTorch GPU; partitioned + inter-chrom)
│   │   └── deconv/  Population deconvolution of bulk Hi-C: deconvolve(..., method=)
│   │                dispatcher; preprocess.py (Hi-C -> contact probabilities);
│   │                igm/ (IGM A/M population modelling on the native engine,
│   │                protocol "igm"; cells = structures, traces = chromosome copies)
│   └── fish/        GEM-FISH: Hi-C + FISH combined (PyTorch; TAD-level + intra-TAD)
├── im/              Imaging-side processing
│   ├── trace/       Chromatin tracing / spot-to-trace alignment (Jie aligner)
│   └── impute/      FISH coordinate imputation (linear, grid, SnapFISH-IMPUTE)
├── strc/            Structure identification
│   ├── tad/         TAD detection (directionality index, ArcFISH arc p-value, FISHnet)
│   ├── loop/        Loop detection (axis-wise F-test)
│   ├── comp/        Compartment detection (axes PC)
│   └── enrichment.py  Run structure callers and project results onto spots
├── fea/             Per-bin features (distance, arc, sequence, GTF annotation,
│                    MACS-style peaks, structure projection) + feature registry
├── emb/             Single-cell embedding (Higashi / FastHigashi wrapper)
├── pl/              Plotting (3D structure, trace statistics)
├── utils/           Shared statistics helpers (LOWESS, etc.)
├── browser/         Desktop 3D browser (PyVista + PyQt5); `--web` starts uchrom-browser
└── op.py            Misc operations (mark empty particles)
```

- **Development install** (the packages are not on PyPI): `uv pip install -e "packages/uchrom[web]"` (the
  `[tool.uv.sources]` of each pyproject take the sibling packages from their folders), or with pip
  `pip install -e packages/chromdata -e packages/uchrom-browser -e "packages/uchrom[web]"`;
  discovery: `pip install -e packages/uchrom-discovery`; the native engine: `pip install ./packages/uchrom-recon`
  (needs Rust).
- **Package dependencies**: chromdata ← uchrom-browser; chromdata ← uchrom ← uchrom-discovery;
  apps use them all.  chromdata and uchrom-browser never import uchrom (their `tests/test_standalone.py`
  check it); new data-model code goes into chromdata, new analysis into uchrom.
- **Dependency direction is one-way**: `uchrom_discovery` may import the
  public `uchrom` API; `uchrom` must never import `uchrom_discovery`
  (except the deprecated `uchrom.auto_discovery` shim and the deprecated
  `ChromData.*discovery*` delegators, both slated for removal).  Reusable
  feature computation belongs in `uchrom.fea` / `uchrom.strc`, not in
  discovery.
- **The paper lives elsewhere**: manuscripts, figure scripts and figure results are in
  `u-science-lab/u-chrom-paper` (private; check it out next to this repository as
  `../u-chrom-paper`).  Benchmarks that feed a figure stay here and write
  `manuscripts/full/figures/<fig>/results/*.json` there (`benchmarks/_paper.py`, `$UCHROM_PAPER`); library
  changes a figure needs are made here first.  Never re-create `paper/` in this repository; a
  symlink `paper -> ../u-chrom-paper` (ignored) may show the paper checkout next to the code.
- **Tests live in each package** (`packages/<pkg>/tests`, `apps/atlas/tests`); every suite is a
  `tests` package, so run each from its folder: `cd packages/uchrom && pytest tests` (likewise
  chromdata, uchrom-browser, uchrom-discovery; `cd apps/atlas && pytest tests`; `cargo test` in
  uchrom-recon; benchmark helpers: `pytest benchmarks/<name>/tests`).  A test goes to the package whose code it tests: chromdata's and uchrom-browser's
  suites run without uchrom installed; tests of the legacy `.h5cd` container / the upgrade are
  uchrom's (`uchrom.io`); integration tests (uchrom + the browser) are uchrom's and skip without
  uchrom-browser.  Shared fixtures (an object with every attribute, a store with linked / embedded
  maps, a folder atlas, an HTTP server with range requests, store comparisons) are
  `chromdata.testing`; each suite's `tests/__init__.py` has `REPO` (the repository root, for
  example-data/).
- `uchrom` stays pure Python: it imports `uchrom_recon` lazily (tests skip
  when it is not installed); the native crate never imports `uchrom`.

## ChromData — Core Data Container

`ChromData` (`chromdata.ChromData`, also `uchrom.ChromData`; package `packages/chromdata`) is the central data structure, analogous to AnnData for scRNA-seq.

### Hierarchy

Cell → Trace → Spot; every Spot points at one Bin (the locus axis, shared by all cells).

### Attributes

```
ChromData (format 2.0)
├── bins        pd.DataFrame (n_bins)       locus axis, index = bin_id: chrom, start, end, [name, resolution]
├── bin_tracks  pd.DataFrame (n_bins)       per-locus signals (bulk ATAC, ChIP, GC, features, compartment score)
├── binm        dict[str, ndarray]           per-locus multi-dim, first axis n_bins
├── intervals   dict[str, IntervalTable]     typed TADs / loops / peaks / segments (domain|pair|peak|segment)
├── coords      np.ndarray (n_spots, 3)     x, y, z coordinates
├── spots       pd.DataFrame (n_spots)      bin_id, trace_id, [cell_id]; chrom/start/end derived from bins
├── spot_tracks pd.DataFrame (n_spots)      per-spot signals (IF intensity, seqFISH z-scores)
├── tracks      (deprecated)                spot-aligned view of bin_tracks + spot_tracks (2.x shim)
├── cells       pd.DataFrame (n_cells)      cell-level metadata (cell_type, position, ...)
├── cellm       dict[str, ndarray]           per-cell multi-dim (embeddings, UMAP, ...)
├── traces      pd.DataFrame (n_traces)     trace-level metadata
├── layers      dict[str, ndarray]           alternative coords, each (n_spots, 3)
├── cell_shapes dict[str, DataFrame]         cell outlines: cell_id + geometry (WKB), GeoParquet on disk (2.3)
├── points      dict[str, DataFrame]         non-genomic 3-D points (RNA spots, IF puncta) in the coords frame
├── results     ResultsStore                 analysis outputs + provenance (ResultRecord)
└── uns         dict                         metadata (genome_assembly, xyz_unit, ...)
```

### Key Design Decisions

- **Locus axis (`bins`, format 2.0)**: one row per locus shared by all cells; `spots.bin_id` → `bins.index`.  `spots["chrom"/"start"/"end"]` are derived from `bins` (kept in memory, not stored on disk; `cd.spots_with_loci()` is the stable accessor; edit loci → `cd.rebuild_bins()`).  Per-locus data go to `bin_tracks` / `binm` / `intervals`, per-spot data to `spot_tracks`.  Subsetting spots keeps all bins.  New code must not use `cd.tracks` (deprecated spot-aligned view) — use `bin_tracks`, `spot_tracks` or `tracks_spot_view()`; `fea`/`strc` feature writers project onto bins (`fea.project_interval_features_to_bins`).
- **No `spotp` (pairwise matrices)**: Distance/contact matrices are per-trace, not global. Use `cd.compute_distances(trace_id=X)` on demand instead of storing O(n²) matrices.
- **Categorical dtypes**: `chrom`, `trace_id`, `cell_id` are auto-converted to `pd.Categorical` for ~10x memory savings on string columns.
- **Linked modalities stay external**: scHi-C contacts (`.scool`) and multi-modal matrices (`.h5mu`) are referenced, not copied — `cd.link_scool()` / `cd.link_mudata()` record paths + cell mapping in `uns`, `cd.link_spatialdata()` (a SpatialData zarr + its table's `region` / `instance_key` ↔ `cell_id` map; `load_linked_spatialdata(cells=)`, `to_spatialdata()`), `cd.validate_links()` checks them.  Never put contacts or cell positions into `coords`.  **Embedded copies** (for an atlas / object storage): `python -m chromdata.embedded STORE` (`chromdata.embedded.embed_links`) copies the linked `.cool` / `.mcool` / `.scool` / `.h5ad` into `embedded/contacts/<key>/` (Zarr, partitioned by chromosome, sharded for range reads) and `embedded/anndata/<key>/`; the link records stay, readers prefer the embedded copy (the web browser incl. section images, `cd.linked_adata`, `cd.linked_cool_path()` / `load_linked_scool()` export a cooler file on demand, `validate_links`), layout in `packages/chromdata/spec.md`.  `cd.write` onto the store the object was read from keeps `embedded/`; a new path / another object does not — embed after writing.  **Remote stores**: `ChromData.read('s3://…/x.chromdata.zarr', backed=True)` / the web browser open a directory store over fsspec (`chromdata/remote.py`; needs `s3fs` / `aiohttp` / `gcsfs`; options via `UCHROM_STORAGE_OPTIONS` JSON) — metadata + small tables at open, range requests afterwards; linked files do not resolve against a URL, so an atlas store carries embedded copies.
- **Cell spatial position (format 2.3)**: centroids are `cells` columns `centroid_x/y[/z]` (`<key>_centroid_*` for other keys) + a record `uns['cell_spatial'][key]` (`unit`, `frame` fov|tissue|global|…, `region_col`, `in_coords_frame`, `status` measured|inferred, `source` — required when inferred, optional `voxel_size`/`voxel_unit`, `shapes`); `cd.set_cell_positions()` / `cd.cell_positions(key, physical=)`.  Outlines: `cd.set_cell_shapes()` → `cd.cell_shapes[key]` (WKB, `uns['cell_shapes'][key]`), `tables/cell_shapes/<key>.parquet` (GeoParquet); shapely / geopandas only for `cell_shapes_geodataframe()` (extra `u-chrom[spatial]`).  Loaders fill it (seqFISH+ clustering CSV, FOF-CT `Cent_ROI_*` / `cell_center_*_global`, FOF-CT mapping-table `ROI_Boundaries`).  `set_cell_spatial_coordinates()` is deprecated (writes the schema; old `spatial_x` / `x_centroid` columns stay readable).  Schema in `packages/chromdata/spec.md`.
- **FOF-CT compatible**: `ChromData.from_fofct(path)` reads the 4DN FISH Omics Format core table. Column mapping: Spot_ID→spot_id, Trace_ID→trace_id, X/Y/Z→coords, Chrom→chrom, Chrom_Start/End→start/end.
- **Typed results with provenance**: `cd.results` is a `ResultsStore` (dict-like; `cd.results[key]` → value, `cd.results.record(key)` → `ResultRecord(kind, value, params, function, uchrom_version, inputs, created_utc)`).  Unwritable values raise `TypeError` at assignment.  Analysis functions store via `cd.results.set(key, value, kind=, function=, params=, inputs=)`.
- **Calling convention** (`uchrom/convention.py`): `fn(cd, *, chrom=None, trace_ids=None, cells=None, params=<*Params>, device="auto", key_added="<what>.<method>", copy=False)`.  `chrom=None` runs every chromosome and merges into one table under one key; `copy=False` returns the table, `copy=True` a new ChromData.  Deprecated 1.x forms (positional `chrom`, `store=`, `result_key=`) must keep working with a `DeprecationWarning` and the 1.x key.  `uchrom.tl` / `uchrom.pp` are flat aliases; implementations stay in the domain modules.
- **Persistence — `.chromdata.zarr` (format 2.3 = the 2.2 layout + optional `tables/cell_shapes/`)**: `cd.write(path)` / `ChromData.read(path)` pick the container from the path.  `*.chromdata.zarr` = Zarr v3 group with Parquet tables (`chromdata/zarrcd.py`; layout in `packages/chromdata/spec.md`); every spot-aligned value is stored **once**: coordinates + keys **partitioned by chromosome** — `tables/coords/chrom=<name>/part-0.parquet` (bin_id, trace_id / cell_id as integer codes, x, y, z), sorted by (cell, trace, bin), 16,384-row groups on cell boundaries; every other spot-aligned column (extra spot columns, `spot_tracks`, `layers`) in **cell-sorted primary tables** `tables/primary/*.parquet` (order cell › trace › chromosome › bin, no key columns, 65,536-row groups on cell boundaries, float columns dictionary-encoded); spot columns that are a function of the bin / cell / trace (probe names, sample ids) once per key in `tables/derived/`.  `index/` holds the primary runs and `index/coords/` the coordinate runs; `index/coords/primary_run` maps (cell, trace, chromosome) runs one to one.  A full read is in primary order; `get_trace` / `get_cell` read one primary slice + their coordinate runs, `get_chrom(columns="coords")` one partition (`get_chrom` with tracks adds a slice of every primary row group).  `get_*` / `iter_*` / `to_memory` / `read` take `columns=` / `tracks=` (`columns="coords"` = xyz + keys).  `iter_traces` / `iter_cells` stream in chromosome › cell › trace order.  Formats 2.0 / 2.1 are still read; older readers cannot read newer stores.  Lossless decimal float encoding (`chromdata.floatcodec`) is opt-in (`float_encoding=`).  Streaming (roadmap step 7): `ChromData.writer(path)` (writes the store the in-memory writer writes), `from_fofct(..., out=)`, `read_seqfish_multiomics(..., out=)`, exact `uchrom.fea.distance_map`, ArcFISH loop / TAD callers with `streaming=True` (default on backed data); `uchrom.settings.memory_budget` bounds their working memory.  Other tables: small tables as Parquet, `cellm` / `binm` / `index/` / result arrays as Zarr arrays, provenance / `uns` / linked records as JSON attrs.  `*.cdz` = the same tree in one uncompressed zip.  **Row order changes on a round trip** (sorted); compare after sorting by a stable key, or read with `original_order=True` (uses `index/source_row`).  `.h5cd` (the HDF5 container of format 1.x / 2.0) is **no longer read or written**: `read` / `write` raise a `ValueError` naming the converter (`python -m uchrom.io.upgrade old.h5cd`); its reader / writer live only in the private `uchrom/io/_h5cd_legacy.py`, used by `upgrade_h5cd` and the format benchmarks (`benchmarks/fig2`) — nothing else may import it.  Writers are atomic (temp dir + rename).
- **Atlas**: a bucket / folder of `.chromdata.zarr` stores (embedded, self-contained) plus `catalog.json` (`chromdata/catalog.py`: `python -m chromdata.catalog build apps/atlas/datasets.json --root example-data`, display text in `apps/atlas/datasets.json` — datasets grouped by `studies` —, counts / modalities read from the stores; the static page `apps/atlas/site` with thumbnails drawn from the stores by `python apps/atlas/build.py figures`, committed in `apps/atlas/site/figures/`).  The web browser lists it in the Open dialog (`--atlas URL`, `UCHROM_ATLAS`, default the public U-Chrom atlas data on Cloudflare R2, `https://uchrom-atlas-r2.u-science.org` — bucket `u-chrom-atlas`; `uchrom-atlas.u-science.org` is kept free for the atlas web page) and opens a card by URL.  Publishing: `aws s3 sync` to the R2 bucket (credentials stay in the user's environment, never in the repo).
- **Backed mode**: `ChromData.read(path, backed=True)` on a zarr / cdz store → `BackedChromData` (`chromdata/backed.py`): small tables eager; `coords` / `layers` (`BackedArray`) and `spots` / `spot_tracks` (`BackedFrame`) read on access; `get_cell` / `get_trace` / `get_chrom` / `cd[rows]` / `iter_traces(batch)` / `iter_cells(batch)` read only the needed row ranges and return in-memory `ChromData`; `to_memory()` loads all.  Spot-aligned data are read-only on a backed object.  `iter_traces` / `iter_cells` exist on in-memory objects too and yield identical chunks.  The web browser opens stores backed.
- **Format versioning**: `uchrom_format_version` (MAJOR.MINOR) and `uchrom_version` as root attrs (zarr.json attributes); zarr stores are checked by `_check_zarr_version`. Same MAJOR + higher MINOR warns but reads; unknown MAJOR raises. The zarr container's version is `ZARR_FORMAT_VERSION` in `zarrcd.py` (2.3; `ZARR_LAYOUT_VERSION` 2.2 is the spot layout it writes; `ZARR_LAYOUTS` maps MINOR → layout). Legacy `.h5cd` files (format 1.x / 2.0, `FORMAT_VERSION` in `uchrom/io/_h5cd_legacy.py`) are converted by `uchrom.io.upgrade_h5cd(src[, dst])` / `python -m uchrom.io.upgrade SRC [DST]` (default target `<stem>.chromdata.zarr`; 1.x: bins from spot loci, spot-aligned tracks split into bin/spot tracks). To bump format: update the relevant constant, add a reader for the new MAJOR (a new MINOR layout: read it next to the old ones, as 2.2 reads 2.1 and 2.0).
- **Validation on construction**: Checks coords shape, spots required columns, tracks alignment, layers shape.
- **Flat storage, hierarchical access**: All spots across all cells stored flat. Use `cd.get_cell(id)` / `cd.get_trace(id)` / `cd.get_chrom(name)` for subsetting, which returns a new ChromData.

### spots Required Columns

| Column | Type | Required | FOF-CT mapping |
|--------|------|----------|----------------|
| bin_id | int → bins.index | yes (derived from chrom/start/end when absent) | — |
| trace_id | int/str (category) | yes | Trace_ID |
| chrom / start / end | derived from bins | give them instead of bin_id | Chrom / Chrom_Start / Chrom_End |
| cell_id | int/str (category) | no | Cell_ID |

### I/O Methods

- `ChromData(coords, spots, ...)` — direct construction (spots with chrom/start/end → bins derived; or `bins=` + `bin_id`)
- `ChromData.from_dataframe(df)` — from reconstruction CSV (chrom, start, end, x, y, z); auto-assigns one trace per chromosome
- `ChromData.from_fofct(path, cell_table=None, rna_table=None)` — from FOF-CT core table; parses `##` headers into `uns`; companion cell table → `cells` (gene counts as `rna.<gene>`), RNA spot table → `points['rna']`
- `cd.to_fofct(path, cell_table=None, rna_table=None)` / `uchrom.io.write_fofct(cd, path, …)` — the inverse: FOF-CT core table with `##`/`#` headers (from `uns['fofct_header']` or `uns`), optional cell and RNA tables; `from_fofct(to_fofct(cd))` round-trips coords, ids, loci, extra columns, cells and RNA spots exactly
- `cd.write('data.chromdata.zarr')` / `ChromData.read('data.chromdata.zarr'[, backed=True, columns=...])` — format 2.3 round trip (`.cdz` = one zip file; `.h5cd` is refused — convert it)
- `cd.to_dataframe()` — export as flat DataFrame (loci derived from bins; `bin_id` left out unless `include_bin_id=True`)
- `uchrom.io.upgrade_h5cd(src[, dst])` / `python -m uchrom.io.upgrade` — convert `.h5cd` 1.x / 2.0 (or an older store) to `.chromdata.zarr` (or `.cdz` by the target suffix)

## Validation discipline — always run on real data

When porting or implementing an algorithm (new method, new module,
re-implementation of a paper):

- **Synthetic tests validate correctness; real data validates the
  port**.  Both are required.  A PR that only runs on synthetic
  data is not done.
- **If a paper names benchmark datasets, get those exact datasets**.
  Reproducing the paper's setup is the bar — not "something similar".
- **If real data isn't trivially downloadable, solve that, don't
  sidestep it**.  Options in order of preference:
  1. Direct public URL (Zenodo / 4DN open S3 / GitHub raw).
  2. Authenticated portal with a documented procedure.
  3. Pre-trim / extract a small slice on disk once, host it somewhere
     stable, document the recipe.
  4. **Only if all else fails**, use synthetic as a *supplement* to
     real data — never as a replacement.  Clearly label what was and
     wasn't validated.
- **Never fabricate inputs to make a pipeline runnable** (e.g.
  synthesising Hi-C from FISH to "demo" GEM-FISH).  If a tutorial
  can't run on real data end-to-end within reasonable time/size,
  the tutorial is wrong — fix the data pipeline or narrow the scope,
  don't swap in a fake.
- **Do not pass off "it compiled / the tests passed" as validation**
  for a reconstruction / alignment / calling algorithm.  Always
  report the real-data metric (distance-matrix correlation,
  trace purity, ploidy recall, etc.) in the commit message / PR
  body.  If the number is disappointing, say so.
- The example-data catalog rule above is the mechanism — every
  dataset used for validation MUST be documented in
  `example-data/README.md` in the same PR.

## Example data

All datasets consumed by tutorials and benchmarks live in
`example-data/`.  Rules:

- **Catalog is authoritative**: `example-data/README.md` lists every
  dataset with size, source / citation, download URL, format, and
  which tutorial consumes it.  A symlink surfaces the same catalog
  in the Sphinx docs at `docs/source/example_data.md`.
- **< 10 MB → check into the repo**.  Add a row to the "Small,
  in-repo datasets" table of `example-data/README.md`.
- **≥ 10 MB → document + auto-download**.  Add a row to "Large
  datasets", an entry to `example-data/download_data.py`, and follow
  the existing `find_*()` pattern inside the tutorial that needs it
  (see e.g. `find_fofct()` in `tutorials/_build_notebooks.py`).  Add
  the filename(s) to `.gitignore`.
- **Whenever a tutorial or benchmark pulls in a new dataset, the
  catalog must be updated in the same PR** — this is a hard rule.
  Do not add silent downloads.
- Tutorial-produced outputs (e.g. `with_loops.chromdata.zarr`, synthetic
  `fofct_core.csv` fallbacks) are gitignored, not committed.

## Technical Notes

- **GPU frameworks**: native Rust/wgpu, Taichi and PyTorch coexist but don't interact.
  - **NucDynamics → native Rust engine** (`packages/uchrom-recon`, `uchrom_recon`):
    CPU in f64 with rayon (models in parallel, force loops split when there
    are fewer models than cores; per-particle gather → results independent
    of the thread count) and GPU through wgpu (WGSL compute shaders: Metal on
    macOS, Vulkan on Linux/NVIDIA; f32; all models of an ensemble batched in
    one dispatch).  `recon.sc.nucdyn` needs it (the Taichi port was removed).
  - **Taichi** is an optional extra (`u-chrom[gem]`) used only by `recon.sc.gem`
    (legacy); new engines of this kind follow the native pattern.
  - **Gradient-descent optimisation on a structured multi-term loss →
    PyTorch** (e.g. `recon.bulk.mds`, `recon.fish.gem_fish` — hundreds to
    thousands of iterations, each one doing dense matrix-level work; the
    autodiff graph, standard optimisers (Adam / L-BFGS), and easy batch
    dim for ensemble models outweigh Taichi's per-iter speed).
  - Legacy: `recon.sc.gem` is Taichi-based.  If it ever needs ensembles
    or more complex loss terms, consider migrating to PyTorch.
  - Native engine changes: `cargo test --release [--features gpu]` in
    `packages/uchrom-recon`, rebuild with `maturin develop --release`; WGSL lives in
    `src/gpu/nucdyn.wgsl` (included at compile time).
- **Python package name**: `uchrom` (import name), `u-chrom` (pip name)
- **Python ≥ 3.11** (zarr ≥ 3, needed by the `.chromdata.zarr` container, has no 3.10 wheels); `zarr` and `pyarrow` are core dependencies.
- **`uchrom/io/` naming**: The internal file is `_io.py` to avoid shadowing Python's stdlib `io` module. Use `gzip.open(path, mode + "t")` instead of `io.TextIOWrapper`.
- **CLI entry points**: All via `python -m` (e.g., `python -m uchrom.recon.sc.nucdyn`, `python -m uchrom.browser`)
- **Browser backend**: PyVista only (VisPy backend was removed)
- **Web browser**: the `uchrom-browser` package (`packages/uchrom-browser/uchrom_browser`: FastAPI server + React/Three.js SPA in `frontend/`, built into `static/` and committed; API in `API.md`).  It depends on `chromdata` only and must never import `uchrom`.  `python -m uchrom_browser` / `uchrom-browser`, or `python -m uchrom.browser --web` with u-chrom (`uchrom.browser.web` / `uchrom.browser.client` are deprecated aliases).  `uchrom/browser/__init__.py` imports Qt lazily so the web path works without PyQt5.  Frontend changes need `npm run build` in `packages/uchrom-browser/uchrom_browser/frontend` and the rebuilt `static/` committed.  Keep `API.md` in sync with `server.py` / `data.py`.
