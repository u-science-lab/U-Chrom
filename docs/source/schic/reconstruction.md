# Single-cell reconstruction: methods and parameters

Two methods compute 3-D structures of one cell from its contacts, both on the native engine
`uchrom-recon` (Rust; multi-core CPU in f64, GPU in f32 through wgpu: Metal on macOS, Vulkan on Linux),
both returning an ensemble of models as one `ChromData`.

| Method | Module | Best for | Notes |
|--------|--------|----------|-------|
| EMber | `uchrom.recon.sc.ember` | single-cell Hi-C / Dip-C, noisy contacts, phased diploid | protocol `"robust"`; noise-aware, sampled ensembles, fast |
| NucDynamics | `uchrom.recon.sc.nucdyn` | single-cell Hi-C / Dip-C | the 2017 method of Stevens et al.; annealed ensembles |

## NucDynamics (single-cell)

A re-implementation of NucDynamics (Stevens et al. 2017, *Nature* 544:59,
doi:10.1038/nature21429; original code tjs23/nuc_dynamics, LGPL-3.0) in the
separate native package `uchrom-recon` (`packages/uchrom-recon`, Rust + PyO3):

```bash
pip install u-chrom[recon]        # or: pip install ./packages/uchrom-recon
```

It computes an ensemble of structures at once — models in parallel on the
CPU (f64), all models batched on the GPU (f32, wgpu: Metal on macOS, Vulkan
on Linux/NVIDIA).

Input: `.pairs` / `.pairs.gz`, NCC (`.ncc`), a `chr_A pos_A chr_B pos_B`
table (the Stevens 2017 GEO files) or a DataFrame.  Output: a ChromData
with one spot per particle and one trace per chromosome; `coords` = model 0
and `layers["model_<k>"]` = every model (units: particle radii).

```python
import uchrom.datasets as ds
from uchrom.recon.sc.nucdyn import reconstruct_nucdyn

pairs = ds.fetch("stevens2017") / "GSM2219497_Cell_1_contact_pairs.txt.gz"   # Stevens 2017 Cell 1 (GEO)
cd = reconstruct_nucdyn(pairs, n_models=10, device="auto", seed=1)
cd.write("cell1.chromdata.zarr")
```

CLI:

```bash
python -m uchrom.recon.sc.nucdyn contacts.pairs.gz out.chromdata.zarr \
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

## EMber (single-cell, noise-aware)

EMber (EM + annealing / sampling) runs on the same native engine as
NucDynamics (engine protocol `"robust"`, alias `"ember"`).  It keeps the
NucDynamics 2017 base and adds a mixture observation model — each contact is a
true proximity or a false contact; contact restraints are re-weighted by
their posterior probability of being true (EM; false-contact rate and contact
kernel learned from the data, plus local-support evidence) — a short schedule,
a finite-temperature sampling stage (calibrated ensembles) and adaptive
resolution below 25 kb.  It was pre-registered, frozen and tested against
NucDynamics on held-out contacts and imaging-truth simulations
(`benchmarks/screcon/PREREG.md`, `TEST_RESULTS.md`): better on both primary
endpoints, ~5x faster on one GPU; its real-data ensembles are less tight.

```python
from uchrom.recon.sc import reconstruct_ember
cd = reconstruct_ember(pairs, n_models=10, device="auto", seed=1)
cd.results["ember.contact_weights"]    # posterior weight of every input contact
# also: uchrom.tl.reconstruct_sc(contacts, method="ember")
#       reconstruct_nucdyn(contacts, protocol="ember")  (same coordinates for the same seed)
```

## Programmatic API

```python
from uchrom.recon.sc.nucdyn import reconstruct_nucdyn
cd = reconstruct_nucdyn("contacts.pairs.gz", n_models=10)   # ChromData ensemble
cd.write("out.chromdata.zarr")

from uchrom import ChromData
cd = ChromData.read("out.chromdata.zarr")
```

Both write a `ChromData` with one trace per chromosome (`coords` = model 0, `layers["model_<k>"]` = every
model); downstream tools do not care which method made it.  Bulk Hi-C: [bulk Hi-C](../bulk/index).
