# U-Chrom tutorials

Jupyter notebooks that show each part of U-Chrom at work on real data.  They are committed
**executed** (the documentation renders them as they are) and grouped like the documentation's
chapters.  Their data come from the public atlas (`uchrom.datasets.atlas`) or from the original
sources (`uchrom.datasets.fetch`, cached in `$UCHROM_DATA`, else `~/.cache/uchrom`); outputs go to
`tutorials/_out/` (ignored by git).

| Chapter | Notebook | Shows |
|---------|----------|-------|
| *By data type* | | |
| Chromatin tracing | `import_fofct.ipynb` | 4DN FOF-CT tracing with cell and RNA tables, and back |
| | `import_pyhim_ecsv.ipynb` | PyHiM ECSV traces |
| | `jie_aligner.ipynb` | spot-to-trace alignment on raw seqFISH+ spots |
| | `fish_imputation.ipynb` | filling missing loci: linear, cubic, SnapFISH-IMPUTE |
| Imaging multi-omics (DNA seqFISH+) | `import_seqfish_multiomics.ipynb` | DNA seqFISH+ with chromatin marks and RNA (Takei 2025 cerebellum) |
| Single-cell and spatial Hi-C | `reconstruction.ipynb` | single-cell NucDynamics and EMber on the native engine |
| | `higashi_embedding.ipynb` | FastHigashi on single-cell Hi-C |
| Bulk Hi-C | `bulk_reconstruction.ipynb` | MDS and IGM population models |
| | `gem_fish_reconstruction.ipynb` | Hi-C + FISH (GEM-FISH) |
| *Common to all data* | | |
| Data model & storage | `chromdata_basics.ipynb` | `ChromData`: bins, spots, tracks, intervals, results, subsetting |
| | `chromdata_stores.ipynb` | the `.chromdata.zarr` store: backed and remote reads, streaming, linked and embedded modalities |
| Structure calling | `loop_calling.ipynb`, `tad_calling.ipynb`, `fishnet_domains.ipynb`, `compartment.ipynb` | loops, TADs, per-allele domains, compartments from 3-D distances |
| Per-locus features | `features.ipynb` | distance maps, variance features, peaks, interval projections |
| Cells & embeddings | `cell_embeddings.ipynb` | embeddings and clusters from RNA / marks / contacts |
| Visualisation | `plotting_and_browser.ipynb` | `uchrom.pl` plots; the web browser from Python |

`takei2025_auto_discovery.ipynb` and `takei2025_iterative_auto_discovery.ipynb` (agents exploring a
dataset, `uchrom-discovery`) are kept here but left out of the documentation for now.

Run a notebook from the repository root:

```bash
jupyter nbconvert --to notebook --execute --inplace tutorials/<name>.ipynb
```
