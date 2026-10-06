# U-Chrom tutorials

Jupyter notebooks that show each part of U-Chrom at work on real data.  They are committed
**executed** (the documentation renders them as they are) and grouped like the documentation's
chapters.  Every dataset they use is listed in [`example-data/README.md`](../example-data/README.md);
outputs go to `tutorials/_out/` (ignored by git).

| Chapter | Notebook | Shows |
|---------|----------|-------|
| Data model & storage | `chromdata_basics.ipynb` | `ChromData`: bins, spots, tracks, intervals, results, subsetting |
| | `chromdata_stores.ipynb` | the `.chromdata.zarr` store: backed and remote reads, streaming, linked and embedded modalities |
| Importing data | `import_fofct.ipynb` | 4DN FOF-CT tracing with cell and RNA tables, and back |
| | `import_pyhim_ecsv.ipynb` | PyHiM ECSV traces |
| | `import_seqfish_multiomics.ipynb` | DNA seqFISH+ multi-omics (Takei 2025 cerebellum) |
| Imaging | `jie_aligner.ipynb` | spot-to-trace alignment on raw seqFISH+ spots |
| | `fish_imputation.ipynb` | filling missing loci: linear, cubic, SnapFISH-IMPUTE |
| 3-D reconstruction | `reconstruction.ipynb` | single-cell NucDynamics and EMber on the native engine |
| | `bulk_reconstruction.ipynb` | bulk Hi-C: MDS and IGM population models |
| | `gem_fish_reconstruction.ipynb` | Hi-C + FISH (GEM-FISH) |
| Structure calling | `loop_calling.ipynb`, `tad_calling.ipynb`, `fishnet_domains.ipynb`, `compartment.ipynb` | loops, TADs, per-allele domains, compartments from 3-D distances |
| Per-locus features | `features.ipynb` | distance maps, variance features, peaks, interval projections |
| Cells & embeddings | `cell_embeddings.ipynb` | embeddings and clusters from RNA / marks / contacts |
| | `higashi_embedding.ipynb` | FastHigashi on single-cell Hi-C |
| Visualisation | `plotting_and_browser.ipynb` | `uchrom.pl` plots; the web browser from Python |
| Auto-discovery | `takei2025_auto_discovery.ipynb`, `takei2025_iterative_auto_discovery.ipynb` | agents exploring a dataset |

Run a notebook from the repository root (it finds `example-data/` itself):

```bash
jupyter nbconvert --to notebook --execute --inplace tutorials/<name>.ipynb
```
