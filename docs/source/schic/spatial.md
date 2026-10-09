# Spatial variation across a tissue

Spatial Hi-C measures contacts spot by spot over a tissue section, and chromatin tracing in tissue places every
traced nucleus.  Both raise the same question about each 3-D genome feature: does it vary in space, and does it
vary beyond what the cells there are?  `uchrom.spatial` answers it for any per-cell or per-spot value.  The
values can be global features of a spot's contacts, compartment scores, the insulation of a known boundary or the
strength of a known loop.

| Step | API |
|------|-----|
| global features of every spot: the contact-distance histogram (scHiCluster's bins) and trans contacts per chromosome, one pass over the library's pairs | `uchrom.io.ContactStats` → `cd.cellm["contacts.distance"]` |
| short / long-range ratio (Guo et al. 2026's definition), distance bands, contact-decay slopes, cis fraction, trans share per chromosome | `uchrom.fea.contact_features` |
| known boundaries and loops scored in every spot: contacts in their windows (flanks / crossing square, peak / donut), insulation against domain interiors | `uchrom.io.WindowCounts`, `boundary_windows`, `loop_windows`, `uchrom.fea.window_scores` |
| compartment values of every spot | `uc.tl.single_cell_compartments` ([structures from single cells](structures.md)) |
| barcode stripes of microfluidic arrays (DBiT-type: one channel per array row and column) removed, the smooth pattern kept | `uchrom.spatial.destripe`, `smooth_share` |
| neighbours in tissue (per section / field of view), spatial autocorrelation (Moran's I, Geary's C; normality, randomisation, permutations) | `uchrom.spatial.spatial_neighbors`, `spatial_autocorr` |
| tests of spatial variation, adjusted for covariates (depth, the spot's transcriptome, cell-type composition) | `uchrom.spatial.sparkx`, `spatially_variable` |
| cells in tissue coloured by a value; export with positions for scanpy / squidpy | `uchrom.pl.plot_spatial`; `cd.to_anndata()` (`obsm["spatial"]`) |

## The tests

`spatially_variable(cd, features, covariates=...)` tests every feature section by section.  Its default test is
SPARK-X (Zhu, Sun & Zhou 2021).  SPARK-X is a covariance test against eleven coordinate kernels, with the kernel
p-values combined by the Cauchy combination and adjusted over features by Benjamini–Yekutieli.  Its null
distribution here is the exact chi-square mixture.  `method="moran"` uses Moran's I over the neighbour graph
instead.

Testing a feature with the cells' identity as covariates asks the second question, what varies beyond the cells.
The identity can be the spot's RNA principal components, a deconvolved composition or the cell type.  An
adjustment by noisy covariates is never complete: a spot's RNA is shallow.  So compare what is left of a feature
with what the same adjustment leaves of genes held out of it.
`benchmarks/spatial_variable` (stage `calibrate`) measures this as the share of the smooth spatial variance that
remains.

## Checks

- **Against the reference implementations, on real data.**  The data are the spot RNA of Guo et al. 2026, mouse
  brain section r1: 6,275 spots and 9,342 genes.
  - SPARK-X against `SPARK::sparkx` (R, xzhoulab/SPARK @a8b4bf2): the combined p-values agree within 8.4e-5,
    within the accuracy of the package's Davies integration.  The Spearman correlation is 0.99999, and the
    adjusted calls are identical (9,336 of 9,342 genes).
  - Moran's I and Geary's C against PySAL `esda` 2.10, for 1,000 genes: the statistics, expectations and
    variances agree within 1e-13.
- **Per-spot contact statistics.**  On both mouse brain sections (12,474 spots, 7.3 × 10⁹ cis contacts), the
  cis and trans counts equal those of the per-spot maps of the atlas spot for spot.
- **The short / long-range ratio.**  It reproduces the paper's regional pattern in both sections: cortex, CA and
  DG lie above white matter and the choroid plexus.  The medians are 3.17 vs 2.48 (r1) and 3.13 vs 2.56 (r2),
  with an AUC of 0.89 and 0.86.

The analysis and its numbers are kept with their provenance in `benchmarks/spatial_variable/results/`.

API: [uchrom.spatial](../reference/api/spatial), [uchrom.fea](../reference/api/fea),
[uchrom.io](../reference/api/io).
