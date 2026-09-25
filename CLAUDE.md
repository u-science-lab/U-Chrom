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
├── core/            ChromData container (cdata.py) + format spec (spec.md)
├── io/              Data I/O (.pairs, .cool, .hic, .3dg, .csv, .pdb, seqFISH multi-omics)
├── recon/           3D reconstruction
│   ├── _base.py     Shared simulation base (Taichi)
│   ├── sc/          Single-cell reconstruction
│   │   ├── nucdyn/  Nuc Dynamics (molecular dynamics, Taichi GPU)
│   │   └── gem/     GEM (energy minimization, Taichi autodiff)
│   ├── bulk/        Bulk reconstruction
│   │   └── mds/     MDS/SMACOF (PyTorch GPU; partitioned + inter-chrom)
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
├── browser/         Interactive 3D browser: desktop (PyVista + PyQt5) and
│   └── web/         web (FastAPI server + React/Three.js SPA in frontend/,
│                    built into static/ and committed; API in API.md)
└── op.py            Misc operations (mark empty particles)

discovery/           Separate package `uchrom-discovery` (import uchrom_discovery):
                     LLM-driven multi-omics auto-discovery — h5cd schema → ideas →
                     notebooks → verification → evidence; iterative idea graph,
                     pre-discovery enrichment, Pantheon / Claude / Codex CLI
                     backends, graph UI.  Own pyproject and tests/.
```

- **Dependency direction is one-way**: `uchrom_discovery` may import the
  public `uchrom` API; `uchrom` must never import `uchrom_discovery`
  (except the deprecated `uchrom.auto_discovery` shim and the deprecated
  `ChromData.*discovery*` delegators, both slated for removal).  Reusable
  feature computation belongs in `uchrom.fea` / `uchrom.strc`, not in
  discovery.
- Run the two test suites separately (both have a `tests` package):
  `pytest tests` from the root, `cd discovery && pytest tests`.

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
├── points      dict[str, DataFrame]         non-genomic 3-D points (RNA spots, IF puncta) in the coords frame
├── results     dict                         analysis outputs (tads, loops, compartments)
└── uns         dict                         metadata (genome_assembly, xyz_unit, ...)
```

### Key Design Decisions

- **No `spotp` (pairwise matrices)**: Distance/contact matrices are per-trace, not global. Use `cd.compute_distances(trace_id=X)` on demand instead of storing O(n²) matrices.
- **Categorical dtypes**: `chrom`, `trace_id`, `cell_id` are auto-converted to `pd.Categorical` for ~10x memory savings on string columns.
- **Linked modalities stay external**: scHi-C contacts (`.scool`) and multi-modal matrices (`.h5mu`) are referenced, not copied — `cd.link_scool()` / `cd.link_mudata()` record paths + cell mapping in `uns`, `cd.validate_links()` checks them, `cd.set_cell_spatial_coordinates()` stores cell-level (possibly inferred) positions in `cells`.  Never put contacts or inferred positions into `coords`.
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
- `ChromData.from_fofct(path, cell_table=None, rna_table=None)` — from FOF-CT core table; parses `##` headers into `uns`; companion cell table → `cells` (gene counts as `rna.<gene>`), RNA spot table → `points['rna']`
- `cd.write('data.h5cd')` / `ChromData.read('data.h5cd')` — HDF5 roundtrip
- `cd.to_dataframe()` — export as flat DataFrame

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
- **Web browser**: `python -m uchrom.browser --web`.  `uchrom/browser/__init__.py` imports Qt lazily so the web path works without PyQt5.  Frontend changes need `npm run build` in `uchrom/browser/web/frontend` and the rebuilt `static/` committed.  Keep `API.md` in sync with `server.py` / `data.py`.
