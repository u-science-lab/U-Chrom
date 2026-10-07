# Marks, cells and tissue

What sets seqFISH+ multi-omics apart is the second layer: the signals measured at each DNA spot
(`cd.spot_tracks`: H3K27ac, H3K9me3, LaminB1, nuclear speckles, RNA polymerase II, ...) and the cells'
transcripts and positions.

**Marks along the genome.**  Averaged over the cells (or a cell type), a spot signal becomes a per-locus
track (`cd.bin_tracks`), next to the coordinates; peaks of such a track mark the loci a chromatin mark
enriches — the [per-locus features](../tutorials/features) tutorial calls H3K4me3 peaks on chromosome 19 of
the Takei 2025 cerebellum (`ds.load("takei2025_cerebellum")`, the atlas store) and compares them with gene
annotation and sequence content.

**Cells by their marks.**  `uchrom.emb.aggregate_tracks` sums the spot signals of each cell (means, or
the within-cell correlations between marks), and `embed_cells(source="if")` embeds and clusters the cells
by them, as RNA would be — the IF section of the [cell embeddings](../tutorials/cell_embeddings) tutorial
does it for the 1,799 cerebellar cells:

```python
import uchrom as uc
import uchrom.datasets as ds
import uchrom.emb as emb

cd = ds.load("takei2025_cerebellum")
emb.aggregate_tracks(cd, prefix="if", stat="mean")    # cells["if.<mark>"]
uc.tl.embed_cells(cd, source="if")                    # cellm["if_pca" / "if_tsne" / "if_umap"]
emb.score_embedding(cd, "if_pca", "cell_type")        # against the published cell types
```

**Cells in the tissue.**  The loaders record each cell's centroid (and outline when published) as cell
positions (`cd.cell_positions()`, `cd.cell_shapes`); the web browser shows the cells in their tissue,
coloured by type, by an embedding or by any mark, next to each cell's traces in 3-D.

API: [uchrom.emb](../reference/api/emb), [uchrom.fea](../reference/api/fea).
