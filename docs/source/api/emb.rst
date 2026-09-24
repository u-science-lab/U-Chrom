uchrom.emb
==========

Cell embeddings: from per-cell features of any modality (``embed_cells``
with count / z-score / TF-IDF-LSI normalisation, ``aggregate_tracks`` for
per-spot imaging signals), from single-cell contact maps (scHiCluster,
``uchrom.emb.hic``) and from single-cell Hi-C with Higashi (``higashi``).

.. automodule:: uchrom.emb.cells
   :members: embed_cells, normalize_counts, tfidf_lsi, aggregate_tracks, MODALITY_LABELS

.. automodule:: uchrom.emb.hic
   :members: scool_cell_features, schicluster_features, schicluster_impute

.. automodule:: uchrom.emb.higashi
   :members: run, align_embedding
