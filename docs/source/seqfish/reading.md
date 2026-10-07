# Imaging multi-omics: DNA seqFISH+

DNA seqFISH+ with sequential immunofluorescence and RNA FISH (Takei et al. 2021, 2025) measures, in the
same nucleus, where thousands of loci are *and* what they carry: dozens of chromatin marks and nuclear
bodies per spot, transcripts per cell, the cell's position in the tissue.  In a `ChromData` the spots
carry coordinates and per-spot signals (`spot_tracks`), the cells carry their type, position and
expression (`cells`, `cellm`), and the transcript matrix can stay in its own AnnData, linked by cell.

| Step | API |
|------|-----|
| read the per-FOV spot tables with the locus map and the cell clustering | `uchrom.io.read_seqfish_multiomics(csvs, locus_annotation=, cell_clustering=, out=)` |
| a whole replicate, with the RNA matrix as a linked AnnData | `uchrom.io.load_takei2025_cerebellum()`, `load_seqfish_multiomics_linked` |
| the Takei 2021 tables as FOF-CT (DNA, RNA spots, cells) | `ChromData.from_fofct(core, cell_table=, rna_table=)` ([chromatin tracing](../tracing/index)) |
| cell positions and outlines in the tissue | `cd.cell_positions()`, `cd.set_cell_shapes()` |
| the full Takei 2025 cerebellum without downloading it | `uchrom.datasets.atlas("takei2025_cerebellum")` |

## Tutorials

```{toctree}
:maxdepth: 1

/tutorials/import_seqfish_multiomics
```

## Then

The spots are coordinates with signals, so the [common analyses](../structures/index) apply as for
chromatin tracing.  Two are specific to the extra layers:

- **Signals along the genome**: peaks of a chromatin mark in the spot signals, signals summed over
  intervals, annotation and sequence content — [per-locus features](../features/index) (its tutorial
  calls H3K4me3 peaks on chromosome 19 of the cerebellum data).
- **Which cells are alike**: cell embeddings from the chromatin marks (per-cell means or the
  mark–mark correlations within a cell) or from RNA — [cells & embeddings](../cells/index).

The [web browser](../viz/index) shows the cells in their tissue, each cell's traces in 3-D coloured by
any mark, and the marks along the genome.

API: [uchrom.io](../reference/api/io).
