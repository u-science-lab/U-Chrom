# Imaging multi-omics: DNA seqFISH+

DNA seqFISH+ with sequential immunofluorescence and RNA FISH (Takei et al. 2021, 2025) measures, in the
same nucleus, where thousands of loci are *and* what they carry: dozens of chromatin marks and nuclear
bodies per spot, transcripts per cell, the cell's position in the tissue.

| Step | Page | API |
|------|------|-----|
| read the per-field spot tables with the locus map and the cell clustering; the RNA as a linked AnnData | [Reading seqFISH+ multi-omics data](reading) | `uchrom.io.read_seqfish_multiomics`, `load_takei2025_cerebellum`, `uchrom.datasets.load` |
| chromatin marks along the genome, cells by their marks, cells in the tissue | [Marks, cells and tissue](marks) | `uchrom.emb.aggregate_tracks` / `embed_cells(source="if")`, `uchrom.fea` peaks, `cd.cell_positions` |

The DNA spots are coordinates, so what applies to chromatin tracing applies here too:
[calling structures](../tracing/structures) from 3-D distances, distance maps
([per-locus features](../features/index)), the [web browser](../viz/index) with the cells in their tissue.

```{toctree}
:maxdepth: 2
:hidden:

reading
marks
```
