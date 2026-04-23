# U-Chrom Development Guide

## Project Vision

U-Chrom (Universal Chromatin) is a general-purpose toolkit for chromatin 3D structure data analysis. The name reflects its goal: providing a **universal** framework that works across different data modalities and analysis tasks.

### Core Data Structure

The central data structure is a **structure table** — a DataFrame where each row represents a genomic bin with its 3D coordinates:

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

```
uchrom/
├── io/              Data I/O (.pairs, .cool, .hic, .3dg, .csv, .pdb)
├── recon/           3D reconstruction
│   ├── _base.py     Shared simulation base (Taichi)
│   ├── sc/          Single-cell reconstruction
│   │   ├── nucdyn/  Nuc Dynamics (molecular dynamics, Taichi GPU)
│   │   └── gem/     GEM (energy minimization, Taichi autodiff)
│   ├── bulk/        Bulk reconstruction
│   │   └── mds/     MDS/SMACOF (PyTorch GPU)
│   └── fish/        Sequencing + imaging combined (placeholder)
├── im/              Image processing (placeholder)
├── strc/            Structure identification
│   ├── tad/         TAD detection (directionality index)
│   ├── loop/        Loop detection (placeholder)
│   └── comp/        Compartment detection (placeholder)
├── fea/             Geometric features (placeholder)
├── emb/             Structure embedding (placeholder)
├── pl/              Plotting (placeholder)
├── browser/         Interactive 3D browser (PyVista + PyQt5)
└── op.py            Misc operations (mark empty particles)
```

## ChromData — Core Data Container

`ChromData` (`uchrom.core.ChromData`) is the central data structure, analogous to AnnData for scRNA-seq.

### Hierarchy

Cell → Trace → Spot/Bin

### Attributes

```
ChromData
├── coords      np.ndarray (n_spots, 3)     x, y, z coordinates
├── spots       pd.DataFrame (n_spots)      chrom, start, end, trace_id, [cell_id]
├── cells       pd.DataFrame (n_cells)      cell-level metadata (cell_type, position, ...)
├── cellm       dict[str, ndarray]           per-cell multi-dim (embeddings, UMAP, ...)
├── tracks      pd.DataFrame (n_spots)      epigenomic signals per bin (ATAC, ChIP, ...)
├── traces      pd.DataFrame (n_traces)     trace-level metadata
├── layers      dict[str, ndarray]           alternative coords, each (n_spots, 3)
├── results     dict                         analysis outputs (tads, loops, compartments)
└── uns         dict                         metadata (genome_assembly, xyz_unit, ...)
```

### Key Design Decisions

- **No `spotp` (pairwise matrices)**: Distance/contact matrices are per-trace, not global. Use `cd.compute_distances(trace_id=X)` on demand instead of storing O(n²) matrices.
- **Categorical dtypes**: `chrom`, `trace_id`, `cell_id` are auto-converted to `pd.Categorical` for ~10x memory savings on string columns.
- **FOF-CT compatible**: `ChromData.from_fofct(path)` reads the 4DN FISH Omics Format core table. Column mapping: Spot_ID→spot_id, Trace_ID→trace_id, X/Y/Z→coords, Chrom→chrom, Chrom_Start/End→start/end.
- **HDF5 persistence**: `.h5cd` format via `cd.write(path)` / `ChromData.read(path)`. DataFrames stored as per-column datasets, categorical as byte strings.
- **Format versioning**: root HDF5 attrs `uchrom_format_version` (MAJOR.MINOR) and `uchrom_version`. Read-side dispatches to `_read_vN()`. Same MAJOR + higher MINOR warns but reads; different MAJOR raises. Missing attr → legacy 1.0 with warning. To bump format: update `FORMAT_VERSION` in `cdata.py`, add `_read_vN` function for the new MAJOR.
- **Validation on construction**: Checks coords shape, spots required columns, tracks alignment, layers shape.
- **Flat storage, hierarchical access**: All spots across all cells stored flat. Use `cd.get_cell(id)` / `cd.get_trace(id)` / `cd.get_chrom(name)` for subsetting, which returns a new ChromData.

### spots Required Columns

| Column | Type | Required | FOF-CT mapping |
|--------|------|----------|----------------|
| chrom | str (category) | yes | Chrom |
| start | int | yes | Chrom_Start |
| end | int | yes | Chrom_End |
| trace_id | int/str (category) | yes | Trace_ID |
| cell_id | int/str (category) | no | Cell_ID |

### I/O Methods

- `ChromData(coords, spots, ...)` — direct construction
- `ChromData.from_dataframe(df)` — from reconstruction CSV (chrom, start, end, x, y, z); auto-assigns one trace per chromosome
- `ChromData.from_fofct(path)` — from FOF-CT core table; parses `##` headers into `uns`
- `cd.write('data.h5cd')` / `ChromData.read('data.h5cd')` — HDF5 roundtrip
- `cd.to_dataframe()` — export as flat DataFrame

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
- Tutorial-produced outputs (e.g. `with_loops.h5cd`, synthetic
  `fofct_core.csv` fallbacks) are gitignored, not committed.

## Technical Notes

- **GPU frameworks**: Taichi and PyTorch coexist but don't interact.
  - **MD simulations / tight inner loops with many cheap iterations → Taichi**
    (e.g. `recon.sc.nucdyn` — molecular-dynamics style integration over
    millions of timesteps where per-iteration launch overhead matters).
  - **Gradient-descent optimisation on a structured multi-term loss →
    PyTorch** (e.g. `recon.bulk.mds`, `recon.fish.gem_fish` — hundreds to
    thousands of iterations, each one doing dense matrix-level work; the
    autodiff graph, standard optimisers (Adam / L-BFGS), and easy batch
    dim for ensemble models outweigh Taichi's per-iter speed).
  - Legacy: `recon.sc.gem` is Taichi-based.  If it ever needs ensembles
    or more complex loss terms, consider migrating to PyTorch.
- **Python package name**: `uchrom` (import name), `u-chrom` (pip name)
- **`uchrom/io/` naming**: The internal file is `_io.py` to avoid shadowing Python's stdlib `io` module. Use `gzip.open(path, mode + "t")` instead of `io.TextIOWrapper`.
- **CLI entry points**: All via `python -m` (e.g., `python -m uchrom.recon.sc.nucdyn`, `python -m uchrom.browser`)
- **Browser backend**: PyVista only (VisPy backend was removed)
