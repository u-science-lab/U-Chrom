# U-Chrom tutorials

Jupyter notebooks that show each part of U-Chrom at work on real data.  They are committed
**executed** (the documentation renders them as they are) and grouped like the documentation's
chapters.  Their data come from the public atlas (`uchrom.datasets.atlas`) or from the original
sources (`uchrom.datasets.fetch`, cached in `$UCHROM_DATA`, else `~/.cache/uchrom`); outputs go to
`tutorials/_out/` (ignored by git).

| Chapter › step | Notebook | Shows |
|----------------|----------|-------|
| *By data type* | | |
| Chromatin tracing › reading | `import_fofct.ipynb` | 4DN FOF-CT tracing with cell and RNA tables, and back |
| | `import_pyhim_ecsv.ipynb` | PyHiM ECSV traces |
| Chromatin tracing › traces | `jie_aligner.ipynb` | spot-to-trace alignment on raw seqFISH+ spots |
| Chromatin tracing › imputation | `fish_imputation.ipynb` | filling missing loci: linear, cubic, SnapFISH-IMPUTE |
| Chromatin tracing › structures | `loop_calling.ipynb`, `tad_calling.ipynb`, `fishnet_domains.ipynb`, `compartment.ipynb` | loops, TADs, per-allele domains, compartments from 3-D distances |
| DNA seqFISH+ › reading | `import_seqfish_multiomics.ipynb` | DNA seqFISH+ with chromatin marks and RNA (Takei 2025 cerebellum) |
| Single-cell Hi-C › pseudo-bulk | `pseudobulk.ipynb` | cell-type maps summed from an atlas store over HTTP (dscHi-C); compartments and their strength at matched depth |
| Single-cell Hi-C › 3-D structures | `reconstruction.ipynb` | single-cell NucDynamics and EMber on the native engine |
| Single-cell Hi-C › embeddings | `higashi_embedding.ipynb` | FastHigashi on single-cell Hi-C |
| | `cell_embeddings.ipynb` | scHiCAR cells by RNA / ATAC / contacts; imaging cells by chromatin marks |
| Bulk Hi-C › calling structures | `hic_structures.ipynb` | compartments, insulation domains, HiCCUPS / Mustache loops and APA on Rao 2014 IMR90, against the published calls; what depth does to them |
| Bulk Hi-C › 3-D structures | `bulk_reconstruction.ipynb` | MDS and IGM population models |
| Bulk Hi-C › with imaging | `gem_fish_reconstruction.ipynb` | Hi-C + FISH (GEM-FISH) |
| *Common to all data* | | |
| Data model & storage | `chromdata_basics.ipynb` | `ChromData`: bins, spots, tracks, intervals, results, subsetting |
| | `chromdata_stores.ipynb` | the `.chromdata.zarr` store: backed and remote reads, streaming, linked and embedded modalities |
| Per-locus features | `features.ipynb` | distance maps, variance features, peaks, interval projections |
| Visualisation | `plotting_and_browser.ipynb` | `uchrom.pl` plots; the web browser from Python |

`takei2025_auto_discovery.ipynb` and `takei2025_iterative_auto_discovery.ipynb` (agents exploring a
dataset, `uchrom-discovery`) are kept here but left out of the documentation for now.

Run a notebook from the repository root:

```bash
jupyter nbconvert --to notebook --execute --inplace tutorials/<name>.ipynb
```
