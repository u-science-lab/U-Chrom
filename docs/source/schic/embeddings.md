# Cells & embeddings

With hundreds to thousands of cells, the question becomes which cells are alike.  `uchrom.emb`
embeds cells from any per-cell matrix — RNA counts, chromatin marks (IF), accessibility (ATAC),
contact maps — clusters them, finds marker features, and stores the result in `cd.cellm` with the
metadata the web browser uses to label it.

| Task | API |
|------|-----|
| embed cells from RNA / IF / ATAC / any matrix (PCA, t-SNE, UMAP) | `uchrom.emb.embed_cells`, `normalize_counts`, `tfidf_lsi` |
| cell features from contact maps | `scool_cell_features`, `schicluster_features` |
| clusters and their markers | `cluster_cells`, `marker_features` |
| per-cell averages of spot / bin signals | `aggregate_tracks` |
| Higashi / FastHigashi embeddings of single-cell Hi-C | `uchrom.emb.higashi` (extra `emb`) |

## Tutorials

```{toctree}
:maxdepth: 1

/tutorials/cell_embeddings
/tutorials/higashi_embedding
```

API: [uchrom.emb](../reference/api/emb).
