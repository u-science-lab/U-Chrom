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

## Technical Notes

- **GPU frameworks**: Taichi (sc reconstruction), PyTorch (bulk MDS). They coexist but don't interact.
- **Python package name**: `uchrom` (import name), `u-chrom` (pip name)
- **`uchrom/io/` naming**: The internal file is `_io.py` to avoid shadowing Python's stdlib `io` module. Use `gzip.open(path, mode + "t")` instead of `io.TextIOWrapper`.
- **CLI entry points**: All via `python -m` (e.g., `python -m uchrom.recon.sc.nucdyn`, `python -m uchrom.browser`)
- **Browser backend**: PyVista only (VisPy backend was removed)
