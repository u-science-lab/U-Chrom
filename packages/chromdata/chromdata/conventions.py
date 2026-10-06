"""Naming conventions shared by the data model, the analysis library and the browser."""

#: display name of each feature prefix of the per-cell matrices and embeddings (``rna_pca`` -> "RNA"); the browser
#: groups embeddings by it
MODALITY_LABELS = {"rna": "RNA", "if": "Histone/IF", "protein": "Protein", "ab": "Protein",
                   "atac": "ATAC", "hic": "Hi-C", "higashi": "Hi-C"}
