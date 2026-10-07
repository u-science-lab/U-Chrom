# Reading seqFISH+ multi-omics data

In a `ChromData` the spots carry coordinates and per-spot signals (`spot_tracks`: the chromatin marks and
nuclear bodies measured at each locus), the cells carry their type, position and expression (`cells`,
`cellm`), and the transcript matrix can stay in its own AnnData, linked by cell.

| Step | API |
|------|-----|
| read the per-FOV spot tables with the locus map and the cell clustering | `uchrom.io.read_seqfish_multiomics(csvs, locus_annotation=, cell_clustering=, out=)` |
| a whole replicate, with the RNA matrix as a linked AnnData | `uchrom.io.load_takei2025_cerebellum()`, `load_seqfish_multiomics_linked` |
| the Takei 2021 tables as FOF-CT (DNA, RNA spots, cells) | `ChromData.from_fofct(core, cell_table=, rna_table=)` ([chromatin tracing](../tracing/index)) |
| cell positions and outlines in the tissue | `cd.cell_positions()`, `cd.set_cell_shapes()` |
| the full Takei 2025 cerebellum without downloading it | `uchrom.datasets.load("takei2025_cerebellum")` (the atlas store) |

## Tutorial

```{toctree}
:maxdepth: 1

/tutorials/import_seqfish_multiomics
```
