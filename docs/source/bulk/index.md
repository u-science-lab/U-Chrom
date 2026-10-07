# Bulk Hi-C

A bulk Hi-C map averages millions of nuclei.  U-Chrom reads it (`.cool`, `.mcool`, `.hic`, also over
HTTP), links it to a `ChromData` as a contact map, and turns it into 3-D in three ways: one consensus
structure (MDS), a population of structures whose contacts together reproduce the map (IGM), or a model
that also honours the distances of chromatin tracing in the same cell type (GEM-FISH).  Each returns a
`ChromData`, so the result is compared with imaging, measured and viewed like any traced data.

| Step | API |
|------|-----|
| read a map: `.cool` / `.mcool`, `.hic` (also over HTTP range requests) | `uchrom.io.load_cool`, `load_hic`, `load_hic_genome` |
| link a map to a `ChromData` (bulk or pseudo-bulk per cell type) | `cd.link_cool`, `cd.linked_cool_path()` |
| consensus structure: MDS / SMACOF (PyTorch; partitioned, inter-chromosomal) | `uchrom.recon.bulk.mds.run_mds`, `python -m uchrom.recon.bulk.mds` |
| population of structures: IGM (native engine) | `uchrom.recon.bulk.deconv.preprocess_hic`, `deconvolve(..., method="igm")` |
| Hi-C + chromatin tracing: GEM-FISH (PyTorch) | `uchrom.recon.fish.reconstruct_gem_fish`, `GEMFISHParams` |
| TADs from a contact map (directionality index) | `uc.tl.call_tads(cd, method="di", contacts=key)` ([structure calling](../structures/index)) |

IGM runs on the native engine, the package `uchrom-recon` (Rust; multi-core CPU and wgpu GPU):
`pip install ./packages/uchrom-recon`.

## Tutorials

```{toctree}
:maxdepth: 1

/tutorials/bulk_reconstruction
/tutorials/gem_fish_reconstruction
```

## Guides

```{toctree}
:maxdepth: 1

methods
```

API: [uchrom.recon](../reference/api/recon), [GEM-FISH](../reference/api/recon_fish).
