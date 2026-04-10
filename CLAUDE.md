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

## Technical Notes

- **GPU frameworks**: Taichi (sc reconstruction), PyTorch (bulk MDS). They coexist but don't interact.
- **Python package name**: `uchrom` (import name), `u-chrom` (pip name)
- **`uchrom/io/` naming**: The internal file is `_io.py` to avoid shadowing Python's stdlib `io` module. Use `gzip.open(path, mode + "t")` instead of `io.TextIOWrapper`.
- **CLI entry points**: All via `python -m` (e.g., `python -m uchrom.recon.sc.nucdyn`, `python -m uchrom.browser`)
- **Browser backend**: PyVista only (VisPy backend was removed)
