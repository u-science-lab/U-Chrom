# Bulk Hi-C

A bulk Hi-C map averages millions of nuclei.  U-Chrom reads it (`.cool`, `.mcool`, `.hic`, also over HTTP),
links it to a `ChromData` and calls the structures it shows — compartments, domains, loops, or the pileup
of known loops when the map is too shallow to call them.  It also turns the map into 3-D: one consensus
structure (MDS), a population of structures whose contacts together reproduce the map (IGM), or a model that
also honours the distances measured by chromatin tracing in the same cell type (GEM-FISH).  Each returns a
`ChromData`, compared with imaging, measured and viewed like any traced data.

| Step | Page | API |
|------|------|-----|
| read a map; link it to a `ChromData` (bulk, or pseudo-bulk per cell type) | — | `uchrom.io.load_cool` / `load_hic`, `cd.link_cool`, `cd.linked_cool_path`, `uchrom.datasets.load` |
| compartments (cis eigenvector, saddle strength), domains (insulation, directionality index), loops (HiCCUPS, Mustache) and pileups of known loops, against published calls | [Calling structures from a map](structures) | `uc.tl.call_compartments(cd, method="eig")`, `uc.tl.compartment_strength`, `uc.tl.call_tads(cd, method="insulation")`, `uc.tl.call_loops(cd, method="hiccups")`, `uc.tl.pileup` |
| one consensus structure (MDS), a population of structures (IGM) | [Structures from a bulk map](reconstruction) | `uchrom.recon.bulk.mds`, `uchrom.recon.bulk.deconv.deconvolve(..., method="igm")` |
| Hi-C and chromatin tracing together | [Hi-C with imaging: GEM-FISH](gem_fish) | `uchrom.recon.fish.reconstruct_gem_fish` |

IGM runs on the native engine, the package `uchrom-recon` (Rust; multi-core CPU and wgpu GPU):
`pip install ./packages/uchrom-recon`.

```{toctree}
:maxdepth: 2
:hidden:

structures
reconstruction
gem_fish
```
