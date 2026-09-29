**Your 8 cells are the Bergmann glia.** Every one is labelled `cell_type = Bergmann`, and together they make up all of Leiden cluster 2, with no other cells mixed in. This field of view has 47 cells in total. The rest are 22 Granule, 9 Other, 3 MLI1, 3 Purkinje and 2 MLI2+PLI.

**How they differ from the other 39 cells** (one value per cell, Mann–Whitney test, rank-biserial r as effect size):

| Feature | Selected cells (median) | Other cells (median) | r | p |
|---|---|---|---|---|
| **SOX2 (IF)** | 0.215 | 0.041 | +0.83 | 5×10⁻⁵ (still significant after correcting for testing ~55 fields, q = 0.002) |
| H3K27ac | 0.32 | 0.21 | +0.64 | 0.003 (q ≈ 0.09) |
| H3K4me3, H3K4me2, RNAPII Ser5-P, H3K27me2, BRG1, H3K9ac, H4K8ac | all higher | | +0.5 to +0.57 | 0.01–0.03 (not significant after correction) |
| y position | 1046 | 1303 | −0.55 | 0.013 (they sit together in one band of the tissue) |
| Chromatin radius of gyration | 1.42 | 1.26 (ratio 1.13) | +0.44 | 0.055 |
| Nuclear volume | 297 µm³ | 226 µm³ | +0.25 | 0.28 |

- **SOX2 is the only robust difference.** That's expected, because SOX2 is a known Bergmann glia marker. It confirms the label rather than revealing something new.
- **The active histone marks and RNA Pol II lean higher,** but none of them survive correction for testing many fields.
- **The chromatin looks slightly less compact, but I wouldn't trust it.** The radius-of-gyration difference is borderline (p = 0.055), and radius of gyration tracks nuclear volume strongly across cells (ρ = 0.75). The difference may just reflect nucleus size.

**Caveats:**
- Everything comes from one field of view in one batch, so there is no replicate.
- There are only 8 vs 39 cells, so treat these results as exploratory.

**What I changed in the browser:**
- **P5:** a new Stats view of radius of gyration, comparing your selection with the other 39 cells. To make it, I registered those 39 cells as a group called "other 39 cells". The medians it shows (1.47 vs 1.29) are over individual traces rather than per cell, so they're a bit higher than the per-cell numbers in the table.
- **P4:** a new IF-UMAP embedding of all cells, coloured by SOX2.
- **Colouring:** I set colouring to `if.SOX2`, which applies to every view, so P1 and P2 are now coloured that way too.
- I didn't move or close P1 or P2, and your selection is still focused. The only view I closed was one I had just opened, which compared your cells against Granule cells only.
