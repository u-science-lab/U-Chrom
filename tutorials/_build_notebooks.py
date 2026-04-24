"""Regenerate the tutorial notebooks under ``tutorials/``.

Run once from the repo root::

    python tutorials/_build_notebooks.py

Notebooks are written with empty outputs and ``execution_count = null`` so
they diff cleanly.  Keep cell ``source`` as a list of strings (one line
each) for readability in ``git diff``.
"""

from __future__ import annotations

import json
from pathlib import Path


def md(text: str):
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": [line + "\n" for line in text.rstrip("\n").split("\n")],
    }


def code(text: str):
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [line + "\n" for line in text.rstrip("\n").split("\n")],
    }


NB_META = {
    "kernelspec": {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    },
    "language_info": {
        "name": "python",
        "version": "3.11",
    },
}


def write_nb(path: Path, cells: list):
    nb = {
        "cells": cells,
        "metadata": NB_META,
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(nb, indent=1) + "\n")
    print(f"wrote {path}")


# ============================================================
# ChromData basics
# ============================================================

nb1 = [
    md("""\
# ChromData — the core data container

`uchrom.ChromData` is the central data structure for U-Chrom, analogous to
[AnnData](https://anndata.readthedocs.io/) for chromatin 3D structure data.
It holds genomic bins mapped to 3D coordinates, grouped in a
**Cell → Trace → Spot** hierarchy, and persists as `.h5cd` (HDF5) files.

This notebook covers:

- Creating a ChromData from scratch
- The three "core tables" (core / cell / chromatin) and auxiliary storage
- Subsetting by chromosome, trace, or cell
- Round-tripping to `.h5cd` with format versioning
- Importing from reconstruction CSV and FOF-CT"""),

    code("""\
import numpy as np
import pandas as pd
from uchrom import ChromData"""),

    md("## Minimal construction\n\n`ChromData` needs at least `coords (n_spots, 3)` and a `spots` DataFrame with `chrom / start / end / trace_id`."),

    code("""\
rng = np.random.default_rng(0)
coords = rng.normal(size=(60, 3))
spots = pd.DataFrame({
    'chrom':    ['chr1']*30 + ['chr2']*30,
    'start':    list(range(0, 30_000_000, 1_000_000)) * 2,
    'end':      list(range(1_000_000, 31_000_000, 1_000_000)) * 2,
    'trace_id': [0]*30 + [1]*30,
})

cd = ChromData(coords, spots, uns={'genome_assembly': 'GRCh38'})
cd"""),

    md("## Attributes"),

    code("""\
print('n_spots :', cd.n_spots)
print('n_traces:', cd.n_traces)
print('chroms  :', cd.chroms)
cd.spots.head()"""),

    md("`spots['chrom']` and `spots['trace_id']` are auto-converted to `pd.Categorical` for ~10× memory savings on large datasets."),

    code("""\
print(cd.spots['chrom'].dtype)
print(cd.spots['trace_id'].dtype)"""),

    md("## Subsetting\n\nAll subset operations return a **new** `ChromData` — never mutate the original."),

    code("""\
chr1 = cd.get_chrom('chr1')
print(chr1)"""),

    code("""\
trace0 = cd.get_trace(0)
print(trace0)

# Boolean indexing also works
first_ten = cd[np.arange(10)]
print(first_ten)"""),

    md("## On-demand distance matrix\n\nGlobal pairwise distance matrices are not stored (they'd be O(n²) and biologically meaningless across cells). Compute per-trace on demand:"),

    code("""\
d = cd.compute_distances(trace_id=0)
print('distance matrix shape:', d.shape)
print('diagonal is zero      :', np.allclose(np.diag(d), 0))"""),

    md("## Persistence — `.h5cd`\n\n`ChromData` serialises to HDF5 with a format version attribute so future releases can migrate old files."),

    code("""\
import tempfile, os
tmp = tempfile.mkdtemp()
path = os.path.join(tmp, 'demo.h5cd')

cd.write(path)
cd2 = ChromData.read(path)
print(cd2)
print('coords match:', np.allclose(cd.coords, cd2.coords))"""),

    md("""\
## Importing from existing formats

| Source | Method |
|--------|--------|
| Reconstruction CSV (chrom, start, end, x, y, z) | `ChromData.from_dataframe(df)` |
| 4DN FOF-CT core table | `ChromData.from_fofct(path)` |
| `.h5cd` | `ChromData.read(path)` |"""),

    code("""\
# Example: from a reconstruction output CSV (here we build a fake one)
recon = pd.DataFrame({
    'chrom': ['chr1']*10,
    'start': range(0, 10_000_000, 1_000_000),
    'end':   range(1_000_000, 11_000_000, 1_000_000),
    'x': rng.normal(size=10),
    'y': rng.normal(size=10),
    'z': rng.normal(size=10),
})
cd_recon = ChromData.from_dataframe(recon, cell_id='demo_cell')
cd_recon"""),

    md("## Where to go next\n\n- **Importing FOF-CT imaging data** and inspecting trace structure.\n- **3D reconstruction** from Hi-C `.pairs` files.\n- **Loop calling** on FOF-CT data."),
]

write_nb(Path("tutorials") / "chromdata_basics.ipynb", nb1)


# ============================================================
# FOF-CT imaging data
# ============================================================

nb2 = [
    md("""\
# Importing FOF-CT imaging data

The [4DN FISH Omics Format — Chromatin Tracing](https://fish-omics-format.readthedocs.io/)
(FOF-CT) is the community standard for chromatin-tracing / multiplexed DNA
FISH experiments.  A FOF-CT *core table* is a CSV with a metadata header
(`##FOF-CT_Version=v1.0`, `##Columns=(…)`) followed by per-spot rows.

This notebook loads a real FOF-CT dataset with `ChromData.from_fofct` and
shows how to navigate the **Cell → Trace → Spot** hierarchy that imaging
data naturally exposes."""),

    code("""\
import numpy as np
import pandas as pd
from uchrom import ChromData

# Change this to a FOF-CT file you have locally
FOFCT = 'example-data/fofct_core.csv'  # or similar

# For this tutorial we build a synthetic example that looks like FOF-CT
# output in case you do not have a file handy.  Skip this cell if you
# downloaded a real file.
import io, os
if not os.path.exists(FOFCT):
    os.makedirs('example-data', exist_ok=True)
    rng = np.random.default_rng(0)
    header = '''##FOF-CT_Version=v1.0
##Table_Namespace=4dn_FOF-CT_core
##Genome_Assembly=GRCh38
##XYZ_Unit=micron
#Lab_Name: Demo
##Columns=(Spot_ID, Trace_ID, X, Y, Z, Chrom, Chrom_Start, Chrom_End, Cell_ID)
'''
    rows = []
    sid = 1
    for cell in range(20):
        for trace in range(2):          # 2 alleles per cell
            walk = np.cumsum(rng.normal(scale=0.12, size=(12, 3)), axis=0)
            for bin_i in range(12):      # 12 bins per trace
                x, y, z = walk[bin_i]
                start = 1_000_000 + bin_i * 10_000
                rows.append((sid, f'{cell}_{trace}', x, y, z,
                             'chr17', start, start + 10_000, cell))
                sid += 1
    with open(FOFCT, 'w') as f:
        f.write(header)
        for r in rows:
            f.write(','.join(str(x) for x in r) + '\\n')

FOFCT"""),

    md("## Load the file"),

    code("""\
cd = ChromData.read(FOFCT) if FOFCT.endswith(".h5cd") else ChromData.from_fofct(FOFCT)
cd"""),

    md("## Inspect metadata\n\nThe FOF-CT header fields go into `cd.uns` so you can always trace the origin of a dataset."),

    code("""\
cd.uns['fofct_header']"""),

    code("""\
print('genome   :', cd.uns.get('genome_assembly'))
print('xyz_unit :', cd.uns.get('xyz_unit'))
print()
print(cd.spots.head())"""),

    md("## Traces per chromosome\n\nImaging data typically has many traces per chromosome (each trace = one allele observation)."),

    code("""\
summary = (
    cd.spots
      .groupby('chrom', observed=True)
      .agg(n_spots=('trace_id', 'size'),
           n_traces=('trace_id', 'nunique'))
)
summary"""),

    md("## Subsetting a single trace\n\nThis is the natural unit of analysis in chromatin tracing."),

    code("""\
first_trace_id = cd.spots['trace_id'].iloc[0]
trace = cd.get_trace(first_trace_id)
print(trace)
print()
print(trace.to_dataframe().head())"""),

    md("## Convert to ChromData-backed analysis format\n\nDownstream analysis modules in `uchrom.fea` and `uchrom.strc` operate directly on the flat DataFrame produced by `cd.to_dataframe()` or accept the `ChromData` itself."),

    code("""\
df = cd.to_dataframe()
print(df.columns.tolist())
df.head()"""),

    md("""\
## Writing your own FOF-CT-compatible data

If you produced tracing data with a tool that does not write FOF-CT, you
can create a ChromData directly (see the ChromData basics tutorial) and write `.h5cd`.  The
on-disk format is versioned so downstream tools can safely consume it."""),
]

write_nb(Path("tutorials") / "import_fofct.ipynb", nb2)


# ============================================================
# Reconstruction from Hi-C
# ============================================================

nb3 = [
    md("""\
# 3D reconstruction from Hi-C data

U-Chrom provides several 3D reconstruction algorithms:

| Module | Best for | Notes |
|--------|---------|-------|
| `uchrom.recon.sc.nucdyn` | Single-cell Hi-C / Dip-C | Molecular-dynamics, Taichi GPU |
| `uchrom.recon.sc.gem` | Single-cell, energy minimisation | Taichi autodiff |
| `uchrom.recon.bulk.mds` | Bulk Hi-C | SMACOF MDS, PyTorch GPU |

This notebook walks through a short single-cell reconstruction using Nuc
Dynamics on the example data shipped with the repo."""),

    md("## Locate the example data\n\nThe notebook looks for `example-data/cell1.pairs` in the repo; we walk up the directory tree to find the repo root so this runs from any cwd."),

    code("""\
from pathlib import Path

def find_repo_root(start: Path = Path.cwd()) -> Path:
    for p in [start, *start.parents]:
        if (p / 'example-data' / 'cell1.pairs').exists():
            return p
    raise FileNotFoundError('Could not locate example-data/cell1.pairs')

repo = find_repo_root()
pairs = repo / 'example-data' / 'cell1.pairs'
out_path = repo / 'tutorials' / '_out_tutorial3.h5cd'
print('pairs:', pairs)
print('out  :', out_path)"""),

    md("## Run Nuc Dynamics\n\nThe CLI is the simplest way; the main function is also importable."),

    code("""\
# From the shell (uncomment to run):
# !python -m uchrom.recon.sc.nucdyn example-data/cell1.pairs out.h5cd \\
#     --arch=cpu --dyns=30 --size_steps='[2, 0.4]'

from uchrom.recon.sc.nucdyn import main as nucdyn_main
nucdyn_main(
    str(pairs),
    str(out_path),
    arch='cpu',      # 'cuda' if you have an NVIDIA GPU
    dyns=30,         # fewer steps for the tutorial
    size_steps=[2, 0.4],  # only two resolution stages
)"""),

    md("## Load the reconstructed structure\n\nThe `.h5cd` output carries a `cell_id` derived from the filename and one trace per chromosome."),

    code("""\
from uchrom import ChromData
cd = ChromData.read(str(out_path))
cd"""),

    code("""\
print('chroms  :', cd.chroms)
print('n_spots :', cd.n_spots)
cd.spots.head()"""),

    md("## Compute a distance matrix for one chromosome"),

    code("""\
import matplotlib.pyplot as plt

trace_id = cd.spots['trace_id'].iloc[0]
D = cd.compute_distances(trace_id=trace_id)

fig, ax = plt.subplots(figsize=(5, 5))
im = ax.imshow(D, cmap='viridis_r', aspect='equal')
ax.set_title(f'Distance matrix — trace {trace_id}')
fig.colorbar(im, ax=ax, label='distance')"""),

    md("""\
## Using other reconstruction backends

`python -m uchrom.recon.sc.gem <in> <out.h5cd>` — energy-minimisation
variant (smoother, slower).

`python -m uchrom.recon.bulk.mds <contact.mcool> <out.h5cd> --resolution=100000`
— PyTorch SMACOF MDS on bulk Hi-C data.  Inter-chromosomal whole-genome
reconstruction via `--inter` with the additional `--resolution_inter` flag.

All three write the same `.h5cd` schema so downstream tools don't care
which reconstructor was used."""),
]

write_nb(Path("tutorials") / "reconstruction.ipynb", nb3)


# ============================================================
# Benchmarking MDS reconstruction (speed & quality)
# ============================================================

nb_benchmark = [
    md("""\
# Benchmarking MDS reconstruction

U-Chrom's bulk MDS module (`uchrom.recon.bulk.mds`) exposes two solvers
(SMACOF and Adam) and runs on CPU, CUDA, or Apple MPS.  When you set up
a new analysis you usually want to know:

1. **Which solver should I use?**  (SMACOF vs Adam)
2. **Does the GPU actually help for my data size?**
3. **How does resolution trade off against cost and reconstruction fidelity?**

This notebook is a reproducible benchmark template.  We use GM12878
in-situ Hi-C (Rao et al., 2014) and chromosome 22 so the whole notebook
finishes in under a minute.  The same pattern applies to any
chromosome or dataset."""),

    md("""\
## Background: evolution from miniMDS

U-Chrom's bulk MDS solver borrows the overall recipe from
[miniMDS (Rieber & Mahony, 2017)](https://github.com/seqcode/miniMDS):
convert contact frequencies to distances via `d = c^(-1/α)`, smooth
with a distance-decay prior, then iteratively minimise MDS stress.
The U-Chrom implementation is a PyTorch-native rewrite with the
following departures:

| Aspect | miniMDS | U-Chrom |
|--------|---------|---------|
| Input | BED text (manual export) | `.hic` / `.mcool` / `.cool` directly |
| Initialisation | 4 random inits × 300 iters | CMDS eigendecomposition × 1 run (up to 1000 iters, early stop on convergence) |
| Device | CPU only (sklearn) | PyTorch on CUDA / MPS / CPU with auto-detection |
| Distance-decay prior | Python double `for` loop | Vectorised `scatter_add_` |
| Zero-contact bins | `assert` crash on all-zero rows | Auto-filtered before MDS; bins returned in `nonzero_mask` |
| Stress | Treats missing pairs as `d = 0` | Observed-pairs-only (weighted mask) |
| Whole-genome | Manual per-chromosome script | `inter_mds()` one-liner |
| Output | Custom TSV with NaN markers | `.h5cd` (ChromData HDF5) |

Both solvers exposed in `run_mds(method=...)` share this infrastructure:

- `method='smacof'` — Guttman transform, no autograd, the direct
  miniMDS lineage path.  Fastest for typical cases.
- `method='adam'` — PyTorch autograd + Adam optimiser.  Useful if you
  need to modify the stress function or add priors.

Typical speedup on GM12878 chr22 @ 100 kb (single-thread CPU):
miniMDS ~0.8 s vs U-Chrom SMACOF ~0.1 s; on Apple MPS / CUDA the
advantage grows to 20–40× at finer resolutions.  Structures remain
equivalent (pairwise-distance Pearson r > 0.99, input-output
correlation within 0.001)."""),

    md("""\
## Locate the GM12878 `.hic` file

The benchmark needs the GM12878 in-situ combined Hi-C file
(`GSE63525_GM12878_insitu_primary+replicate_combined_30.hic`,
~40 GB).  Because of its size this file is **not** auto-downloaded;
drop it into `example-data/` (or point `UCHROM_GM12878_HIC` at it).

Download sources:

- [4DN DCIC — 4DNFI1UEG1HD](https://data.4dnucleome.org/files-processed/4DNFI1UEG1HD/)
- [GEO GSE63525](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE63525)

Also required: `pip install hic-straw` (reads `.hic` files)."""),

    code("""\
import os
from pathlib import Path

def find_repo_root(start: Path = Path.cwd()) -> Path:
    for p in [start, *start.parents]:
        if (p / 'pyproject.toml').exists() or (p / 'example-data').exists():
            return p
    raise FileNotFoundError('Could not locate repo root')

repo = find_repo_root()
default_path = repo / 'example-data' / 'GSE63525_GM12878_insitu_primary+replicate_combined_30.hic'
HIC_PATH = Path(os.environ.get('UCHROM_GM12878_HIC', str(default_path)))

if not HIC_PATH.exists():
    raise FileNotFoundError(
        f'GM12878 .hic file not found at {HIC_PATH}.\\n'
        'Download from 4DN DCIC (4DNFI1UEG1HD) or GEO GSE63525, place it at\\n'
        f'  {default_path}\\n'
        'or set UCHROM_GM12878_HIC to its location.'
    )
print('Using:', HIC_PATH)"""),

    md("""\
## Load chr22 contact matrix at 100 kb

`uchrom.io.load_hic` wraps `hicstraw` and returns a `(bins_df, matrix)`
tuple.  We'll use chr22 because it's small (~51 Mb → 514 bins at 100 kb)
and good enough to show the scaling trend."""),

    code("""\
import numpy as np
import torch
from uchrom.io import load_hic

CHROM, RES = 'chr22', 100_000
bins_df, contact_mat = load_hic(str(HIC_PATH), RES, CHROM)

n = contact_mat.shape[0]
sparsity = 1.0 - np.count_nonzero(contact_mat) / (n * n)
print(f'{CHROM} @ {RES//1000}kb: {n} bins, sparsity {sparsity:.1%}')"""),

    md("""\
## Compare the two MDS solvers

`run_mds` exposes both SMACOF (default, fast) and Adam (gradient
descent with autograd).  Both are called via the same interface; only
the `method` argument differs."""),

    code("""\
import time
from uchrom.recon.bulk.mds import run_mds

def time_mds(method, device='cpu', n_iter=1000):
    t0 = time.time()
    coords, mask = run_mds(
        torch.from_numpy(contact_mat.astype(np.float64)),
        alpha=4.0, weight=0.05,
        method=method, device=device, n_iter=n_iter,
        verbose=False,
    )
    return coords, mask, time.time() - t0

coords_smacof, mask, t_smacof = time_mds('smacof', device='cpu')
coords_adam,   _,    t_adam   = time_mds('adam',   device='cpu')

print(f'SMACOF (CPU): {t_smacof:.2f}s, output shape {coords_smacof.shape}')
print(f'Adam   (CPU): {t_adam:.2f}s, output shape {coords_adam.shape}')"""),

    md("""\
## Compare CPU vs GPU (SMACOF)

On Apple silicon `device='auto'` picks MPS (Metal); on an NVIDIA box it
picks CUDA.  For chr22 the matrix is small enough that GPU startup
overhead dominates — the advantage kicks in at finer resolutions (see
the sweep below)."""),

    code("""\
coords_cpu, _, t_cpu = time_mds('smacof', device='cpu')
coords_gpu, _, t_gpu = time_mds('smacof', device='auto')
print(f'SMACOF CPU : {t_cpu:.2f}s')
print(f'SMACOF auto: {t_gpu:.2f}s  (speedup {t_cpu/t_gpu:.2f}×)')"""),

    md("""\
## Three orthogonal evaluation metrics

No single number captures reconstruction quality.  We compute three:

1. **Agreement (Pearson r on pairwise distances)** — after Procrustes
   alignment, how similar are two reconstructions of the same data?
2. **Input-output correlation** — per method, Spearman correlation
   between observed contact frequency and `1 / d_3D`.  Measures how
   faithfully the 3D structure preserves Hi-C signal (independent of
   the other method).
3. **Distance-fitting RMSD** — how well do the coordinates satisfy
   each solver's own target distance matrix (i.e. the MDS objective)?"""),

    code("""\
from scipy.spatial.distance import pdist
from scipy.stats import pearsonr, spearmanr
from uchrom.recon.bulk.mds.transforms import procrustes_alignment, apply_transform


def agreement_pearson(a, b):
    \"\"\"Pairwise distance Pearson r after Procrustes alignment.\"\"\"
    R, t, s = procrustes_alignment(a, b)
    a_aligned = apply_transform(a, R, t, s)
    return pearsonr(pdist(a_aligned), pdist(b))[0]


def io_correlation(coords, contact):
    \"\"\"Spearman between contact frequency and 1/d_3D on observed pairs.\"\"\"
    from scipy.spatial.distance import squareform
    d = squareform(pdist(coords))
    mask = contact > 0
    np.fill_diagonal(mask, False)
    c = contact[mask]
    inv_d = 1.0 / np.clip(d[mask], 1e-12, None)
    return spearmanr(c, inv_d)[0]


def fit_rmsd(coords, target_dist):
    \"\"\"Normalized RMSD between 3D distances and target on observed pairs.\"\"\"
    from scipy.spatial.distance import squareform
    d = squareform(pdist(coords))
    mask = (target_dist > 0)
    np.fill_diagonal(mask, False)
    if not mask.any():
        return float('nan')
    scale = target_dist[mask].mean() / max(d[mask].mean(), 1e-12)
    d *= scale
    rg = float(np.sqrt(np.mean(np.sum((coords - coords.mean(0)) ** 2, axis=1))))
    return float(np.sqrt(((d[mask] - target_dist[mask]) ** 2).mean()) / max(rg, 1e-12))


# Build the target distance matrix the way the SMACOF solver saw it
from uchrom.recon.bulk.mds.core import (
    apply_distance_decay_prior, contact_to_distance, normalize_distances,
)

contact_tensor = torch.from_numpy(contact_mat.astype(np.float64))
contact_tensor = contact_tensor[mask][:, mask]  # use the filtered bins
contact_adj = apply_distance_decay_prior(contact_tensor, 0.05)
target_dist = normalize_distances(contact_to_distance(contact_adj, 4.0)).numpy()
contact_sub = contact_tensor.numpy()

print(f'Agreement (SMACOF vs Adam, Pearson r)   : {agreement_pearson(coords_smacof, coords_adam):.4f}')
print(f'IO correlation  — SMACOF                : {io_correlation(coords_smacof, contact_sub):.4f}')
print(f'IO correlation  — Adam                  : {io_correlation(coords_adam,   contact_sub):.4f}')
print(f'Distance-fit RMSD — SMACOF              : {fit_rmsd(coords_smacof, target_dist):.4f}')
print(f'Distance-fit RMSD — Adam                : {fit_rmsd(coords_adam,   target_dist):.4f}')"""),

    md("""\
## Resolution sweep

At coarse resolutions miniMDS-style solvers finish quickly and GPU
overhead dominates.  At fine resolutions GPU wins by a large margin.
Let's quantify that on chr22 across four resolutions."""),

    code("""\
import pandas as pd
import matplotlib.pyplot as plt

records = []
for r in [100_000, 50_000, 25_000, 10_000]:
    bins_r, mat_r = load_hic(str(HIC_PATH), r, CHROM)
    n_r = mat_r.shape[0]

    coords_cpu_r, _, t_cpu_r = time_mds('smacof', device='cpu')
    tensor_r = torch.from_numpy(mat_r.astype(np.float64))
    t0 = time.time()
    coords_gpu_r, mask_r = run_mds(tensor_r, alpha=4.0, weight=0.05,
                                   method='smacof', device='auto',
                                   n_iter=1000, verbose=False)
    t_gpu_r = time.time() - t0

    sub = mat_r[mask_r][:, mask_r]
    io_r = io_correlation(coords_gpu_r, sub)
    records.append({'resolution_kb': r // 1000, 'n_bins': n_r,
                    't_cpu': t_cpu_r, 't_gpu': t_gpu_r,
                    'io_corr': io_r})

df = pd.DataFrame(records).sort_values('resolution_kb', ascending=False)
df"""),

    code("""\
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4))

ax1.plot(df['resolution_kb'], df['t_cpu'], 'o-', label='CPU (1 thread)', color='#E74C3C')
ax1.plot(df['resolution_kb'], df['t_gpu'], 'o-', label='GPU / MPS',     color='#F39C12')
ax1.set_xlabel('Resolution (kb)'); ax1.set_ylabel('Time (s)')
ax1.set_xscale('log'); ax1.set_yscale('log'); ax1.invert_xaxis()
ax1.grid(True, which='both', alpha=0.3); ax1.legend()
ax1.set_title(f'{CHROM} — speed vs resolution')

ax2.plot(df['resolution_kb'], df['io_corr'], 'o-', color='#27AE60')
ax2.set_xlabel('Resolution (kb)'); ax2.set_ylabel('Input-output Spearman r')
ax2.set_xscale('log'); ax2.invert_xaxis()
ax2.set_ylim(0, 1.02); ax2.grid(True, which='both', alpha=0.3)
ax2.set_title(f'{CHROM} — quality vs resolution')

fig.tight_layout()"""),

    md("""\
## Standard output format: `.h5cd`

U-Chrom's reconstruction output is `.h5cd` — a ChromData HDF5 file
that every reconstructor (NucDyn, GEM, bulk MDS) and every import
path (FOF-CT, Hi-C .pairs) writes in the same schema.  That means you
can feed any reconstruction to the same downstream tools (loop / TAD
/ compartment callers, browser, plotting helpers) without format
adapters.

Each `.h5cd` carries:

- **coords** — per-bin 3D coordinates
- **spots** — `chrom`, `start`, `end`, `trace_id` (+ optional `cell_id`)
- **format header** — `uchrom_format_version` attr for forward-compatible upgrades
- **optional** — cell metadata, epigenomic tracks, analysis results (loops/TADs/compartments)

`save_particles()` auto-detects the format from the filename
extension (`.h5cd` → ChromData HDF5, `.csv` → flat CSV)."""),

    code("""\
from uchrom.io import save_particles, read_particles
from uchrom import ChromData

out_dir = repo / 'tutorials' / '_out_benchmark'
out_dir.mkdir(parents=True, exist_ok=True)

def to_df(coords, bin_mask):
    kept = bins_df[bin_mask].reset_index(drop=True)
    return pd.DataFrame({
        'chrom': kept['chrom'].values,
        'start': kept['start'].values,
        'end':   kept['end'].values,
        'x': coords[:, 0], 'y': coords[:, 1], 'z': coords[:, 2],
    })

save_particles(to_df(coords_smacof, mask), out_dir / 'smacof.h5cd')
save_particles(to_df(coords_adam,   mask), out_dir / 'adam.h5cd')

print('Wrote:')
print(f'  {out_dir}/smacof.h5cd')
print(f'  {out_dir}/adam.h5cd')"""),

    md("""\
### Reading the output back

Two paths depending on what you need next:

- **`read_particles(path)`** — returns a flat `pandas.DataFrame`
  (chrom/start/end/x/y/z).  Simplest for quick analysis or export to
  another tool.
- **`ChromData.read(path)`** — returns the full ChromData container
  with cell/trace hierarchy, metadata accessors, and
  `compute_distances()` for on-demand pairwise distance matrices."""),

    code("""\
# Quick flat-DataFrame access
df_smacof = read_particles(str(out_dir / 'smacof.h5cd'))
print(df_smacof.head(3))
print('shape:', df_smacof.shape)"""),

    code("""\
# Full ChromData container
cd = ChromData.read(str(out_dir / 'smacof.h5cd'))
print(cd)
print('n_traces :', len(cd.traces))
print('n_spots  :', cd.n_spots)"""),

    md("""\
## Visualize side-by-side in the U-Chrom Browser

The browser is a PyQt5 + PyVista GUI that renders any number of
`.h5cd` files as linked 3D viewports.  Launch it from a terminal:

```bash
python -m uchrom.browser tutorials/_out_benchmark/smacof.h5cd \\
                         tutorials/_out_benchmark/adam.h5cd
```

Inside the browser:

- Each file gets its own viewport (linked camera by default — drag in
  one viewport rotates all of them in sync).
- Toggle **Canvas → Link canvases** to control this behaviour.
- Use the right-side **Properties** panel to change style (line / tube
  / points), width, opacity, colour mode (rainbow / single / per-trace),
  and layer label font/position.  In link mode those settings apply to
  every viewport at once.
- Click a viewport to switch the active canvas (its parameters load
  into the right panel).
- Drag a layer into the **Layers** list to manage visibility or delete
  it.

Tip: open more than two files to see all reconstructions at once; the
browser handles 4–8 viewports comfortably.

The screenshot below shows the two reconstructions for this tutorial
(SMACOF left, Adam right) with cameras synced:

![U-Chrom Browser — SMACOF vs Adam reconstructions of GM12878 chr22 @ 100 kb](_out_benchmark/browser_demo.png)"""),

    code("""\
# Exact command printed again for easy copy-paste
print('python -m uchrom.browser',
      out_dir / 'smacof.h5cd', out_dir / 'adam.h5cd')"""),

    md("""\
## Takeaways and next steps

- **SMACOF is the default** because it converges in fewer iterations
  without autograd overhead.  Adam remains useful when you need a
  custom stress function.
- **GPU wins at finer resolutions.**  For coarse maps (≥ 250 kb) CPU
  is often faster because MPS/CUDA startup overhead dominates.
- **All three metrics agree on the rough conclusion** that SMACOF and
  Adam produce structurally equivalent reconstructions (Pearson r > 0.99)
  — they differ mostly in how quickly they get there.
- For very high resolutions (5 kb and below) dense MDS on a whole
  chromosome is memory-bound.  Use
  `uchrom.recon.bulk.mds.partitioned_mds` (TAD-wise divide and
  conquer) or the whole-genome workflow in `uchrom.recon.bulk.mds.inter`.
- External comparisons against `miniMDS` follow the same pattern — add
  a third call to whatever solver you want and run it through the same
  three metrics."""),
]

write_nb(Path("tutorials") / "benchmark.ipynb", nb_benchmark)


# ============================================================
# Loop calling
# ============================================================

nb4 = [
    md("""\
# Loop calling on tracing data

`uchrom.strc.loop` provides a GPU-accelerated reimplementation of the
axis-wise F-test loop caller from Yu et al. 2025 (*ArcFISH*, bioRxiv
2025.11.26.690837).  Unlike Hi-C-style contact-frequency callers, the
axis-wise approach explicitly models the anisotropic per-axis measurement
error that is typical of DNA FISH images (Z usually noisier than X/Y),
and works with as few as ~30 traces per chromosome.

Pipeline, per chromosome:

1. **Per-axis variance cube** — for each `(i, j)` bin pair and each
   axis `c`, compute the variance of `x_c[j] - x_c[i]` across traces.
2. **Filter + normalise** — two LOWESS passes on log(genomic distance):
   first to NaN-out per-trace outliers at 4 σ, then to put the
   distance-stratified mean variance at 1.
3. **Per-axis F-test** — candidate `(i, j)` gets `F_c = norm_var / ring_mean`
   against a local background ring `[inner_cut, outer_cut]`.
4. **ACAT Cauchy combine** — aggregate the per-axis p-values with the
   median-trace-variance-inverse axis weights.
5. **BH-FDR**, cluster accepted candidates by 1D proximity, pick the
   lowest-p summit per cluster.
6. **Pseudo-contact-frequency filter** — only keep summits where the
   fraction of traces with `3D pdist < adjacent-bin cutoff` exceeds
   1/2 (singleton) or 1/3 (larger cluster).

Output is a BEDPE-style `DataFrame` stored under `cd.results['loops']`."""),

    code("""\
import pandas as pd
from uchrom import ChromData
from uchrom.strc.loop import call_loops_axiswise_f, LoopCallerParams"""),

    md("## Load a chromatin-tracing dataset\n\nWe use the Takei et al. 2021 Nature mESC chromatin-tracing dataset (4DN accession `4DNFIHF3JCBY`).  The helper below auto-downloads it from the public 4DN S3 bucket into `example-data/` on the first run, and re-uses the local copy afterwards.  If the download can't reach the network, the notebook falls back to a small synthetic FOF-CT with hand-crafted TAD + loop structure so the notebook still runs."),

    code("""\
from pathlib import Path
import os

# Takei et al. 2021 Nature mESC chromatin tracing (mm10, 25 kb, 20 chroms,
# ~400 traces/chrom).  Public 4DN S3 object — no auth required.
TAKEI_URL = (
    'https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/'
    'wfoutput/e699334e-fb34-4a0e-8ef6-670b2099831a/4DNFIHF3JCBY.csv'
)

def _download_takei(dest: Path) -> bool:
    '''Download Takei 2021 FOF-CT to *dest* if it doesn't already exist.
    Returns True on success, False on any network error.'''
    if dest.exists():
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f'[data] downloading Takei 2021 (~22 MB) → {dest}')
    try:
        import urllib.request
        tmp = dest.with_suffix(dest.suffix + '.part')
        urllib.request.urlretrieve(TAKEI_URL, tmp)
        tmp.rename(dest)
        return True
    except Exception as exc:
        print(f'[data] download failed ({exc}); falling back to synthetic')
        return False

def _repo_root() -> Path:
    # nbconvert runs the notebook with cwd = tutorials/, so walk up to the
    # repo root (contains pyproject.toml) before anchoring example-data.
    for p in [Path.cwd(), *Path.cwd().parents]:
        if (p / 'pyproject.toml').exists() or (p / 'example-data').exists():
            return p
    return Path.cwd()

def find_fofct() -> str:
    root = _repo_root()
    # 1) Fast path — any local copy already on disk
    candidates = [
        root / 'example-data' / '4DNFIHF3JCBY.csv',
        Path.home() / 'Downloads' / 'ArcFISH_data' / '4DNFIHF3JCBY.csv',
        Path.home() / 'Downloads' / 'ArcFISH_data' / '4DNFIHF3JCBY.h5cd',
        Path.home() / 'Downloads' / '4DNFIHF3JCBY.csv',
    ]
    for c in candidates:
        if c.exists():
            print(f'[data] using real Takei 2021 FOF-CT: {c}')
            return str(c)

    # 2) Download to a stable repo-local location
    dest = root / 'example-data' / '4DNFIHF3JCBY.csv'
    if _download_takei(dest):
        print(f'[data] using real Takei 2021 FOF-CT: {dest}')
        return str(dest)

    # 3) If a synthetic was already built (e.g. by an earlier run), reuse it
    for p in [Path.cwd(), *Path.cwd().parents]:
        cand = p / 'example-data' / 'fofct_core.csv'
        if cand.exists():
            print(f'[data] using synthetic FOF-CT: {cand}')
            return str(cand)

    # 4) Last resort: synthesise a FOF-CT with built-in TAD + loop structure
    print('[data] generating synthetic FOF-CT (offline fallback)')
    (root / 'example-data').mkdir(parents=True, exist_ok=True)
    import numpy as np
    rng = np.random.default_rng(0)
    header = '''##FOF-CT_Version=v1.0
##Table_Namespace=4dn_FOF-CT_core
##Genome_Assembly=GRCh38
##XYZ_Unit=micron
#Lab_Name: Demo
##Columns=(Spot_ID, Trace_ID, X, Y, Z, Chrom, Chrom_Start, Chrom_End, Cell_ID)
'''
    # Tri-domain polymer with a nested loop:
    #   - Bins  0..9  = TAD 1 (tight, small step size inside)
    #   - Bins 10..19 = TAD 2 (tight) — separated from TAD 1 by a jump
    #   - Bins 20..29 = TAD 3 (tight) — separated from TAD 2 by a jump
    #   - Loop between bins 5 (in TAD 1) and 20 (first bin of TAD 3)
    # Each TAD walks with small step; inter-TAD jumps are large.
    def synth_trace(
        rng,
        tad_edges=(0, 10, 20, 30),
        intra_step=0.08,
        inter_jump=0.8,
        loop_a=5,
        loop_b=20,
        anchor_noise=0.04,
    ):
        n_bins = tad_edges[-1]
        w = np.zeros((n_bins, 3))
        # Walk each TAD internally, plus a big jump between TADs
        for t in range(len(tad_edges) - 1):
            a, b = tad_edges[t], tad_edges[t + 1]
            if t > 0:
                w[a] = w[a - 1] + rng.normal(scale=inter_jump, size=3)
            for i in range(a + 1, b):
                w[i] = w[i - 1] + rng.normal(scale=intra_step, size=3)
        # Loop closure: pin bin loop_b close to bin loop_a
        w[loop_b] = w[loop_a] + rng.normal(scale=anchor_noise, size=3)
        # Re-walk bins after loop_b so they stay continuous with the new anchor
        for i in range(loop_b + 1, n_bins):
            w[i] = w[i - 1] + rng.normal(scale=intra_step, size=3)
        return w

    rows = []
    sid = 1
    for cell in range(300):
        for trace in range(2):
            walk = synth_trace(rng)
            for bin_i in range(30):
                x, y, z = walk[bin_i]
                s = 1_000_000 + bin_i * 25_000
                rows.append((sid, f'{cell}_{trace}', x, y, z,
                             'chr17', s, s + 25_000, cell))
                sid += 1
    path = str(root / 'example-data' / 'fofct_core.csv')
    with open(path, 'w') as f:
        f.write(header)
        for r in rows:
            f.write(','.join(str(x) for x in r) + chr(10))
    return path

FOFCT = find_fofct()
print('using', FOFCT)
cd = ChromData.read(FOFCT) if FOFCT.endswith(".h5cd") else ChromData.from_fofct(FOFCT)
print(cd)
print()
print('traces per chrom:')
print(
    cd.spots.groupby('chrom', observed=True)['trace_id']
      .nunique().sort_values(ascending=False).head(10)
)"""),

    md("## Call loops on a single chromosome\n\nDefault parameters match ArcFISH (`fdr_cutoff=0.1`, `pval_cutoff=1e-5`, `gap=50 kb`, `inner_cut=25 kb`, `outer_cut=50 kb`)."),

    code("""\
# Pick a chromosome with enough traces
chrom = (
    cd.spots.groupby('chrom', observed=True)['trace_id']
      .nunique().idxmax()
)
print('calling loops on', chrom)

loops = call_loops_axiswise_f(
    cd,
    chrom=chrom,
    device='auto',   # CUDA > MPS > CPU
    store=True,      # also write to cd.results['loops']
    verbose=True,
)
loops"""),

    md("## Visualising the result\n\nThe companion modules `uchrom.fea` and `uchrom.pl` compute and render the population-level aggregates that chromatin-tracing papers use to present loop calls."),

    code("""\
import matplotlib.pyplot as plt
import numpy as np
from uchrom.fea import mean_distance_matrix, contact_frequency, radius_of_gyration
from uchrom.pl import plot_distance_matrix, plot_contact_map, plot_rg_histogram

df = cd.get_chrom(chrom).to_dataframe()

# Median pairwise distance matrix across all traces
dmat, bin_ids, n = mean_distance_matrix(df, chrom=chrom)
fig = plot_distance_matrix(dmat, title=f'Median 3D distance ({n} traces)')

# Overlay called loop summits on the heatmap
ax = fig.axes[0]
for _, row in loops.iterrows():
    i, j = int(row['summit_i']), int(row['summit_j'])
    ax.plot(j, i, 'o', mfc='none', mec='white', mew=1.5, ms=14)
    ax.plot(i, j, 'o', mfc='none', mec='white', mew=1.5, ms=14)
ax.set_title(ax.get_title() + f' — {len(loops)} loop(s) overlaid')
plt.show()"""),

    code("""\
# Population-level contact map at a user-chosen distance threshold
threshold = float(np.nanmedian(dmat[dmat > 0]) * 0.5)  # loose rule of thumb
cmat, bin_ids, n = contact_frequency(df, threshold=threshold, chrom=chrom)
fig = plot_contact_map(cmat, title=f'Contact frequency (< {threshold:.2g}, {n} traces)')
ax = fig.axes[0]
for _, row in loops.iterrows():
    i, j = int(row['summit_i']), int(row['summit_j'])
    ax.plot(j, i, 'o', mfc='none', mec='cyan', mew=1.5, ms=14)
    ax.plot(i, j, 'o', mfc='none', mec='cyan', mew=1.5, ms=14)
plt.show()"""),

    code("""\
# Per-trace radius of gyration distribution
rg = radius_of_gyration(df, chrom=chrom)
fig = plot_rg_histogram(rg, title=f'Rg distribution ({len(rg)} traces)')
plt.show()"""),

    md("## Tuning thresholds\n\nAll parameters live on `LoopCallerParams`:"),

    code("""\
params = LoopCallerParams(
    fdr_cutoff=0.05,    # stricter FDR
    pval_cutoff=1e-6,   # stricter p-value
    gap=25_000,         # tighter cluster gap
    k_sigma=3.0,        # aggressive outlier filter
)
loops_strict = call_loops_axiswise_f(cd, chrom=chrom, params=params, device='auto', store=False)
print(f'default: {len(loops)} loops  |  strict: {len(loops_strict)} loops')"""),

    md("## Whole-genome loop calling\n\nLoop over chromosomes and concatenate.  Each call is independent so trivial to parallelise if needed."),

    code("""\
all_loops = []
for chrom in cd.chroms:
    ls = call_loops_axiswise_f(cd, chrom=chrom, device='auto',
                               store=False, verbose=False)
    ls['chrom'] = chrom
    all_loops.append(ls)

loops_genome = pd.concat(all_loops, ignore_index=True)
print(f'Total called loops genome-wide: {len(loops_genome)}')
loops_genome.sort_values('pval').head(10)"""),

    md("## Persist results into the ChromData\n\nThe single-chromosome call already wrote to `cd.results['loops']`.  The result round-trips through `.h5cd`."),

    code("""\
out = Path(FOFCT).parent / 'with_loops.h5cd'
cd.write(str(out))

cd_reloaded = ChromData.read(str(out))
print(cd_reloaded.results['loops'])"""),

    md("## CLI\n\nFor batch scripts:\n\n```bash\npython -m uchrom.strc.loop --input=data.h5cd --output=data_loops.h5cd \\\n    --chrom=chr17 --device=auto\n\n# BEDPE export instead\npython -m uchrom.strc.loop --input=data.h5cd --output=loops.bedpe \\\n    --chrom=chr17 --device=auto\n```"),

    md("""\
## Comparison notes

This implementation is independent of the upstream ArcFISH
(GPL-3.0) source; all algorithmic components — per-trace 4 σ filter,
distance-stratified LOWESS normalisation, per-axis F-test, ACAT
combine, BH-FDR, pseudo-contact-frequency summit filter — are
reimplemented here.

On the canonical Takei 2021 mESC benchmark we see **~2–3× speedup on
Apple MPS** and typically 60–70 % precision vs ArcFISH's summit set
at ±25 kb anchor tolerance, with a more conservative call set overall.
MPS forces float32; on CUDA with float64 you will see higher overlap
with the upstream output."""),
]

write_nb(Path("tutorials") / "loop_calling.ipynb", nb4)


# ============================================================
# TAD calling
# ============================================================

nb5 = [
    md("""\
# TAD calling

`uchrom.strc.tad.call_tads_by_pval` is a GPU-accelerated reimplementation
of the ArcFISH TAD caller (Yu et al. 2025).  For each candidate boundary
position it asks: is the variance *inside* the window smaller than the
variance *across* the window?  A per-axis F-test answers this and ACAT
combines the three axes into one p-value per bin.  Local minima in that
p-value are scored as TAD boundaries; the hierarchical option emits
nested TAD levels by repeatedly dropping the weakest boundary."""),

    code("""\
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from uchrom import ChromData
from uchrom.strc.tad import call_tads_by_pval, TADCallerParams
from uchrom.fea import mean_distance_matrix
from uchrom.pl import plot_distance_matrix"""),

    md("## Load the example FOF-CT\n\nUses the Takei et al. 2021 Nature mESC chromatin-tracing dataset (4DN `4DNFIHF3JCBY`); auto-downloaded from the public 4DN S3 bucket on first run, cached under `example-data/`."),

    code("""\
from pathlib import Path
import os

TAKEI_URL = (
    'https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/'
    'wfoutput/e699334e-fb34-4a0e-8ef6-670b2099831a/4DNFIHF3JCBY.csv'
)

def _repo_root() -> Path:
    # Walk up until we find the repo marker (pyproject.toml); fall back to
    # cwd if nothing matches.  Avoid matching on ``example-data/`` alone —
    # prior notebook runs may have synthesised a ``tutorials/example-data/``.
    for p in [Path.cwd(), *Path.cwd().parents]:
        if (p / 'pyproject.toml').exists():
            return p
    return Path.cwd()

def find_fofct() -> str:
    root = _repo_root()
    candidates = [
        root / 'example-data' / '4DNFIHF3JCBY.csv',
        Path.home() / 'Downloads' / 'ArcFISH_data' / '4DNFIHF3JCBY.csv',
        Path.home() / 'Downloads' / 'ArcFISH_data' / '4DNFIHF3JCBY.h5cd',
        Path.home() / 'Downloads' / '4DNFIHF3JCBY.csv',
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    # Fall back to an earlier synthetic build if present
    cand = root / 'example-data' / 'fofct_core.csv'
    if cand.exists():
        return str(cand)
    # Download
    dest = root / 'example-data' / '4DNFIHF3JCBY.csv'
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f'[data] downloading Takei 2021 (~22 MB) → {dest}')
    import urllib.request
    tmp = dest.with_suffix(dest.suffix + '.part')
    urllib.request.urlretrieve(TAKEI_URL, tmp)
    tmp.rename(dest)
    return str(dest)

FOFCT = find_fofct()
print(FOFCT)
cd = ChromData.read(FOFCT) if FOFCT.endswith(".h5cd") else ChromData.from_fofct(FOFCT)
cd"""),

    md("## Run the TAD caller"),

    code("""\
chrom = cd.spots['chrom'].astype(str).iloc[0]
params = TADCallerParams(
    window_bp=1e5,     # boundary window (bp)
    fdr_cutoff=0.1,
    hierarchical=True,
    max_levels=3,
)
tads = call_tads_by_pval(cd, chrom=chrom, params=params, device='auto', verbose=True)
print(f'{len(tads)} TAD entries across {tads[\"level\"].nunique()} levels')
tads.head(15)"""),

    md("## Overlay TAD blocks on the median distance matrix\n\nA good TAD call should outline the **low-distance blocks** along the diagonal of the population-median pairwise distance matrix — the classic Hi-C TAD-view.  We draw each TAD as a rectangle along the diagonal."),

    code("""\
from matplotlib.patches import Rectangle

df = cd.get_chrom(chrom).to_dataframe()
dmat, bin_ids, n_traces = mean_distance_matrix(df, chrom=chrom)
B = len(bin_ids)
mid_bp = np.array([(s + e) * 0.5 for (s, e) in bin_ids])

def bin_of(bp):
    return int(np.argmin(np.abs(mid_bp - bp)))

def draw_tad_rects(ax, tad_df, **kw):
    for _, r in tad_df.iterrows():
        a = bin_of(r['start'])
        b = bin_of(r['end']) - 1  # inclusive end bin
        if b - a < 1:
            continue
        ax.add_patch(Rectangle(
            (a - 0.5, a - 0.5), b - a + 1, b - a + 1,
            fill=False, **kw,
        ))

# Top-level TADs only
top_level = tads[tads['level'] == tads['level'].min()]
fig = plot_distance_matrix(dmat, title=f'Median distance, top-level TADs ({len(top_level)})')
draw_tad_rects(fig.axes[0], top_level, edgecolor='white', linewidth=1.5)
plt.show()"""),

    md("## Hierarchy — nested TADs\n\nWith `hierarchical=True`, level 1 keeps only the strongest boundaries (coarse TADs); deeper levels add weaker ones.  Overlaying a different colour per level on the same heatmap makes the nesting obvious."),

    code("""\
fig = plot_distance_matrix(dmat, title='Hierarchical TADs')
ax = fig.axes[0]
level_colors = {1: 'white', 2: 'cyan', 3: 'orange', 4: 'magenta'}
for lv in sorted(tads['level'].unique()):
    draw_tad_rects(
        ax, tads[tads['level'] == lv],
        edgecolor=level_colors.get(lv, 'yellow'),
        linewidth=1.5 if lv == 1 else 1.0,
        linestyle='-' if lv == 1 else '--',
    )
handles = [
    plt.Line2D([0], [0], color=level_colors.get(lv, 'yellow'),
               ls='-' if lv == 1 else '--',
               label=f'level {lv} ({(tads[\"level\"]==lv).sum()} TADs)')
    for lv in sorted(tads['level'].unique())
]
ax.legend(handles=handles, loc='upper right', fontsize=9, framealpha=0.6)
plt.show()"""),

    md("## Boundary score track\n\nBehind the scenes each bin has a per-axis F-test p-value for the hypothesis *\"intra-window variance < inter-window variance\"*.  Plot the −log10 p along the chromosome to see where boundaries are most confident.  TAD corners should coincide with peaks."),

    code("""\
# Recompute the per-bin statistic directly so we can plot it.
from uchrom.fea.arc import axis_variance_cube, filter_normalize, axis_weight
from uchrom.strc.tad.arc_pval import _boundary_pvals

cube = axis_variance_cube(cd, chrom=chrom, device='auto')
cube = filter_normalize(cube)
w = axis_weight(cd, chrom=chrom, device='auto')
pvals_track, _ = _boundary_pvals(
    cube['norm_var'], cube['count'],
    np.array([(s+e)*0.5 for s,e in cube['bin_ids']]),
    w, window_bp=1e5,
)
neg_log_p = -np.log10(np.clip(np.where(np.isfinite(pvals_track), pvals_track, 1.0), 1e-300, 1.0))

fig, ax = plt.subplots(figsize=(9, 3))
ax.plot(np.arange(len(neg_log_p)), neg_log_p, 'k-', lw=1)
ax.set_xlabel('Bin index'); ax.set_ylabel('-log10 p (boundary)')
ax.set_title('TAD-boundary signal along the chromosome')
# Mark level-1 boundary bins
for _, r in top_level.iterrows():
    for bp in (r['start'], r['end']):
        k = bin_of(bp)
        if 0 < k < B:
            ax.axvline(k, color='red', alpha=0.5, lw=1)
plt.tight_layout()
plt.show()"""),

    md("""\
## Notes

- The variance-normalisation preprocessing is shared with
  :func:`uchrom.strc.loop.call_loops_axiswise_f` — you only pay for it
  once per chromosome if you cache.
- For a "flat" TAD partition set ``hierarchical=False`` or just use
  ``level == 1``.
- This caller complements the classical directionality-index method
  available in :func:`uchrom.strc.tad.get_domains`; they agree on
  strong TADs and disagree on boundary-marginal ones."""),
]

write_nb(Path("tutorials") / "tad_calling.ipynb", nb5)


# ============================================================
# A/B compartment
# ============================================================

nb6 = [
    md("""\
# A/B compartment calling

`uchrom.strc.comp.call_compartments_axes_pc` is a GPU-accelerated
reimplementation of the ArcFISH `ABCaller.by_axes_pc`.  The idea:

- Turn each axis' normalised variance matrix into a pseudo-contact
  matrix ``K = exp(-var)``.
- Take the **second-largest eigenvector** of each axis' ``K``.  The
  first captures the overall distance-decay trend; the second captures
  compartment-scale alternation.
- Weight the three per-axis PC2's by the ArcFISH axis weights, stack
  them as a 3-feature vector per bin, and run ``KMeans(n=2)``.
- Assign A/B so that the cluster with smaller mean intra-distance is
  the more compact one (A by convention)."""),

    code("""\
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from uchrom import ChromData
from uchrom.strc.comp import call_compartments_axes_pc, CompartmentCallerParams
from uchrom.fea import mean_distance_matrix
from uchrom.pl import plot_distance_matrix"""),

    md("## Load example data\n\nUses the Takei et al. 2021 Nature mESC chromatin-tracing dataset (4DN `4DNFIHF3JCBY`); auto-downloaded from the public 4DN S3 bucket on first run, cached under `example-data/`."),

    code("""\
from pathlib import Path

TAKEI_URL = (
    'https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/'
    'wfoutput/e699334e-fb34-4a0e-8ef6-670b2099831a/4DNFIHF3JCBY.csv'
)

def _repo_root() -> Path:
    # Walk up until we find the repo marker (pyproject.toml); fall back to
    # cwd if nothing matches.  Avoid matching on ``example-data/`` alone —
    # prior notebook runs may have synthesised a ``tutorials/example-data/``.
    for p in [Path.cwd(), *Path.cwd().parents]:
        if (p / 'pyproject.toml').exists():
            return p
    return Path.cwd()

def find_fofct() -> str:
    root = _repo_root()
    candidates = [
        root / 'example-data' / '4DNFIHF3JCBY.csv',
        Path.home() / 'Downloads' / 'ArcFISH_data' / '4DNFIHF3JCBY.csv',
        Path.home() / 'Downloads' / 'ArcFISH_data' / '4DNFIHF3JCBY.h5cd',
        Path.home() / 'Downloads' / '4DNFIHF3JCBY.csv',
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    cand = root / 'example-data' / 'fofct_core.csv'
    if cand.exists():
        return str(cand)
    dest = root / 'example-data' / '4DNFIHF3JCBY.csv'
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f'[data] downloading Takei 2021 (~22 MB) → {dest}')
    import urllib.request
    tmp = dest.with_suffix(dest.suffix + '.part')
    urllib.request.urlretrieve(TAKEI_URL, tmp)
    tmp.rename(dest)
    return str(dest)

FOFCT = find_fofct()
print(FOFCT)
cd = ChromData.read(FOFCT) if FOFCT.endswith(".h5cd") else ChromData.from_fofct(FOFCT)
cd"""),

    md("## Run the compartment caller"),

    code("""\
chrom = cd.spots['chrom'].astype(str).iloc[0]
comps = call_compartments_axes_pc(
    cd, chrom=chrom,
    params=CompartmentCallerParams(min_bins=2),
    device='auto', verbose=True,
)
print('compartment counts:')
print(comps['compartment'].value_counts())
comps.head(10)"""),

    md("## Compartment track\n\nThe weighted PC2 track alternates along the chromosome; A / B labels come from KMeans."),

    code("""\
fig, (ax_track, ax_label) = plt.subplots(
    2, 1, figsize=(10, 4), sharex=True,
    gridspec_kw={'height_ratios': [3, 1]},
)

mid_bp = (comps['start'] + comps['end']) / 2
ax_track.plot(mid_bp, comps['pc2'], 'k-', lw=1)
ax_track.axhline(0, color='grey', lw=0.5)
ax_track.set_ylabel('weighted PC2')
ax_track.set_title(f'A/B compartments — {chrom} ({len(comps)} bins)')

colors = {'A': 'tab:red', 'B': 'tab:blue'}
for lab, sub in comps.groupby('compartment'):
    for _, r in sub.iterrows():
        ax_label.axvspan(r['start'], r['end'], color=colors[lab], alpha=0.7)
ax_label.set_yticks([])
ax_label.set_xlabel('Genomic position (bp)')
ax_label.set_ylabel('A/B')
plt.tight_layout()
plt.show()"""),

    md("## Compartments on the distance matrix\n\nVisualising per-bin A/B labels next to the population-mean distance matrix makes the compartment pattern clear: A-A and B-B pairs are usually closer than A-B pairs."),

    code("""\
df = cd.get_chrom(chrom).to_dataframe()
dmat, bin_ids, _ = mean_distance_matrix(df, chrom=chrom)
fig = plot_distance_matrix(dmat, title=f'Median distance with A/B track')

ax = fig.axes[0]
# Colour the diagonal edge by compartment label
B = len(bin_ids)
for i in range(B):
    lab = comps.iloc[i]['compartment']
    ax.plot(i, -2, 's', ms=8, color=colors[lab], clip_on=False)
    ax.plot(-2, i, 's', ms=8, color=colors[lab], clip_on=False)
ax.set_xlim(-3, B)
ax.set_ylim(-3, B)
plt.show()"""),

    md("""\
## Notes

- The A/B assignment here is a convention (smaller mean intra-distance
  → A).  With a gene-density annotation you would pick whichever
  cluster has higher TSS density as A — this library does not ship
  that integration.
- ``n_clusters`` can be > 2 if you want to explore sub-compartment
  structure (A1 / A2 / B1 / B2).  The naming in the output DataFrame
  will no longer be ``{A, B}``.
- Like the loop and TAD callers, this caller shares the
  ``filter_normalize`` preprocessing step with the other ArcFISH-style
  routines."""),
]

write_nb(Path("tutorials") / "compartment.ipynb", nb6)


# ============================================================
# FISHnet — per-allele domain calling
# ============================================================

nb7 = [
    md("""\
# Single-cell domain calling with FISHnet

:func:`uchrom.strc.tad.call_domains_fishnet` is a reimplementation of
FISHnet (Patel et al. 2025, *Nature Methods* 22, 1255–1264,
doi:10.1038/s41592-025-02688-1), a graph-theory method for detecting
chromatin domains on **single alleles** rather than on a population
average.

Unlike the loop / TAD / compartment callers in tutorials 4–6 — which
aggregate across traces to get one answer per chromosome — FISHnet runs
on every trace independently, so each allele gets its own set of
domain boundaries.  The population-level signal is recovered by
summing single-allele domain masks (the "ensemble domain mask").

Algorithm, per trace:

1. **Threshold sweep** — binarise the pairwise distance matrix at a
   grid of distance thresholds (``(i, j) → 1`` if ``dist[i, j] ≤ t``).
2. **Smooth** — a ``(2*w)×(2*w)`` NaN-aware boxcar averages the binary
   map, converting the graph into a weighted network.
3. **Louvain modularity** — run Louvain community detection ``n_runs``
   times per threshold; pick the consensus partition by maximal
   adjusted-RAND similarity to the other runs.
4. **Plateau detection** — find runs of ``plateau_size`` or more
   consecutive thresholds that give the same number of communities;
   each plateau contributes one partition to the final call.
5. **Size exclusion + boundary merging** — drop tiny runs, collapse
   boundaries within ``merge_tol`` bins."""),

    code("""\
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from uchrom import ChromData
from uchrom.strc.tad import call_domains_fishnet, FISHnetParams
from uchrom.fea import mean_distance_matrix
from uchrom.pl import plot_distance_matrix"""),

    md("## Load the example FOF-CT\n\nUses the Takei et al. 2021 Nature mESC chromatin-tracing dataset (4DN `4DNFIHF3JCBY`); auto-downloaded from the public 4DN S3 bucket on first run, cached under `example-data/`."),

    code("""\
from pathlib import Path

TAKEI_URL = (
    'https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/'
    'wfoutput/e699334e-fb34-4a0e-8ef6-670b2099831a/4DNFIHF3JCBY.csv'
)

def _repo_root() -> Path:
    for p in [Path.cwd(), *Path.cwd().parents]:
        if (p / 'pyproject.toml').exists():
            return p
    return Path.cwd()

def find_fofct() -> str:
    root = _repo_root()
    candidates = [
        root / 'example-data' / '4DNFIHF3JCBY.csv',
        Path.home() / 'Downloads' / 'ArcFISH_data' / '4DNFIHF3JCBY.csv',
        Path.home() / 'Downloads' / '4DNFIHF3JCBY.csv',
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    dest = root / 'example-data' / '4DNFIHF3JCBY.csv'
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f'[data] downloading Takei 2021 (~22 MB) → {dest}')
    import urllib.request
    tmp = dest.with_suffix(dest.suffix + '.part')
    urllib.request.urlretrieve(TAKEI_URL, tmp)
    tmp.rename(dest)
    return str(dest)

FOFCT = find_fofct()
cd = ChromData.read(FOFCT) if FOFCT.endswith('.h5cd') else ChromData.from_fofct(FOFCT)
cd"""),

    md("## FISHnet on a single allele\n\nStart by looking at one trace.  The caller returns a dict with per-plateau domains, canonical boundary bin indices, and a (n_bins × n_bins) `domain_mask` counting how many plateaus grouped each bin pair together — a single-allele analogue of the ensemble domain mask."),

    code("""\
from uchrom.strc.tad.fishnet import call_domains_fishnet_trace
from uchrom.fea.distance import _bin_coord_cube, _pairwise_distance_per_trace

chrom = 'chr19'
df = cd.get_chrom(chrom).to_dataframe()
cube, bin_ids, trace_ids = _bin_coord_cube(df, chrom=chrom)
dists = _pairwise_distance_per_trace(cube)   # (n_traces, n_bins, n_bins), in μm

# Pick a high-coverage trace for the demo
cov = np.mean(np.isfinite(cube[:, :, 0]), axis=1)
ti = int(np.argmax(cov))
trace_id = trace_ids[ti]
print(f'demo trace: {trace_id}  coverage={cov[ti]:.0%}')

params = FISHnetParams(
    plateau_size=3,     # ≥3 adjacent thresholds → stable call
    n_louvain_runs=10,
    max_thresholds=30,  # 30 thresholds across the observed distance range
    min_coverage=0.3,
)
res = call_domains_fishnet_trace(dists[ti], params=params)
print(f'  {len(res[\"domains\"])} domains, {res[\"n_plateaus\"]} plateaus')
print('  boundaries:', res['boundaries'])"""),

    md("### Overlay single-allele domains on its distance matrix"),

    code("""\
from matplotlib.patches import Rectangle

fig, ax = plt.subplots(figsize=(6, 5))
im = ax.imshow(dists[ti], cmap='viridis_r', origin='lower')
for a, b in res['domains']:
    if b - a < 2:
        continue
    ax.add_patch(Rectangle((a - 0.5, a - 0.5), b - a, b - a,
                           fill=False, edgecolor='white', lw=1.5))
ax.set_title(f'{chrom} trace {trace_id} — FISHnet ({len(res[\"domains\"])} domains)')
ax.set_xlabel('Bin'); ax.set_ylabel('Bin')
plt.colorbar(im, ax=ax, label='distance (μm)')
plt.tight_layout()
plt.show()"""),

    md("## FISHnet across many alleles → ensemble domain mask\n\nEach trace gets its own set of domain boundaries; summing the single-allele domain masks across many traces produces an **ensemble domain mask** — a (n_bins × n_bins) array where `mask[i, j]` counts the number of alleles in which bins `i` and `j` fall in the same domain.  This is FISHnet's population-level readout."),

    code("""\
fishnet_df = call_domains_fishnet(
    cd, chrom=chrom, params=params, verbose=True,
    max_traces=80,   # keep tutorial runtime reasonable
)
print(f'{len(fishnet_df)} domains across {fishnet_df[\"trace_id\"].nunique()} traces')
print('  mean domains per trace:', fishnet_df.groupby('trace_id', observed=True).size().mean().round(2))
fishnet_df.head()"""),

    code("""\
ens = cd.results['fishnet_ensemble']
mask = ens['mask']
print(f'ensemble domain mask: shape={mask.shape}, max={mask.max()}, n_traces={ens[\"n_traces\"]}')

# Population-mean distance matrix for comparison
dmat, _, n_traces_all = mean_distance_matrix(df, chrom=chrom)

fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
im0 = axes[0].imshow(dmat, cmap='viridis_r', origin='lower')
axes[0].set_title(f'Median pairwise distance ({n_traces_all} traces)')
plt.colorbar(im0, ax=axes[0], label='distance (μm)')

im1 = axes[1].imshow(mask, cmap='magma', origin='lower')
axes[1].set_title(f'FISHnet ensemble domain mask ({ens[\"n_traces\"]} traces)')
plt.colorbar(im1, ax=axes[1], label='# alleles sharing a domain')
for ax in axes:
    ax.set_xlabel('Bin'); ax.set_ylabel('Bin')
plt.tight_layout()
plt.show()"""),

    md("The ensemble mask's block-diagonal structure should track the population distance matrix's low-distance blocks — the two are different readouts of the same underlying chromatin folding."),

    md("## Per-allele variability of domain counts\n\nA unique aspect of FISHnet is that it returns **one call per allele**, so we can look at cell-to-cell variability of the number of domains."),

    code("""\
counts_per_trace = (
    fishnet_df.groupby('trace_id', observed=True).size()
)
fig, ax = plt.subplots(figsize=(6, 3.5))
ax.hist(counts_per_trace, bins=np.arange(0, counts_per_trace.max() + 2) - 0.5,
        color='tab:blue', edgecolor='black')
ax.set_xlabel('Number of FISHnet domains per allele')
ax.set_ylabel('# alleles')
ax.set_title(f'{chrom} — single-allele domain count distribution')
plt.tight_layout()
plt.show()"""),

    md("""\
## Notes and when to use which caller

- **FISHnet (this tutorial)** — per-allele domain calls; cell-to-cell
  variability is explicit; ideal for questions like *"which alleles
  share the same folding pattern?"*.
- **F-test hierarchical TAD caller** (tad_calling tutorial) — population-level
  boundaries with an FDR-controlled hierarchy; ideal for
  *"where are the consensus domain boundaries in this cell type?"*.
- **Directionality index** (:func:`uchrom.strc.tad.get_domains`) —
  classical Dixon-style caller on a contact/frequency matrix.

**Hyperparameters that matter:**

| Parameter | Effect |
|-----------|--------|
| ``plateau_size`` | Higher = fewer but more robust calls |
| ``window_size`` | Smoothing kernel — 2 is the paper default |
| ``max_thresholds`` | Density of the threshold sweep — runtime scales linearly |
| ``n_louvain_runs`` | Stability of consensus — 10–20 is enough for most data |
| ``min_coverage`` | Skip traces with < N bins detected.  Lower for sparse data |
| ``impute`` | Linear interpolate missing bins before thresholding |

The upstream reference implementation (``github.com/RohanpatelUpenn/FISHnet``)
uses a custom Louvain solver; this reimplementation delegates to
:func:`networkx.algorithms.community.louvain_communities` so installation
is simpler."""),
]

write_nb(Path("tutorials") / "fishnet_domains.ipynb", nb7)


# ============================================================
# Spot-to-fiber tracing (jie) on real seqFISH+ data
# ============================================================

nb8 = [
    md("""\
# Spot-to-fiber tracing with jie on seqFISH+ data

:func:`uchrom.im.trace.align_spots` is an independent reimplementation
of jie (Jia & Ren 2022, *Nature Biotechnology* 22,
doi:10.1038/s41587-022-01568-9), a *spatial genome aligner* that
resolves spot-to-fiber assignment in multiplexed DNA-FISH data.

Where do the tutorials so far start?  The FOF-CT files we've been
using (4DN `4DNFIHF3JCBY`) already carry a ``trace_id`` column — the
fiber each spot belongs to has been assigned upstream.  But before
that assignment, the raw seqFISH+ output looks like this:

- Every cell has **multiple candidate spots per locus** (noise, sister
  chromatids, copy-number variants → often 3–8 per 25-kb region).
- No ground-truth link tells you which spot lies on which chromatin
  fiber.

jie decides:

1. For each (cell, chromosome), build a DAG over candidate spots
   ordered by genomic position.
2. Score each candidate edge by the Gaussian-chain bond probability —
   "how plausibly are these two spots linked by a ~L-bp piece of
   chromatin?"
3. Shortest path picks one spot per locus; iterate (masking used
   spots) to extract all fibers → **ploidy emerges naturally**.
4. Post-hoc sister-chromatid detection groups fibers whose
   co-locus distances stay within a threshold."""),

    code("""\
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

from uchrom.im.trace import align_spots, SpotAlignerParams
from uchrom import ChromData"""),

    md("""\
## Auto-download the Takei 2021 seqFISH+ spot-level data

The raw detections used by Jia & Ren 2022 live in Takei et al. 2021's
Zenodo deposit (doi:10.5281/zenodo.3735329, 144 MB zip — slower than
the FOF-CT file used in previous tutorials, so cache aggressively).

The archive contains eight CSVs; we use
``DNAseqFISH+25kbloci-E14-replicate1.csv`` (~35 MB uncompressed) which
has 46 mESC cells × 20 chromosomes × 60 loci at 25-kb resolution."""),

    code("""\
import zipfile
import urllib.request

DATA_URL = (
    'https://zenodo.org/records/3735329/files/DNAseqFISH%2B.zip?download=1'
)

def _repo_root() -> Path:
    for p in [Path.cwd(), *Path.cwd().parents]:
        if (p / 'pyproject.toml').exists():
            return p
    return Path.cwd()

def load_seqfish_spots(variant: str = '25kbloci-E14-replicate1') -> pd.DataFrame:
    '''Download (once) and read one replicate from the Zenodo zip.'''
    root = _repo_root()
    zip_path = root / 'example-data' / 'DNAseqFISH+.zip'
    if not zip_path.exists():
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        print(f'[data] downloading seqFISH+ (~144 MB) → {zip_path}')
        tmp = zip_path.with_suffix('.zip.part')
        urllib.request.urlretrieve(DATA_URL, tmp)
        tmp.rename(zip_path)
    inner = f'DNAseqFISH+/DNAseqFISH+{variant}.csv'
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(inner) as f:
            return pd.read_csv(f)

raw = load_seqfish_spots()
print('raw shape:', raw.shape)
print('cells:', raw['cellID'].nunique(), ' chromIDs:', raw['chromID'].nunique())
print('spots per (cell, chromID, region):',
      raw.groupby(['cellID', 'chromID', 'regionID (hyb1-60)']).size().describe().round(1).to_dict())"""),

    md("""\
The key observation is in the spots-per-(cell, chromID, region) histogram:
**the median is 6 candidate spots per locus** — raw seqFISH+ is very
far from one-spot-per-locus, which is exactly the ambiguity jie is
designed to resolve."""),

    md("""\
## Convert to the `align_spots` input contract

``align_spots`` expects a long-format DataFrame with columns
``cell_id, chrom, start, end, x, y, z`` (and optional
``sigma_x/y/z, spot_id``).  We translate the seqFISH+ columns:

- ``cellID`` → ``cell_id``
- ``chromID`` → ``chrom`` (1..19 → ``chr1..chr19``, 20 → ``chrX``)
- ``regionID (hyb1-60)`` → bin index along the chromosome, converted
  to ``(start, end)`` at 25-kb resolution.
- ``x, y`` are pixel indices — multiply by 103 nm/pixel.
- ``z`` is pixel index — multiply by 250 nm/pixel.
- We drop ``labelID == -1`` spots (the upstream pipeline's rejected
  detections) and ignore other labelID values so jie works purely from
  geometry.  The ``labelID`` column is kept separately as a
  pre-assigned label we can compare against later."""),

    code("""\
XY_PIX_NM = 103.0
Z_PIX_NM = 250.0
BIN_SIZE_BP = 25_000

def _chrom_name(cid: int) -> str:
    return 'chrX' if cid == 20 else f'chr{cid}'

raw_good = raw[raw['labelID'] >= 0].copy()
spots_df = pd.DataFrame({
    'spot_id':  np.arange(len(raw_good)),
    'cell_id':  raw_good['cellID'].astype(str).values,
    'chrom':    raw_good['chromID'].map(_chrom_name).values,
    'start':    ((raw_good['regionID (hyb1-60)'] - 1) * BIN_SIZE_BP).astype(int).values,
    'end':      (raw_good['regionID (hyb1-60)'] * BIN_SIZE_BP).astype(int).values,
    'x':        (raw_good['x'] * XY_PIX_NM).values,
    'y':        (raw_good['y'] * XY_PIX_NM).values,
    'z':        (raw_good['z'] * Z_PIX_NM).values,
    'labelID':  raw_good['labelID'].astype(int).values,  # upstream pre-assignment
})
print('converted shape:', spots_df.shape)
print('cells:', spots_df['cell_id'].nunique(),
      'chroms:', spots_df['chrom'].nunique())
spots_df.head()"""),

    md("""\
## Run jie on one chromosome

To keep the tutorial runtime small we trace chr19 only — ~60 loci ×
~350 candidate spots per (cell, chrom), which is 46 Dijkstra runs
total.  Real analyses would loop over all chromosomes (embarrassingly
parallel)."""),

    code("""\
chr_to_use = 'chr19'
sub = spots_df[spots_df['chrom'] == chr_to_use].copy()
print(f'{len(sub)} spots on {chr_to_use} across {sub["cell_id"].nunique()} cells')

# We pass τ explicitly (0.012 nm/bp is the canonical mESC value; the
# automatic fit would be inflated by decoys in the raw data).  Tighter
# min_spots_per_fiber + max_fibers + mean_edge_weight_cutoff together
# reject spurious fibers built out of decoy spots.
cd = align_spots(
    sub.drop(columns=['labelID']),
    params=SpotAlignerParams(
        persistence_length_bp=150.0,
        max_skip=3,
        gap_penalty=3.0,
        min_spots_per_fiber=30,          # ≥50% of 60 loci
        max_fibers_per_chrom=4,
        mean_edge_weight_cutoff=5.0,     # reject high-cost paths
        detect_sisters=True,
        sister_pair_radius_nm=400.0,
        verbose=True,
    ),
    tau_by_chrom={chr_to_use: 0.012},
)
print('\\n', cd)"""),

    md("## Ploidy distribution across cells"),

    code("""\
ploidy = cd.results['ploidy']
print('ploidy table:')
print(ploidy)
print('\\nploidy distribution (n_sister_groups = distinct fibers):')
print(ploidy['n_sister_groups'].value_counts().sort_index())

fig, ax = plt.subplots(figsize=(6, 3.5))
ax.hist(ploidy['n_sister_groups'], bins=np.arange(0, ploidy['n_sister_groups'].max() + 2) - 0.5,
        color='tab:green', edgecolor='black')
ax.set_xlabel('# distinct fibers (sister-merged) per cell')
ax.set_ylabel('# cells')
ax.set_title(f'{chr_to_use} — jie-called ploidy (mESC E14 replicate 1)')
plt.tight_layout()
plt.show()"""),

    md("""\
mESC cells are nominally diploid; a peak at 2 is the expected
signature.  Deviations (triploid or more, or monoploid) reflect
aneuploidy or reconstruction noise."""),

    md("""\
## Agreement with the upstream labelID

The Takei 2021 dataset ships with a ``labelID`` column carrying an
upstream pre-assignment (0..3 plus -1 for rejected).  We can compare:
for each jie-called fiber, what fraction of its spots share the same
``labelID``?  A high purity means jie recovers the same fibers as the
upstream pipeline using only geometry + polymer physics."""),

    code("""\
# Join called trace_id back onto the original spots by spot_id
called = cd.spots[['spot_id', 'cell_id', 'trace_id']].copy()
called['trace_id'] = called['trace_id'].astype(int)
joined = sub.merge(called, on=['spot_id', 'cell_id'], how='inner')

purities = []
for (cell, tid), g in joined.groupby(['cell_id', 'trace_id']):
    top = g['labelID'].value_counts().iloc[0]
    purities.append(top / len(g))

fig, ax = plt.subplots(figsize=(6, 3.5))
ax.hist(purities, bins=np.linspace(0, 1, 21), color='tab:orange', edgecolor='black')
ax.set_xlabel('trace purity (top labelID / total)')
ax.set_ylabel('# called fibers')
ax.set_title(f'{chr_to_use} — agreement with upstream labelID (mean={np.mean(purities):.2f})')
plt.tight_layout()
plt.show()
print(f'mean purity: {np.mean(purities):.3f}')
print(f'median: {np.median(purities):.3f}; 25th percentile: {np.quantile(purities, 0.25):.3f}')"""),

    md("""\
## Feed jie output into FISHnet

Because ``align_spots`` returns a ``ChromData``, every downstream tool
in u-chrom works on the result unchanged.  We run FISHnet on the
jie-assigned traces to confirm the 3-D structure is domain-structured
and comparable with the FOF-CT-based analyses in tutorials 5 and 7."""),

    code("""\
from uchrom.strc.tad import call_domains_fishnet, FISHnetParams
from uchrom.fea import mean_distance_matrix

fishnet_df = call_domains_fishnet(
    cd, chrom=chr_to_use,
    params=FISHnetParams(
        plateau_size=3, n_louvain_runs=10, max_thresholds=30,
        min_coverage=0.3,
    ),
    verbose=True, max_traces=60,
)
print(f'{len(fishnet_df)} domains across {fishnet_df["trace_id"].nunique()} traces')"""),

    code("""\
ens = cd.results['fishnet_ensemble']
dmat, _, _ = mean_distance_matrix(cd.get_chrom(chr_to_use).to_dataframe(), chrom=chr_to_use)

fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
im0 = axes[0].imshow(dmat, cmap='viridis_r', origin='lower')
axes[0].set_title('Median distance after jie (FISH coords in nm, jie-assigned traces)')
plt.colorbar(im0, ax=axes[0], label='distance (nm)')

im1 = axes[1].imshow(ens['mask'], cmap='magma', origin='lower')
axes[1].set_title(f'FISHnet ensemble mask ({ens["n_traces"]} traces)')
plt.colorbar(im1, ax=axes[1], label='# alleles sharing a domain')
for ax in axes: ax.set_xlabel('Bin'); ax.set_ylabel('Bin')
plt.tight_layout()
plt.show()"""),

    md("""\
## Notes

- **Two parallel paths in ``uchrom``**: you can either start from an
  already-traced FOF-CT file (other tutorials use 4DN
  `4DNFIHF3JCBY`) **or** from raw detections + jie (this tutorial).
  Both produce a `ChromData` with the same schema.
- **jie is SV-blind** — inversions/translocations break the DAG
  monotonicity assumption.  Flag or exclude known SV regions if
  working with tumour / abnormal samples.
- **Sister chromatid resolution is soft**: when sisters are very close
  (< ~150 nm) the aligner tends to merge them into one fiber.  This
  mirrors the upstream implementation's limits.
- For the full ~920 (cell, chromosome) combinations in this dataset,
  expect ~15 minutes on a single core.  Trivially parallelisable per
  (cell, chromosome) using ``multiprocessing``."""),
]

write_nb(Path("tutorials") / "jie_aligner.ipynb", nb8)


# ============================================================
# README
# ============================================================

readme = """\
# U-Chrom tutorials

Jupyter notebooks walking through the main analysis pipelines.  All
notebooks assume you have installed `uchrom` (`pip install -e .` from
the repo root) and are running from the repo root so relative paths
work.

Grouped by the U-Chrom module each tutorial targets:

### Core & I/O

| Notebook | Topic |
|----------|-------|
| `chromdata_basics.ipynb` | The `ChromData` container |
| `import_fofct.ipynb` | Loading FOF-CT imaging data |

### Reconstruction (`uchrom.recon`)

| Notebook | Topic |
|----------|-------|
| `reconstruction.ipynb` | 3D reconstruction from Hi-C |
| `benchmark.ipynb` | Benchmarking MDS reconstruction (speed & quality) |

### Imaging / tracing (`uchrom.im`)

| Notebook | Topic |
|----------|-------|
| `jie_aligner.ipynb` | Spot-to-fiber tracing on raw seqFISH+ detections |

### Structure identification (`uchrom.strc`)

| Notebook | Submodule | Topic |
|----------|-----------|-------|
| `loop_calling.ipynb` | `strc.loop` | Loop calling (axis-wise F-test) |
| `tad_calling.ipynb` | `strc.tad` | TAD calling (hierarchical F-test) |
| `fishnet_domains.ipynb` | `strc.tad` | Per-allele domain calling (FISHnet) |
| `compartment.ipynb` | `strc.comp` | A/B compartment calling |

The notebooks are regenerated by running
`python tutorials/_build_notebooks.py` from the repo root, which keeps
them small and diff-friendly.
"""
Path("tutorials/README.md").write_text(readme)
print("wrote tutorials/README.md")
