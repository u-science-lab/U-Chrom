# 3D reconstruction

U-Chrom ships three reconstruction backends under `uchrom.recon`, all
writing the same `.h5cd` output format.

| Backend | Module | Best for | Notes |
|---------|--------|----------|-------|
| NucDynamics | `uchrom.recon.sc.nucdyn` | Single-cell Hi-C / Dip-C | Native engine (Rust; multi-core CPU, wgpu GPU: Metal / Vulkan); ensembles |
| GEM | `uchrom.recon.sc.gem` | Single-cell, energy minimisation | Taichi autodiff |
| SMACOF MDS | `uchrom.recon.bulk.mds` | Bulk Hi-C, contact matrices | PyTorch GPU, inter-chromosomal support |

## NucDynamics (single-cell)

A re-implementation of NucDynamics (Stevens et al. 2017, *Nature* 544:59,
doi:10.1038/nature21429; original code tjs23/nuc_dynamics, LGPL-3.0) in the
separate native package `u-chrom-nucdyn` (`native/nucdyn`, Rust + PyO3):

```bash
pip install u-chrom[nucdyn]        # or: pip install ./native/nucdyn
```

It computes an ensemble of structures at once — models in parallel on the
CPU (f64), all models batched on the GPU (f32, wgpu: Metal on macOS, Vulkan
on Linux/NVIDIA).  Without the native package the deprecated Taichi port
runs instead (with a `DeprecationWarning`); it is not faithful to the
original and will be removed.

Input: `.pairs` / `.pairs.gz`, NCC (`.ncc`), a `chr_A pos_A chr_B pos_B`
table (the Stevens 2017 GEO files) or a DataFrame.  Output: a ChromData
with one spot per particle and one trace per chromosome; `coords` = model 0
and `layers["model_<k>"]` = every model (units: particle radii).

```python
from uchrom.recon.sc.nucdyn import reconstruct_nucdyn
cd = reconstruct_nucdyn("cell1.pairs", n_models=10, device="auto", seed=1)
cd.write("cell1.chromdata.zarr")
```

CLI:

```bash
python -m uchrom.recon.sc.nucdyn cell1.pairs out.chromdata.zarr \
    --n_models=10 --device=gpu --seed=1
```

Key parameters:

| Param | Default | Meaning |
|-------|---------|---------|
| `n_models` | 10 | Structures in the ensemble |
| `device` | `"auto"` | `cpu` (f64, all cores), `gpu` (f32), `auto` (GPU if available) |
| `n_threads` | 0 (all) | CPU threads |
| `seed` | 0 | Random seed (CPU results are bitwise reproducible per seed) |
| `protocol` | `"nuc_dynamics_2017"` | The 2017 code behind the published structures; `"release_1.3"`: the later version (bead scaling, model selection) |
| `particle_sizes` (`size_steps` in Mb on the CLI) | 8, 4, 2, 0.4, 0.2, 0.1 Mb | Hierarchical schedule |
| `temp_steps` / `dynamics_steps` | 500 / 100 | Annealing temperature steps per stage / MD steps per temperature |
| `temp_start` / `temp_end` | 5000 / 10 | Annealing temperatures |
| `genome_ranges` | None | Restrict the contacts, e.g. `["chr19"]` |

## GEM (single-cell, energy minimisation)

Same CLI pattern:

```bash
python -m uchrom.recon.sc.gem cell1.pairs out.h5cd --arch=cuda
```

Writes four energy terms each step (stretch / bend / exclude / contact)
with Taichi's `ti.Tape` for autodiff gradient descent.

## Bulk MDS (PyTorch, whole-genome)

Input: `.hic` / `.mcool` / `.cool`.
Output: `.h5cd` (or per-chromosome for inter mode).

```bash
# Single chromosome
python -m uchrom.recon.bulk.mds data.mcool out.h5cd \
    --resolution=100000 --chrom=chr1 --device=auto

# Whole genome with inter-chromosomal contacts
python -m uchrom.recon.bulk.mds data.mcool ./outdir/ \
    --resolution=100000 --resolution-inter=1000000 \
    --inter=True --device=auto
```

The solver is **SMACOF** with CMDS initialisation, implemented in
PyTorch so it runs on CUDA / MPS / CPU.  Inter-chromosomal mode runs a
low-resolution whole-genome scaffold MDS then Procrustes-aligns each
chromosome's high-resolution structure to its scaffold position.

Additional flags:

| Flag | Default | Meaning |
|------|---------|---------|
| `--alpha` | 4.0 | Contact → distance exponent |
| `--weight` | 0.05 | Distance-decay prior weight |
| `--n_iter` | 1000 | SMACOF iterations |
| `--partitioned` | False | Split by TAD for better parallelism |
| `--tad_bed` | None | TAD regions BED when `--partitioned` |

## Programmatic API

```python
from uchrom.recon.sc.nucdyn import reconstruct_nucdyn
cd = reconstruct_nucdyn("cell1.pairs", n_models=10)   # ChromData ensemble
cd.write("out.chromdata.zarr")

from uchrom import ChromData
cd = ChromData.read("out.h5cd")
```

All three backends write `.h5cd` with one trace per chromosome (single
cell) or one chromosome structure (bulk).  Downstream tools don't care
which reconstructor you used.
