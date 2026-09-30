# 3D reconstruction

U-Chrom ships three reconstruction backends under `uchrom.recon`, all
writing the same `.chromdata.zarr` output format.

| Backend | Module | Best for | Notes |
|---------|--------|----------|-------|
| Nuc Dynamics | `uchrom.recon.sc.nucdyn` | Single-cell Hi-C / Dip-C | Molecular dynamics, Taichi GPU (CUDA/Metal) |
| GEM | `uchrom.recon.sc.gem` | Single-cell, energy minimisation | Taichi autodiff |
| SMACOF MDS | `uchrom.recon.bulk.mds` | Bulk Hi-C, contact matrices | PyTorch GPU, inter-chromosomal support |

## Nuc Dynamics (single-cell)

Input: `.pairs` / `.pairs.gz` / `.cool`.
Output: `.chromdata.zarr` (one trace per chromosome).

CLI:

```bash
python -m uchrom.recon.sc.nucdyn cell1.pairs out.chromdata.zarr \
    --arch=cuda --dyns=500 \
    --size_steps='[8, 4, 2, 0.4, 0.2, 0.1]'
```

Key parameters:

| Param | Default | Meaning |
|-------|---------|---------|
| `arch` | `"gpu"` | Taichi architecture: `cpu` / `cuda` / `vulkan` / `metal` |
| `dyns` | 500 | MD steps per resolution stage |
| `size_steps` | `[8, 4, 2, 0.4, 0.2, 0.1]` (Mb) | Multi-resolution refinement schedule |
| `hot` / `cold` | 5000 / 10 | Initial / final temperature |
| `pow` | -0.33 | Contact-count → distance exponent |
| `cell_id` | from filename | Tag propagated into `cd.spots['cell_id']` |

## GEM (single-cell, energy minimisation)

Same CLI pattern:

```bash
python -m uchrom.recon.sc.gem cell1.pairs out.chromdata.zarr --arch=cuda
```

Writes four energy terms each step (stretch / bend / exclude / contact)
with Taichi's `ti.Tape` for autodiff gradient descent.

## Bulk MDS (PyTorch, whole-genome)

Input: `.hic` / `.mcool` / `.cool`.
Output: `.chromdata.zarr` (or per-chromosome for inter mode).

```bash
# Single chromosome
python -m uchrom.recon.bulk.mds data.mcool out.chromdata.zarr \
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
from uchrom.recon.sc.nucdyn import main as nucdyn_main
nucdyn_main("cell1.pairs", "out.chromdata.zarr", arch="cuda", dyns=500)

from uchrom import ChromData
cd = ChromData.read("out.chromdata.zarr")
```

All three backends write `.chromdata.zarr` with one trace per chromosome (single
cell) or one chromosome structure (bulk).  Downstream tools don't care
which reconstructor you used.
