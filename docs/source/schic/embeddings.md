# Cell embeddings

With hundreds to thousands of cells, the question becomes which cells are alike.  `uchrom.emb` embeds
cells by their contact maps — FastHigashi's tensor decomposition, or scHiCluster's imputed maps — and by
the other measurements of the same cells (RNA, accessibility), clusters them, scores the clusters against
known cell types and stores everything on the cells axis (`cd.cellm`, with the metadata the web browser uses
to label it in `cd.uns["embeddings"]`).

```python
import uchrom as uc
import uchrom.datasets as ds
import uchrom.emb as emb

cd = ds.load("kim2020_scihic")                          # cells + per-cell contact maps (linked)
uc.tl.embed_higashi(cd, rank=64, seed=0)                # FastHigashi -> cd.cellm["higashi"]
emb.score_embedding(cd, "higashi", "cell_type")         # ARI / NMI of k-means, kNN purity
```

| Task | API |
|------|-----|
| embed cells by their contact maps: FastHigashi | `uc.tl.embed_higashi` / `uchrom.emb.embed_higashi` (extra `emb`) |
| embed cells by their contact maps: scHiCluster | `uc.tl.embed_contacts` / `uchrom.emb.embed_contacts` |
| embed cells from RNA / ATAC / chromatin marks / any matrix (PCA, t-SNE, UMAP) | `uc.tl.embed_cells` / `uchrom.emb.embed_cells`; RNA from the linked AnnData: `add_gene_counts` (highly variable genes) |
| clusters and their markers | `uc.tl.cluster_cells`, `marker_features` |
| how well an embedding separates known types | `score_embedding`, `cluster_agreement`, `knn_purity` |
| plot an embedding, coloured by a type or a value | `plot_embedding` |

The same functions embed imaging cells by their chromatin marks ([DNA seqFISH+](../seqfish/marks)).

## Tutorials

```{toctree}
:maxdepth: 1

/tutorials/higashi_embedding
/tutorials/cell_embeddings
```

API: [uchrom.emb](../reference/api/emb).
