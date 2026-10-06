# 3-D reconstruction

Contacts are not coordinates.  `uchrom.recon` computes 3-D structures from Hi-C — per cell, for a
population, or together with imaging — and returns them as `ChromData` like any traced data, so
everything downstream works on both.

| Method | Data | API |
|--------|------|-----|
| NucDynamics (simulated annealing of a particle model; ensembles on CPU and GPU) | single-cell Hi-C / Dip-C | `uchrom.recon.sc.reconstruct_nucdyn`, `python -m uchrom.recon.sc.nucdyn` |
| EMber (noise-aware single-cell reconstruction) | single-cell Hi-C, noisy contacts, phased diploid | `uchrom.recon.sc.reconstruct_ember`, `uc.tl.reconstruct_sc` |
| MDS / SMACOF (PyTorch; partitioned, inter-chromosomal) | bulk Hi-C | `python -m uchrom.recon.bulk.mds` |
| IGM population modelling (deconvolution into structures) | bulk Hi-C | `uchrom.recon.bulk.deconv.deconvolve(..., method="igm")` |
| GEM-FISH (Hi-C + FISH distances) | bulk Hi-C with tracing | `uchrom.recon.fish.reconstruct_gem_fish` |

NucDynamics, EMber and IGM run on the native engine, the package `uchrom-recon` (Rust; multi-core
CPU and wgpu GPU: Metal on macOS, Vulkan on Linux): `pip install ./packages/uchrom-recon`.

## Tutorials

```{toctree}
:maxdepth: 1

/tutorials/reconstruction
/tutorials/bulk_reconstruction
/tutorials/gem_fish_reconstruction
```

## Guide

```{toctree}
:maxdepth: 1

methods
```

API: [uchrom.recon](../reference/api/recon), [GEM-FISH](../reference/api/recon_fish).
