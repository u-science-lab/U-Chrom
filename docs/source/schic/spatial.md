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
| known boundaries and loops scored in every spot: contacts in their windows (flanks / crossing square, peak / donut), insulation against domain interiors, and against the spot's own expected from its contact-distance histograms | `uchrom.io.WindowCounts`, `boundary_windows`, `loop_windows`, `uchrom.fea.window_expected`, `window_scores` |
| compartment values of every spot | `uc.tl.single_cell_compartments` ([structures from single cells](structures.md)) |
| barcode stripes of microfluidic arrays (DBiT-type: one channel per array row and column) removed, the smooth pattern kept | `uchrom.spatial.destripe`, `smooth_share` |
| neighbours in tissue (per section / field of view), spatial autocorrelation (Moran's I, Geary's C; normality, randomisation, permutations) | `uchrom.spatial.spatial_neighbors`, `spatial_autocorr` |
| tests of spatial variation, adjusted for covariates (depth, the spot's transcriptome, cell-type composition) | `uchrom.spatial.sparkx`, `spatially_variable` |
| cells in tissue coloured by a value; export with positions for scanpy / squidpy | `uchrom.pl.plot_spatial`; `cd.to_anndata()` (`obsm["spatial"]`) |

## Tutorial

```{toctree}
:maxdepth: 1

/tutorials/spatial_variable
```

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

A single boundary or loop has a few contacts per spot.  Score it against the spot's own expected
(`window_scores(counts, expected=window_expected(counts, stats, chromsizes=...))`), not by a log ratio of its
windows alone.  The log ratio also follows the spot's contact decay and, at a few contacts, its coverage of the
chromosome.  Both vary across a tissue, alike for every structure of a chromosome or every loop of a size, so the
log ratios of many structures vary together and their spatial patterns replicate between sections.  In the Guo et
al. 2026 sections this put chromosome X boundaries (X is haploid in these male tissues) and short loops at the top
of the list.

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

## On the reference sections

The share of a feature's smooth spatial variance left after depth and the spot's RNA (30 principal components),
destriped, in the two sections of each tissue:

- **Mouse brain.**  The contact features keep 7-15 % (the 100 kb-1 Mb decay slope 43 and 55 %).  Held-out genes with a spatial pattern keep 25-28 %
  through the same adjustment.  The features vary across the section as its cells do.
- **Human melanoma.**  The features keep 62-82 % (the cis fraction 29 and 35 %).  The spot RNA is shallower here, and few held-out genes have
  a spatial pattern (1 and 4 genes with more than 20 % of their variance smooth); those keep 41-42 %.  The spots' shares
  of contacts per chromosome, a copy-number profile, form patches in the tissue: 71-89 % of their variance is
  smooth for chromosomes 22, 9, 15, 7, 17 and 11.  With five principal components of those profiles as
  covariates, the short / long ratio keeps 36 % and 43 % instead of 69 % and 66 %.  So the 3-D variation that the
  transcriptome does not explain largely follows the tumour's clones.  The same covariates change nothing in the
  brain.
- **The melanoma's copy-number patch.**  Where the spots' copy-number profile changes (the top fifth of its
  second component, 1,208 of 6,036 spots of section r1), the short / long ratio is higher (median 2.01 vs 1.93) --
  on every one of the 23 chromosomes computed on its own, also on the 10 whose copy number does not change (median
  +0.055 log2), unrelated to each chromosome's gain or loss (Spearman -0.05); section r2: 20 of 23.  Its
  compartments are those of the rest (mean scA/B, Pearson r = 0.998).  The patch folds differently genome-wide;
  its copy number marks it.  `uchrom.fea.ContactFeatureParams(per_chromosome=True)` gives features that gains and
  losses of whole chromosomes leave unchanged; the web browser draws a group's map as its log2 ratio to all cells.
- **Single boundaries and loops.**  Scored against each spot's expected, no boundary or loop in either tissue
  varies beyond shuffled spots in a way that repeats in the other section.  The Spearman correlation of their
  excess smooth shares between the sections is -0.01 to 0.03 (as log ratios 0.04-0.74, ordered by chromosome X
  and loop span).  Pooled over all boundaries or loops, a spot's insulation and loop strength do vary: after RNA
  and copy number, 8-16 % of their variance is smooth, against 4-5 % with the spots shuffled.

The analysis and its numbers are kept with their provenance in `benchmarks/spatial_variable/results/`.

API: [uchrom.spatial](../reference/api/spatial), [uchrom.fea](../reference/api/fea),
[uchrom.io](../reference/api/io).
