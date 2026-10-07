# Tutorial gallery

Every tutorial, by data type and analysis step — each runs on real data, from a dataset to its results.  Click
a card to open the tutorial; the chapters ({doc}`tracing <tracing/index>`, {doc}`seqFISH <seqfish/index>`,
{doc}`single-cell Hi-C <schic/index>`, {doc}`bulk Hi-C <bulk/index>`) explain the methods around them.

## Chromatin tracing

```{tutorial-gallery}
- tutorial: import_fofct
  text: 4DN FOF-CT tracing with its cell and RNA tables, read and written back
  image: 2
- tutorial: import_pyhim_ecsv
  text: PyHiM ECSV traces (Bintu 2018 IMR90) as a `ChromData`
  crop: [0.3, 0, 0.68, 1]
- tutorial: jie_aligner
  text: Raw seqFISH+ spots to chromosome traces, against the authors' traces
  image: 2
- tutorial: fish_imputation
  text: Filling missing loci — linear, cubic, SnapFISH-IMPUTE — scored on hidden spots
  image: 2
  crop: [0, 0, 0.36, 1]
- tutorial: tad_calling
  text: TADs from 3-D distances (ArcFISH), next to Hi-C domains of the same loci
- tutorial: fishnet_domains
  text: Domains of single alleles (FISHnet) and how often each boundary is used
- tutorial: loop_calling
  text: Loops from 3-D distances with the axis-wise F-test
- tutorial: compartment
  text: A/B compartments from imaging, against Hi-C of the same cells
```

## Imaging multi-omics: DNA seqFISH+

```{tutorial-gallery}
- tutorial: import_seqfish_multiomics
  text: DNA seqFISH+ with chromatin marks and RNA (Takei 2025 cerebellum)
  crop: [0, 0, 0.52, 1]
```

## Single-cell and spatial Hi-C

```{tutorial-gallery}
- tutorial: pseudobulk
  text: Cell-type maps summed from an atlas store over HTTP; compartment strength at matched depth
- tutorial: reconstruction
  text: Single-cell 3-D structures with NucDynamics and EMber on the native engine
  image: 4
  crop: [0, 0, 0.5, 1]
- tutorial: higashi_embedding
  text: Cells embedded by their contact maps (FastHigashi)
  crop: [0, 0, 0.5, 1]
- tutorial: cell_embeddings
  text: Cells by RNA, ATAC or contacts (scHiCAR), and imaged cells by chromatin marks
  crop: [0, 0, 0.5, 1]
```

## Bulk Hi-C

```{tutorial-gallery}
- tutorial: hic_structures
  text: Compartments, insulation domains, HiCCUPS / Mustache loops and APA, against the published calls
  image: 2
- tutorial: bulk_reconstruction
  text: A consensus structure (MDS) and a population of structures (IGM) from one map
  image: 4
  crop: [0.34, 0.05, 0.68, 1]
- tutorial: gem_fish_reconstruction
  text: Hi-C and FISH distances in one model (GEM-FISH)
```

## Common to all data

```{tutorial-gallery}
- tutorial: chromdata_basics
  text: "`ChromData`: bins, spots, tracks, intervals, results, subsetting"
- tutorial: chromdata_stores
  text: The `.chromdata.zarr` store — backed and remote reads, streaming, linked and embedded data
- tutorial: features
  text: Distance maps, variance features, peaks and projections along the genome
  image: 3
- tutorial: plotting_and_browser
  text: Plots with `uchrom.pl` and the web browser from Python
  image: 4
```
