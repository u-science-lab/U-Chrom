# Chromatin tracing

Multiplexed DNA FISH — ORCA, Hi-M, DNA-MERFISH, chromatin tracing in general — images one locus after
another and gives each locus a position in 3-D.  Its data arrive as a table of spots: one row per
locus of one chromatin fibre, with `x, y, z`.  That is a `ChromData` almost as it stands, so this
chapter is mostly about getting the spots in, linking them into traces and filling the loci a trace
missed; the analyses on the coordinates are common to all data and come after.

| Step | API |
|------|-----|
| read a 4DN FISH Omics Format table (FOF-CT), with its cell and RNA tables; write one | `ChromData.from_fofct(core, cell_table=, rna_table=, out=)`, `cd.to_fofct` |
| read PyHiM traces (ECSV) | `ChromData.from_pyhim_trace` |
| read the tables of Bintu et al. 2018 | `uchrom.io.read_bintu_tracing` |
| link raw detections into traces, with ploidy (the *jie* aligner) | `uchrom.im.trace.align_spots` |
| fill missing loci: linear, cubic spline, SnapFISH-IMPUTE | `uchrom.im.impute.impute_coordinates(cd, method=...)`, `uc.pp.impute` |

## Tutorials

```{toctree}
:maxdepth: 1

/tutorials/import_fofct
/tutorials/import_pyhim_ecsv
/tutorials/jie_aligner
/tutorials/fish_imputation
```

## Guides

```{toctree}
:maxdepth: 1

fofct
alignment
```

## Then

Traces are coordinates, so everything that works on coordinates applies: [structure
calling](../structures/index) from the distances between loci (loops, TADs, domains per allele,
compartments), [per-locus features](../features/index) (distance maps, contact frequencies,
variances), the [web browser](../viz/index).  Imaging and Hi-C of the same cell type meet in
[GEM-FISH](../bulk/index).

API: [uchrom.im](../reference/api/im), [uchrom.io](../reference/api/io).
