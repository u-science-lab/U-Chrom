The 8 cells you selected are **every Bergmann glia cell in this field of view**, and none of the other 39 cells. They also make up the whole of leiden cluster 2. Compared with the other 39, they differ mainly in **SOX2**, and they carry somewhat more active-chromatin marks.

| Field | Your 8 (median) | Other 39 (median) | p (Mann–Whitney) | FDR q |
|---|---|---|---|---|
| **if.SOX2** | 0.215 | 0.041 | 4.7e-5 | **0.002** |
| if.H3K27ac | 0.319 | 0.205 | 0.003 | 0.09 |
| if.H3K4me3 | 0.311 | 0.209 | 0.010 | 0.12 |
| if.RNAPIISer5-P | 0.292 | 0.215 | 0.012 | 0.12 |
| if.H3K4me2 | 0.315 | 0.243 | 0.012 | 0.12 |
| y_centroid | 1046 | 1303 | 0.013 | 0.12 |

- **SOX2 is the only difference that holds up** after correcting for testing about 54 fields. That fits: SOX2 is a known marker of Bergmann glia.
- **Active marks trend higher.** H3K27ac, H3K4me2/3, the RNA Pol II Ser5-P mark (a sign of active transcription), BRG1 and H3K9ac all trend higher, but none passes correction with only 8 cells.
- **Position:** the cells sit lower in y (median about 1046 vs 1303), which is consistent with where Bergmann glia lie in the tissue layers.
- **No meaningful difference** in nuclear volume (p=0.28) or in the heterochromatin marks H3K9me3, H3K27me3 and HP1α.
- **Caveat:** since your selection is exactly one cell type, this is really a "Bergmann glia vs everything else" comparison, not a finding about a sub-population. I only compared per-cell fields; I didn't compute any 3D chromatin statistics such as radius of gyration.

**What changed in your browser:**
- I saved your selection as the group **`selected_8`** and the remaining cells as **`other_39`**, and your selection is still the focus.
- **P3** is a histogram of SOX2.
- **P4** is a scatter plot of SOX2 against H3K27ac. The 8 red points in the upper right are your cells.
- Cells are now coloured by `cell_type`, which affects P1 and P2 as well. Your existing views weren't moved or closed.

The histogram in P3 draws all cells in a single colour even though I asked it to compare the two groups, so it doesn't show the split. P4 is the view that shows the separation.
