# apps/atlas/benchmarks/results

| File | What | Run |
|---|---|---|
| `hic_embeddings.json` | The Hi-C embeddings of the atlas recomputed with the scHiCluster features of uchrom b6d8873 (identical to schicluster 1.3.2, PR #130) by `../hic_embeddings.py` (the recipes' calls: `scool_cell_features` on the per-cell 1-Mb .scool, then `embed_cells(source="hic")` with their PCs and methods), scored as `validate.py` scores them (k-nearest-neighbour agreement with the cell type, k = 15, or the sample, k = 3); `agreement_old` recomputed from the stores' own embeddings (2026-10-05). `{"description", "provenance", "results"}` | 2026-10-15, tag-308 (CPU, 24 cores), 3.2 h |

## Result

Every agreement is higher with the corrected features (old -> new):

| Dataset | Label (k), cells | PCA | UMAP | t-SNE |
|---|---|---|---|---|
| hires_brain | cell type (15), 399 | 0.521 -> 0.555 | 0.491 -> 0.573 | |
| hires_embryo | cell type (15), 7,469 | 0.257 -> 0.315 | 0.227 -> 0.267 | |
| dschic_aging_cortex | cell type (15), 32,777 | 0.794 -> 0.872 | 0.750 -> 0.859 | |
| gageseq_mouse_cortex | cell type (15), 3,296 | 0.291 -> 0.327 | 0.293 -> 0.338 | |
| gageseq_human_bm_cd34 | cell type (15), 1,445 | 0.279 -> 0.292 | 0.284 -> 0.299 | |
| droplet_hic_mouse_cortex | cell type (15), 6,235 | 0.219 -> 0.258 | 0.209 -> 0.243 | |
| paired_hic_mouse_cortex | cell type (15), 24,284 | 0.164 -> 0.182 | 0.139 -> 0.147 | |
| schicar_mouse_cortex | cell type (15), 5,313 | 0.249 -> 0.295 | 0.250 -> 0.292 | 0.258 -> 0.307 |
| unic_human | sample (3), 23 | 0.696 -> 0.957 | | |
| unic_mouse | sample (3), 20 | 0.650 -> 0.867 | | |

The atlas stores still hold the old embeddings (`cellm`); rebuilding them is a separate step.
