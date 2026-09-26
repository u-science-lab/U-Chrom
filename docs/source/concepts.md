# Concepts

## The structure table

The central abstraction in U-Chrom is the **structure table**: a flat
mapping from genomic bins to 3D coordinates.

| chrom | start | end | x | y | z |
|-------|-------|-----|---|---|---|
| chr1 | 0 | 100_000 | 0.34 | 1.20 | -0.55 |
| chr1 | 100_000 | 200_000 | 0.38 | 1.15 | -0.52 |
| … | … | … | … | … | … |

This is what **both** reconstruction output (Hi-C → 3D) **and** imaging
output (chromatin tracing → 3D) produce.  Every analysis module in
U-Chrom consumes this format.

## Hierarchy: Cell → Trace → Spot

A single row in the structure table is a **Spot** — one 3D observation
of one genomic bin.  Spots are organised hierarchically:

- **Spot** — one observation of one bin in one trace.
- **Trace** — an ordered polymer of spots along a chromatin fibre.  One
  allele's copy of the locus is one trace.  In chromatin tracing, a
  diploid cell can give two traces per chromosome (maternal + paternal).
- **Cell** — a physical cell containing one or more traces.

For **reconstructed** data this hierarchy is thin: each chromosome is
typically a single trace, and the whole output is one cell.

For **imaging** data it matters: a single FOF-CT file may have hundreds
of traces on the same chromosome, each coming from a different cell
(and without explicit cell segmentation, individual traces do **not**
necessarily belong to different cells — they just represent separate
allele observations).

## `ChromData` — the container

[`uchrom.ChromData`](api/core) holds the structure table plus hierarchical
metadata and analysis results:

```
ChromData
├── coords      (n_spots, 3)             x, y, z coordinates
├── spots       DataFrame (n_spots)      chrom, start, end, trace_id, [cell_id]
├── cells       DataFrame (n_cells)      cell-level metadata
├── cellm       dict[str, ndarray]        per-cell embeddings etc.
├── tracks      DataFrame (n_spots)      per-bin epigenomic signals (ATAC, ChIP)
├── traces      DataFrame (n_traces)     trace-level metadata
├── layers      dict[str, (n_spots, 3)]  alternative coordinate sets
├── results     dict                      analysis outputs (loops, tads, ...)
└── uns         dict                      genome_assembly, xyz_unit, ...
```

Key design choices are documented in
[User guide — ChromData](guide/chromdata).

## Data flow

```
┌──────────────────────────────────┐
│  Hi-C / Dip-C  (.pairs, .cool)   │
└──────────────────────────────────┘
                │
                ▼ uchrom.recon.{sc,bulk}
┌──────────────────────────────────┐
│   3D coordinates (ChromData)     │──┐
└──────────────────────────────────┘  │
                                      │
┌──────────────────────────────────┐  │
│  Imaging  (FOF-CT .csv)          │──┼──▶ ChromData
└──────────────────────────────────┘  │
                │                     │
                ▼ uchrom.im (WIP)     │
┌──────────────────────────────────┐  │
│   3D coordinates (ChromData)     │──┘
└──────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────┐
│  Downstream analysis             │
│  - uchrom.strc.loop              │
│  - uchrom.strc.tad               │
│  - uchrom.strc.comp  (WIP)       │
│  - uchrom.fea                    │
│  - uchrom.emb  (WIP)             │
│  - uchrom.pl                     │
│  - uchrom.browser                │
└──────────────────────────────────┘
```

## On-disk format: `.chromdata.zarr`

Format 2.0 is a Zarr v3 directory whose tables are Parquet files (the
SpatialData approach); `<name>.cdz` is the same store as one zip file:

```
data.chromdata.zarr/
├── zarr.json              @uchrom_format_version = "2.0", @uchrom_version
├── tables/                spots.parquet (sorted by cell, trace, bin; x, y, z),
│                          spot_tracks.parquet, layers/, bins, bin_tracks,
│                          cells, traces, intervals/, points/, categories/
├── index/                 row offsets per trace / cell, chromosome per trace
├── cellm/, binm/          zarr arrays
├── results/               values + provenance attrs
├── uns/                   JSON attrs (+ arrays)
└── contacts/, links/      linked .cool / .scool / .h5ad / .h5mu records
```

The index makes a cell, trace or chromosome a few contiguous row ranges,
so `ChromData.read(path, backed=True)` can open large data sets without
loading them.  `.h5cd` (HDF5) files — format 1.x and 2.0 — are still read;
`python -m uchrom.io.upgrade` converts them.

Format version follows `MAJOR.MINOR`:

- same MAJOR, higher MINOR → reader warns and proceeds (unknown fields
  are ignored);
- different MAJOR → reader raises, with a clear upgrade path;
- missing attribute → reader warns and assumes legacy 1.0 layout.

See [`uchrom/core/spec.md`](https://github.com/Nanguage/U-Chrom/blob/main/uchrom/core/spec.md)
for the complete on-disk spec.
