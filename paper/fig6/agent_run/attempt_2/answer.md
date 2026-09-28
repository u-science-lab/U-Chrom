Your 8 selected cells are **exactly the Bergmann glia in this field of view**. That's every Bergmann cell and all of Leiden cluster 2. The other 39 cells are 22 Granule, 9 Other, 3 MLI1, 3 Purkinje and 2 MLI2+PLI.

**What sets them apart** (each cell counts once; Mann–Whitney test, corrected for testing 51 fields):

| | Selected (n=8) | Other cells (n=39) | Effect (r) | p | Adjusted p |
|---|---|---|---|---|---|
| **SOX2 immunofluorescence** | 0.215 | 0.041 | +0.83 | 5×10⁻⁵ | **0.002** |
| H3K27ac | 0.319 | 0.205 | +0.64 | 0.003 | 0.09 |
| H3K4me3, H3K4me2, Pol II Ser5-P, H3K9ac, H4K8ac, BRG1 | all higher | | +0.50 to +0.57 | 0.01–0.03 | 0.12–0.14 |
| Chromatin Rg (median per cell) | 1.42 | 1.26 (×1.13) | +0.44 | 0.055 | – |
| Nuclear volume | 297 µm³ | 226 µm³ | | 0.28 | – |

- **SOX2 is the only difference that holds up** after correcting for multiple tests. That fits Bergmann glia, which express SOX2. It isn't a clean split, though: 6 of the other cells, mostly "Other", overlap the lowest selected cell.
- **Active-chromatin marks are all shifted upward** (acetylation, H3K4 methylation, initiating Pol II), but no single mark survives the correction. Treat this as a trend.
- **The chromatin looks somewhat less compact** (Rg and end-to-end span both about 13–18% larger), but this isn't significant. Rg also tracks nuclear volume closely across cells (ρ = 0.75), and the selected nuclei are a bit larger, so this may just reflect nuclear size.
- **Caveats:** there are only 8 cells, all from one batch and one field of view, so there's no replicate. The chromatin statistics are based on 245 vs 1,255 traces, but the tests treat each cell as one sample.

**In your browser:** your existing panes P1 and P2 are unchanged, and your selection is still focused. I made these changes:
- **P4:** scatter of SOX2 against H3K27ac. The selected cells sit in the high-SOX2 corner.
- **P5:** Rg distribution for the selection vs the other cells, with medians 1.47 vs 1.29 over traces.
- I recoloured all cells by `cell_type`.
- I saved the other 39 cells as a group called "other 39 cells".

I also opened a SOX2 histogram, but it pooled both groups into one, so I closed it.
