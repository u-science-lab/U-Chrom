uchrom.emb
==========

Cells by their measurements: embeddings and clusters from contact maps (FastHigashi, scHiCluster), from RNA,
accessibility, chromatin marks or any per-cell matrix, and how well an embedding separates known types.

.. automodule:: uchrom.emb.cells
   :members: embed_cells, cluster_cells, marker_features, normalize_counts, tfidf_lsi, aggregate_tracks, MODALITY_LABELS

.. automodule:: uchrom.emb.higashi
   :members: embed_higashi, run, align_embedding

.. automodule:: uchrom.emb.hic
   :members: embed_contacts, scool_cell_features, schicluster_features, schicluster_impute

.. automodule:: uchrom.emb.genes
   :members: highly_variable_genes, add_gene_counts

.. automodule:: uchrom.emb.metrics
   :members: score_embedding, cluster_agreement, knn_purity

.. automodule:: uchrom.emb.plot
   :members: plot_embedding
